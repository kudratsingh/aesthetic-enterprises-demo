"""Integration tests for POST /api/v1/webhooks/payments and the simulate
endpoint (ADR-0010).

Covers the auth surface (signature valid/invalid/missing, unconfigured 503),
success → invoice paid via royalty.mark_invoice_paid, failure → invoice
untouched, idempotent replays, failed → succeeded retry, and the Phase 6 exit
proof: a paid invoice drops out of the read-derived aging on its own.
"""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient, Response

from app.core.config import Settings, get_settings
from app.main import app
from tests.integration.collections_helpers import (
    PAYMENT_WEBHOOK_PATH,
    PAYMENT_WEBHOOK_SECRET,
    IssuedInvoice,
    hq_headers,
    issued_invoice,
    operator_headers,
    sign_payment_body,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def configured_secret() -> AsyncIterator[None]:
    """Serve real settings with the payment secret set, via dependency override."""
    settings = get_settings().model_copy(update={"payment_webhook_secret": PAYMENT_WEBHOOK_SECRET})
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
async def unconfigured_secret() -> AsyncIterator[None]:
    settings = get_settings().model_copy(update={"payment_webhook_secret": None})
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_settings, None)


async def _post_event(
    client: AsyncClient, payload: dict[str, Any], signature: str | None = None
) -> Response:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    headers["X-Webhook-Signature"] = signature if signature is not None else sign_payment_body(body)
    return await client.post(PAYMENT_WEBHOOK_PATH, content=body, headers=headers)


async def _checkout(client: AsyncClient, settings: Settings, inv: IssuedInvoice) -> str:
    """Operator opens checkout; returns the provider_ref."""
    resp = await client.post(
        f"/api/v1/collections/invoices/{inv.invoice_id}/checkout",
        headers=operator_headers(settings, inv.org_id, inv.user_id),
    )
    assert resp.status_code == 201
    ref: str = resp.json()["payment"]["provider_ref"]
    return ref


async def _invoice_status(client: AsyncClient, settings: Settings, invoice_id: uuid.UUID) -> str:
    listing = await client.get("/api/v1/royalty/invoices", headers=hq_headers(settings))
    row = next(r for r in listing.json() if r["id"] == str(invoice_id))
    status: str = row["status"]
    return status


async def _aging(client: AsyncClient, settings: Settings) -> dict[str, Any]:
    resp = await client.get("/api/v1/royalty/invoices/aging", headers=hq_headers(settings))
    assert resp.status_code == 200
    data: dict[str, Any] = resp.json()
    return data


# ---------------------------------------------------------------------------
# Auth surface (mirrors the ingest webhook contract)
# ---------------------------------------------------------------------------


async def test_missing_signature_is_401(client: AsyncClient, configured_secret: None) -> None:
    resp = await client.post(
        PAYMENT_WEBHOOK_PATH, content=b"{}", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_signature"


async def test_invalid_signature_is_401(client: AsyncClient, configured_secret: None) -> None:
    resp = await _post_event(
        client,
        {"provider_ref": "mock_cs_000000000000", "event": "payment_succeeded"},
        signature="0" * 64,
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_signature"


async def test_unconfigured_secret_is_503(client: AsyncClient, unconfigured_secret: None) -> None:
    resp = await client.post(
        PAYMENT_WEBHOOK_PATH,
        content=b"{}",
        headers={"Content-Type": "application/json", "X-Webhook-Signature": "0" * 64},
    )
    assert resp.status_code == 503
    assert resp.json()["code"] == "payment_webhook_not_configured"


async def test_unknown_provider_ref_is_400(client: AsyncClient, configured_secret: None) -> None:
    resp = await _post_event(
        client, {"provider_ref": "mock_cs_ffffffffffff", "event": "payment_succeeded"}
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "unknown_provider_ref"


async def test_invalid_event_payload_is_400(client: AsyncClient, configured_secret: None) -> None:
    resp = await _post_event(client, {"provider_ref": "mock_cs_000000000000", "event": "refund"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_payload"


# ---------------------------------------------------------------------------
# Success: invoice paid, aging updates itself (Phase 6 exit criterion)
# ---------------------------------------------------------------------------


async def test_payment_succeeded_pays_invoice_and_aging_decrements(
    client: AsyncClient, settings: Settings, configured_secret: None
) -> None:
    inv = await issued_invoice()

    before = await _aging(client, settings)
    assert str(inv.invoice_id) in [r["id"] for r in before["invoices"]]
    count_before = sum(b["invoice_count"] for b in before["buckets"])

    ref = await _checkout(client, settings, inv)
    resp = await _post_event(client, {"provider_ref": ref, "event": "payment_succeeded"})
    assert resp.status_code == 200
    assert resp.json()["applied"] is True
    assert resp.json()["payment_status"] == "succeeded"
    assert resp.json()["invoice_status"] == "paid"

    assert await _invoice_status(client, settings, inv.invoice_id) == "paid"

    # Aging is read-derived: no sweeper ran, the paid invoice simply dropped out.
    after = await _aging(client, settings)
    assert str(inv.invoice_id) not in [r["id"] for r in after["invoices"]]
    assert sum(b["invoice_count"] for b in after["buckets"]) == count_before - 1


async def test_success_replay_is_noop(
    client: AsyncClient, settings: Settings, configured_secret: None
) -> None:
    inv = await issued_invoice()
    ref = await _checkout(client, settings, inv)
    await _post_event(client, {"provider_ref": ref, "event": "payment_succeeded"})

    replay = await _post_event(client, {"provider_ref": ref, "event": "payment_succeeded"})
    assert replay.status_code == 200
    assert replay.json()["applied"] is False
    assert replay.json()["payment_status"] == "succeeded"
    assert replay.json()["invoice_status"] == "paid"

    # An out-of-order failure event can never un-pay an invoice.
    late_failure = await _post_event(client, {"provider_ref": ref, "event": "payment_failed"})
    assert late_failure.json()["applied"] is False
    assert late_failure.json()["payment_status"] == "succeeded"
    assert await _invoice_status(client, settings, inv.invoice_id) == "paid"


# ---------------------------------------------------------------------------
# Failure: payment failed, invoice untouched, retry may still succeed
# ---------------------------------------------------------------------------


async def test_payment_failed_leaves_invoice_collectible(
    client: AsyncClient, settings: Settings, configured_secret: None
) -> None:
    inv = await issued_invoice()
    ref = await _checkout(client, settings, inv)

    failed = await _post_event(client, {"provider_ref": ref, "event": "payment_failed"})
    assert failed.status_code == 200
    assert failed.json() == {
        "payment_id": failed.json()["payment_id"],
        "invoice_id": str(inv.invoice_id),
        "payment_status": "failed",
        "invoice_status": None,
        "applied": True,
    }
    assert await _invoice_status(client, settings, inv.invoice_id) == "issued"

    replay = await _post_event(client, {"provider_ref": ref, "event": "payment_failed"})
    assert replay.json()["applied"] is False

    # The payer retries the same checkout session and succeeds.
    retried = await _post_event(client, {"provider_ref": ref, "event": "payment_succeeded"})
    assert retried.json()["applied"] is True
    assert await _invoice_status(client, settings, inv.invoice_id) == "paid"


# ---------------------------------------------------------------------------
# Simulate endpoint: the mock's stand-in for the provider's redirect flow
# ---------------------------------------------------------------------------


async def test_operator_simulate_pays_own_invoice(client: AsyncClient, settings: Settings) -> None:
    inv = await issued_invoice()
    headers = operator_headers(settings, inv.org_id, inv.user_id)
    checkout = await client.post(
        f"/api/v1/collections/invoices/{inv.invoice_id}/checkout", headers=headers
    )
    payment_id = checkout.json()["payment"]["id"]

    resp = await client.post(f"/api/v1/collections/payments/{payment_id}/simulate", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["payment_status"] == "succeeded"
    assert resp.json()["invoice_status"] == "paid"
    assert await _invoice_status(client, settings, inv.invoice_id) == "paid"

    replay = await client.post(
        f"/api/v1/collections/payments/{payment_id}/simulate", headers=headers
    )
    assert replay.status_code == 200
    assert replay.json()["applied"] is False


async def test_operator_cannot_simulate_another_orgs_payment(
    client: AsyncClient, settings: Settings
) -> None:
    inv_a = await issued_invoice()
    inv_b = await issued_invoice()
    checkout = await client.post(
        f"/api/v1/collections/invoices/{inv_a.invoice_id}/checkout",
        headers=operator_headers(settings, inv_a.org_id, inv_a.user_id),
    )
    payment_id = checkout.json()["payment"]["id"]

    resp = await client.post(
        f"/api/v1/collections/payments/{payment_id}/simulate",
        headers=operator_headers(settings, inv_b.org_id, inv_b.user_id),
    )
    assert resp.status_code == 404  # RLS: another org's payment reads as not found
    assert await _invoice_status(client, settings, inv_a.invoice_id) == "issued"
