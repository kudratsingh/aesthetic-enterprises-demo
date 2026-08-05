"""Phase 2 exit criterion: the full royalty cycle is executable via API alone.

Drives report draft -> attest/lock -> HQ run -> invoices -> aging entirely over
HTTP, plus role gating (403s) and RLS scoping of what each tenant can see.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.security import Role, TokenClaims, mint_token
from tests.integration.royalty_helpers import create_operator, unique_period

pytestmark = pytest.mark.integration


def _token(settings: Settings, org_id: uuid.UUID, user_id: uuid.UUID, role: Role) -> str:
    claims = TokenClaims(sub=str(user_id), org_id=str(org_id), role=role)
    return mint_token(claims, settings)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_full_royalty_cycle_via_api(
    client: AsyncClient, settings: Settings, hq_token: str
) -> None:
    org_a, loc_a, user_a = await create_operator()
    org_b, loc_b, user_b = await create_operator()
    period = unique_period()
    tok_a = _token(settings, org_a, user_a, "operator")
    tok_b = _token(settings, org_b, user_b, "operator")

    # Operator A drafts, edits, and attests a month.
    resp = await client.post(
        "/api/v1/royalty/reports",
        json={
            "location_id": str(loc_a),
            "period": period.isoformat(),
            "gross_cents": 1_500_000,
            "refunds_cents": 0,
        },
        headers=_auth(tok_a),
    )
    assert resp.status_code == 201
    report_a = resp.json()
    assert report_a["status"] == "draft"

    resp = await client.patch(
        f"/api/v1/royalty/reports/{report_a['id']}",
        json={"gross_cents": 2_100_000, "refunds_cents": 100_000},
        headers=_auth(tok_a),
    )
    assert resp.status_code == 200
    assert resp.json()["net_base_cents"] == 2_000_000

    resp = await client.post(
        f"/api/v1/royalty/reports/{report_a['id']}/submit", headers=_auth(tok_a)
    )
    assert resp.status_code == 200
    locked = resp.json()
    assert locked["status"] == "locked"
    assert locked["attested_by"] == str(user_a)
    assert locked["attested_at"] is not None

    # Editing after lock is a typed 409; the correction path is the way out.
    resp = await client.patch(
        f"/api/v1/royalty/reports/{report_a['id']}",
        json={"gross_cents": 1, "refunds_cents": 0},
        headers=_auth(tok_a),
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "report_locked"

    # Operator B locks its month too.
    resp = await client.post(
        "/api/v1/royalty/reports",
        json={
            "location_id": str(loc_b),
            "period": period.isoformat(),
            "gross_cents": 1_000_000,
            "refunds_cents": 0,
        },
        headers=_auth(tok_b),
    )
    report_b = resp.json()
    resp = await client.post(
        f"/api/v1/royalty/reports/{report_b['id']}/submit", headers=_auth(tok_b)
    )
    assert resp.status_code == 200

    # HQ runs the period; both locations appear as line items.
    resp = await client.post(
        "/api/v1/royalty/runs", json={"period": period.isoformat()}, headers=_auth(hq_token)
    )
    assert resp.status_code == 201
    run = resp.json()
    assert run["reused"] is False
    amounts = {li["location_id"]: li["amount_due_cents"] for li in run["line_items"]}
    assert amounts[str(loc_a)] == 140_000  # 7% of 2,000,000
    assert amounts[str(loc_b)] == 70_000  # 7% of 1,000,000

    # Operators only ever see their own line items (RLS, not code branches).
    resp = await client.get(f"/api/v1/royalty/runs/{run['id']}/line-items", headers=_auth(tok_a))
    assert resp.status_code == 200
    assert {li["org_id"] for li in resp.json()} == {str(org_a)}

    # HQ issues invoices: one per (run, org), net-30.
    resp = await client.post(f"/api/v1/royalty/runs/{run['id']}/invoices", headers=_auth(hq_token))
    assert resp.status_code == 201
    invoices = resp.json()["invoices"]
    by_org = {inv["org_id"]: inv for inv in invoices}
    assert by_org[str(org_a)]["amount_due_cents"] == 140_000
    assert by_org[str(org_b)]["amount_due_cents"] == 70_000
    assert all(inv["status"] == "issued" for inv in invoices)

    # Operator sees only its own invoice.
    resp = await client.get(f"/api/v1/royalty/invoices?run_id={run['id']}", headers=_auth(tok_b))
    assert resp.status_code == 200
    assert [inv["org_id"] for inv in resp.json()] == [str(org_b)]

    # Fresh invoices land in the 0-30 aging bucket for HQ.
    resp = await client.get("/api/v1/royalty/invoices/aging", headers=_auth(hq_token))
    assert resp.status_code == 200
    aging = resp.json()
    ours = [inv for inv in aging["invoices"] if inv["org_id"] in {str(org_a), str(org_b)}]
    assert len(ours) == 2
    assert all(inv["bucket"] == "0-30" for inv in ours)
    assert aging["buckets"][0]["bucket"] == "0-30"


async def test_royalty_role_gating_and_tenancy(
    client: AsyncClient, settings: Settings, hq_token: str
) -> None:
    org_a, loc_a, user_a = await create_operator()
    org_b, _, user_b = await create_operator()
    period = unique_period()
    tok_a = _token(settings, org_a, user_a, "operator")
    tok_b = _token(settings, org_b, user_b, "operator")
    tok_staff = _token(settings, org_a, user_a, "clinic_staff")

    # Operators cannot run periods, issue invoices, or read aging (HQ-only).
    resp = await client.post(
        "/api/v1/royalty/runs", json={"period": period.isoformat()}, headers=_auth(tok_a)
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "role_forbidden"
    resp = await client.get("/api/v1/royalty/invoices/aging", headers=_auth(tok_a))
    assert resp.status_code == 403

    # clinic_staff cannot submit revenue reports (permissions matrix).
    resp = await client.post(
        "/api/v1/royalty/reports",
        json={
            "location_id": str(loc_a),
            "period": period.isoformat(),
            "gross_cents": 1,
            "refunds_cents": 0,
        },
        headers=_auth(tok_staff),
    )
    assert resp.status_code == 403

    # HQ cannot author operator reports either — attestation is the operator's.
    resp = await client.post(
        "/api/v1/royalty/reports",
        json={
            "location_id": str(loc_a),
            "period": period.isoformat(),
            "gross_cents": 1,
            "refunds_cents": 0,
        },
        headers=_auth(hq_token),
    )
    assert resp.status_code == 403

    # Another org's location is invisible: creating against it 404s (RLS).
    resp = await client.post(
        "/api/v1/royalty/reports",
        json={
            "location_id": str(loc_a),
            "period": period.isoformat(),
            "gross_cents": 1,
            "refunds_cents": 0,
        },
        headers=_auth(tok_b),
    )
    assert resp.status_code == 404

    # B cannot touch A's report: invisible rows read as 404, never 403.
    resp = await client.post(
        "/api/v1/royalty/reports",
        json={
            "location_id": str(loc_a),
            "period": period.isoformat(),
            "gross_cents": 500_000,
            "refunds_cents": 0,
        },
        headers=_auth(tok_a),
    )
    report_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/royalty/reports/{report_id}/submit", headers=_auth(tok_b))
    assert resp.status_code == 404

    # A period that isn't the first of a month is rejected at validation.
    resp = await client.post(
        "/api/v1/royalty/reports",
        json={
            "location_id": str(loc_a),
            "period": period.replace(day=15).isoformat(),
            "gross_cents": 1,
            "refunds_cents": 0,
        },
        headers=_auth(tok_a),
    )
    assert resp.status_code == 422
