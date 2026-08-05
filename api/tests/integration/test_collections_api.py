"""Integration tests for the collections checkout + payments listing (ADR-0010).

Covers checkout idempotency, the paid/superseded refusals, and RLS scoping:
an operator can neither open checkout on another org's invoice nor see another
org's payments.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import Settings
from app.core.security import TokenClaims, mint_token
from tests.conftest import HQ_ORG_ID, tenant_session
from tests.integration.collections_helpers import (
    INVOICE_CENTS,
    IssuedInvoice,
    hq_headers,
    issued_invoice,
    mock_provider_ref,
    operator_headers,
)

pytestmark = pytest.mark.integration


def _checkout_path(inv: IssuedInvoice) -> str:
    return f"/api/v1/collections/invoices/{inv.invoice_id}/checkout"


def _op_headers(settings: Settings, inv: IssuedInvoice) -> dict[str, str]:
    return operator_headers(settings, inv.org_id, inv.user_id)


async def test_checkout_creates_initiated_payment_and_is_idempotent(
    client: AsyncClient, settings: Settings
) -> None:
    inv = await issued_invoice()
    headers = _op_headers(settings, inv)

    first = await client.post(_checkout_path(inv), headers=headers)
    assert first.status_code == 201
    body = first.json()
    assert body["reused"] is False
    assert body["payment"]["status"] == "initiated"
    assert body["payment"]["invoice_id"] == str(inv.invoice_id)
    assert body["payment"]["org_id"] == str(inv.org_id)
    assert body["payment"]["amount_cents"] == INVOICE_CENTS
    assert body["payment"]["provider"] == "mock"
    assert body["payment"]["provider_ref"] == mock_provider_ref(inv.invoice_id)
    assert body["checkout_url"].startswith("https://checkout.mock.local/")

    again = await client.post(_checkout_path(inv), headers=headers)
    assert again.status_code == 201
    assert again.json()["reused"] is True
    assert again.json()["payment"]["id"] == body["payment"]["id"]

    listing = await client.get(
        "/api/v1/collections/payments",
        headers=headers,
        params={"invoice_id": str(inv.invoice_id)},
    )
    assert listing.status_code == 200
    assert [p["id"] for p in listing.json()] == [body["payment"]["id"]]


async def test_checkout_refuses_paid_invoice(client: AsyncClient, settings: Settings) -> None:
    inv = await issued_invoice()
    paid = await client.post(
        f"/api/v1/royalty/invoices/{inv.invoice_id}/pay", headers=hq_headers(settings)
    )
    assert paid.json()["status"] == "paid"

    resp = await client.post(_checkout_path(inv), headers=_op_headers(settings, inv))
    assert resp.status_code == 409
    assert resp.json()["code"] == "invoice_already_paid"


async def test_checkout_refuses_superseded_invoice(client: AsyncClient, settings: Settings) -> None:
    inv = await issued_invoice()
    successor = await issued_invoice()
    # Point the invoice at a successor directly (invoices are mutable rows and
    # the full reissue flow is exercised in test_royalty_api).
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        await s.execute(
            text("UPDATE invoices SET superseded_by = :new WHERE id = :old"),
            {"new": successor.invoice_id, "old": inv.invoice_id},
        )

    resp = await client.post(_checkout_path(inv), headers=_op_headers(settings, inv))
    assert resp.status_code == 409
    assert resp.json()["code"] == "invoice_superseded"


async def test_operator_cannot_checkout_another_orgs_invoice(
    client: AsyncClient, settings: Settings
) -> None:
    inv_a = await issued_invoice()
    inv_b = await issued_invoice()

    resp = await client.post(_checkout_path(inv_a), headers=_op_headers(settings, inv_b))
    assert resp.status_code == 404  # RLS: another org's invoice reads as not found


async def test_payments_are_rls_scoped_per_operator(
    client: AsyncClient, settings: Settings
) -> None:
    inv_a = await issued_invoice()
    inv_b = await issued_invoice()
    created = await client.post(_checkout_path(inv_a), headers=_op_headers(settings, inv_a))
    payment_id = created.json()["payment"]["id"]

    # Operator B's listing never contains A's payment (invariant 5 for payments).
    b_listing = await client.get(
        "/api/v1/collections/payments", headers=_op_headers(settings, inv_b)
    )
    assert payment_id not in [p["id"] for p in b_listing.json()]

    # Straight to the database as B: the row is invisible, not just filtered.
    async with tenant_session(str(inv_b.org_id), "operator") as s:
        rows = (
            await s.execute(text("SELECT id FROM payments WHERE id = :id"), {"id": payment_id})
        ).all()
    assert rows == []

    # HQ sees it (policy-level bypass, ADR-0002).
    hq_listing = await client.get("/api/v1/collections/payments", headers=hq_headers(settings))
    assert payment_id in [p["id"] for p in hq_listing.json()]


async def test_clinic_staff_may_not_use_collections(
    client: AsyncClient, settings: Settings
) -> None:
    inv = await issued_invoice()
    staff = mint_token(
        TokenClaims(sub="staff-test", org_id=str(inv.org_id), role="clinic_staff"), settings
    )
    resp = await client.post(_checkout_path(inv), headers={"Authorization": f"Bearer {staff}"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "role_forbidden"
