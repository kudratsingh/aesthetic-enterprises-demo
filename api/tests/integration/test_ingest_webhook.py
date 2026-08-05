"""Integration tests for POST /api/v1/webhooks/ghl (R7, ADR-0005).

Covers the auth surface (signature valid/invalid/missing, unconfigured 503),
idempotent replay for leads and consults, update-freshness on consults, and
org attribution (rows land in the destination location's org, visible to that
operator under RLS).
"""

import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text

from app.core.config import get_settings
from app.main import app
from tests.conftest import tenant_session, unique
from tests.integration.royalty_helpers import create_operator

pytestmark = pytest.mark.integration

WEBHOOK_SECRET = "integration-test-webhook-secret"
WEBHOOK_PATH = "/api/v1/webhooks/ghl"


@pytest.fixture
async def configured_secret() -> AsyncIterator[None]:
    """Serve real settings with the webhook secret set, via dependency override."""
    settings = get_settings().model_copy(update={"ghl_webhook_secret": WEBHOOK_SECRET})
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
async def unconfigured_secret() -> AsyncIterator[None]:
    settings = get_settings().model_copy(update={"ghl_webhook_secret": None})
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_settings, None)


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


async def _post(
    client: AsyncClient, payload: dict[str, Any], signature: str | None = None
) -> Response:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    headers["X-Webhook-Signature"] = signature if signature is not None else _sign(body)
    return await client.post(WEBHOOK_PATH, content=body, headers=headers)


def _contact_payload(location_id: uuid.UUID, source: str, external_id: str) -> dict[str, Any]:
    return {
        "event_type": "contact",
        "location_id": str(location_id),
        "contact": {
            "external_id": external_id,
            "source": source,
            "created_at": "2026-07-14T18:02:11Z",
        },
    }


def _appointment_payload(
    location_id: uuid.UUID,
    source: str,
    external_id: str,
    outcome: str | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    payload = _contact_payload(location_id, source, external_id)
    payload["event_type"] = "appointment"
    payload["appointment"] = {
        "external_id": f"appt-{external_id}",
        "scheduled_at": "2026-07-16T17:00:00Z",
        "occurred_at": occurred_at,
        "outcome": outcome,
    }
    return payload


async def _lead_rows(org_id: uuid.UUID, source: str) -> list[dict[str, Any]]:
    """Read back as the OWNING OPERATOR — also proves org attribution under RLS."""
    async with tenant_session(str(org_id), "operator") as s:
        rows = (
            await s.execute(
                text("SELECT id, external_id FROM leads WHERE source = :src"), {"src": source}
            )
        ).mappings()
        return [dict(r) for r in rows]


async def _consult_rows(org_id: uuid.UUID, source: str) -> list[dict[str, Any]]:
    async with tenant_session(str(org_id), "operator") as s:
        rows = (
            await s.execute(
                text(
                    "SELECT c.id, c.outcome, c.occurred_at FROM consults c"
                    " JOIN leads l ON l.id = c.lead_id WHERE l.source = :src"
                ),
                {"src": source},
            )
        ).mappings()
        return [dict(r) for r in rows]


async def test_missing_signature_is_401(client: AsyncClient, configured_secret: None) -> None:
    body = b"{}"
    resp = await client.post(
        WEBHOOK_PATH, content=body, headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_signature"


async def test_invalid_signature_is_401(client: AsyncClient, configured_secret: None) -> None:
    _, loc_id, _ = await create_operator()
    payload = _contact_payload(loc_id, unique("src"), unique("contact"))
    resp = await _post(client, payload, signature="0" * 64)
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_signature"


async def test_unconfigured_secret_is_503(client: AsyncClient, unconfigured_secret: None) -> None:
    resp = await client.post(
        WEBHOOK_PATH,
        content=b"{}",
        headers={"Content-Type": "application/json", "X-Webhook-Signature": "0" * 64},
    )
    assert resp.status_code == 503
    assert resp.json()["code"] == "webhook_not_configured"


async def test_contact_event_creates_lead_in_destination_org(
    client: AsyncClient, configured_secret: None
) -> None:
    org_id, loc_id, _ = await create_operator()
    source, external_id = unique("src"), unique("contact")

    resp = await _post(client, _contact_payload(loc_id, source, external_id))
    assert resp.status_code == 200
    assert resp.json() == {
        "lead_created": True,
        "consult_created": False,
        "consult_updated": False,
    }
    rows = await _lead_rows(org_id, source)
    assert [r["external_id"] for r in rows] == [external_id]


async def test_contact_replay_does_not_duplicate(
    client: AsyncClient, configured_secret: None
) -> None:
    org_id, loc_id, _ = await create_operator()
    source, external_id = unique("src"), unique("contact")
    payload = _contact_payload(loc_id, source, external_id)

    first = await _post(client, payload)
    replay = await _post(client, payload)
    assert first.json()["lead_created"] is True
    assert replay.json()["lead_created"] is False
    assert len(await _lead_rows(org_id, source)) == 1


async def test_appointment_event_creates_lead_and_consult(
    client: AsyncClient, configured_secret: None
) -> None:
    org_id, loc_id, _ = await create_operator()
    source, external_id = unique("src"), unique("contact")

    resp = await _post(client, _appointment_payload(loc_id, source, external_id))
    assert resp.status_code == 200
    assert resp.json() == {
        "lead_created": True,
        "consult_created": True,
        "consult_updated": False,
    }
    assert len(await _lead_rows(org_id, source)) == 1
    assert len(await _consult_rows(org_id, source)) == 1


async def test_appointment_replay_is_idempotent_and_updates_freshness(
    client: AsyncClient, configured_secret: None
) -> None:
    org_id, loc_id, _ = await create_operator()
    source, external_id = unique("src"), unique("contact")

    booked = _appointment_payload(loc_id, source, external_id)
    await _post(client, booked)

    # Exact replay: nothing created, nothing updated.
    replay = await _post(client, booked)
    assert replay.json() == {
        "lead_created": False,
        "consult_created": False,
        "consult_updated": False,
    }

    # Same appointment later reports an outcome: updated in place, not duplicated.
    completed = _appointment_payload(
        loc_id, source, external_id, outcome="sale", occurred_at="2026-07-16T17:05:00Z"
    )
    resp = await _post(client, completed)
    assert resp.json() == {
        "lead_created": False,
        "consult_created": False,
        "consult_updated": True,
    }
    consults = await _consult_rows(org_id, source)
    assert len(consults) == 1
    assert consults[0]["outcome"] == "sale"
    assert consults[0]["occurred_at"] is not None

    # A late replay of the outcome-less "booked" event must not erase the outcome.
    await _post(client, booked)
    consults = await _consult_rows(org_id, source)
    assert len(consults) == 1
    assert consults[0]["outcome"] == "sale"


async def test_unknown_location_is_400(client: AsyncClient, configured_secret: None) -> None:
    payload = _contact_payload(uuid.uuid4(), unique("src"), unique("contact"))
    resp = await _post(client, payload)
    assert resp.status_code == 400
    assert resp.json()["code"] == "unknown_location"


async def test_invalid_json_body_is_400(client: AsyncClient, configured_secret: None) -> None:
    body = b"not json at all"
    resp = await client.post(
        WEBHOOK_PATH,
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": _sign(body)},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_payload"


async def test_appointment_event_without_appointment_is_400(
    client: AsyncClient, configured_secret: None
) -> None:
    _, loc_id, _ = await create_operator()
    payload = _contact_payload(loc_id, unique("src"), unique("contact"))
    payload["event_type"] = "appointment"
    resp = await _post(client, payload)
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_payload"
