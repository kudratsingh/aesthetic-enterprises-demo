"""Phase 7 portal: onboarding completion, document vault, and the reorder flow
whose fulfillment lands in the real supply ledger."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import Settings
from app.core.security import Role, TokenClaims, mint_token
from app.services.portal import ONBOARDING_TEMPLATE
from tests.conftest import HQ_ORG_ID, tenant_session, unique
from tests.integration.test_phase4_fixtures import build_supply_world

pytestmark = pytest.mark.integration


def _headers(settings: Settings, org_id: str, role: Role) -> dict[str, str]:
    token = mint_token(TokenClaims(sub="portal-test", org_id=org_id, role=role), settings)
    return {"Authorization": f"Bearer {token}"}


async def _seed_tasks(org_id: str) -> list[str]:
    ids: list[str] = []
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        for sort_order, (title, category, due) in enumerate(ONBOARDING_TEMPLATE[:3]):
            tid = (
                await s.execute(
                    text(
                        "INSERT INTO onboarding_tasks (id, org_id, title, category,"
                        " sort_order, due_offset_days)"
                        " VALUES (gen_random_uuid(), :org, :t, :c, :s, :d) RETURNING id"
                    ),
                    {"org": org_id, "t": title, "c": category, "s": sort_order, "d": due},
                )
            ).scalar_one()
            ids.append(str(tid))
    return ids


async def test_operator_completes_own_onboarding_not_others(
    client: AsyncClient, settings: Settings
) -> None:
    world_a = await build_supply_world(shipped=0, admins=0)
    world_b = await build_supply_world(shipped=0, admins=0)
    tasks_a = await _seed_tasks(str(world_a["org_id"]))
    tasks_b = await _seed_tasks(str(world_b["org_id"]))

    op_a = _headers(settings, str(world_a["org_id"]), "operator")
    listing = await client.get("/api/v1/portal/onboarding", headers=op_a)
    listed_ids = {t["id"] for t in listing.json()}
    assert set(tasks_a) <= listed_ids
    assert not (set(tasks_b) & listed_ids)  # RLS: B's checklist invisible

    done = await client.post(f"/api/v1/portal/onboarding/{tasks_a[0]}/complete", headers=op_a)
    assert done.status_code == 200
    # completing another org's task: RLS hides the row → 404, not 403 leak
    foreign = await client.post(f"/api/v1/portal/onboarding/{tasks_b[0]}/complete", headers=op_a)
    assert foreign.status_code == 404

    again = await client.post(f"/api/v1/portal/onboarding/{tasks_a[0]}/complete", headers=op_a)
    assert again.status_code == 200  # idempotent
    refreshed = await client.get("/api/v1/portal/onboarding", headers=op_a)
    row = next(t for t in refreshed.json() if t["id"] == tasks_a[0])
    assert row["completed_at"] is not None


async def test_document_vault_is_org_scoped(client: AsyncClient, settings: Settings) -> None:
    world_a = await build_supply_world(shipped=0, admins=0)
    world_b = await build_supply_world(shipped=0, admins=0)
    op_a = _headers(settings, str(world_a["org_id"]), "operator")
    op_b = _headers(settings, str(world_b["org_id"]), "operator")

    title = unique("doc")
    created = await client.post(
        "/api/v1/portal/documents",
        json={"title": title, "category": "policy", "body": "synthetic body"},
        headers=op_a,
    )
    assert created.status_code == 201

    mine = await client.get("/api/v1/portal/documents", headers=op_a)
    assert any(d["title"] == title for d in mine.json())
    theirs = await client.get("/api/v1/portal/documents", headers=op_b)
    assert not any(d["title"] == title for d in theirs.json())


async def test_reorder_flow_end_to_end_lands_in_supply_ledger(
    client: AsyncClient, settings: Settings
) -> None:
    """Phase 7 exit: operator places an order end-to-end; HQ fulfillment creates
    real shipments so on-hand increases through the ledger triggers."""
    world = await build_supply_world(shipped=0, admins=0)
    op = _headers(settings, str(world["org_id"]), "operator")
    hq = _headers(settings, HQ_ORG_ID, "hq_admin")

    order = await client.post(
        "/api/v1/portal/orders",
        json={
            "location_id": str(world["location_id"]),
            "lines": [{"product_id": str(world["product_id"]), "qty": 12}],
        },
        headers=op,
    )
    assert order.status_code == 201
    order_id = order.json()["id"]
    assert order.json()["status"] == "draft"

    submitted = await client.post(f"/api/v1/portal/orders/{order_id}/submit", headers=op)
    assert submitted.json()["status"] == "submitted"
    # double-submit refused
    assert (
        await client.post(f"/api/v1/portal/orders/{order_id}/submit", headers=op)
    ).status_code == 409

    # operator cannot fulfill; HQ can
    fulfill_body = {
        "assignments": [{"product_id": str(world["product_id"]), "lot_id": str(world["lot_id"])}]
    }
    assert (
        await client.post(
            f"/api/v1/portal/orders/{order_id}/fulfill", json=fulfill_body, headers=op
        )
    ).status_code == 403
    fulfilled = await client.post(
        f"/api/v1/portal/orders/{order_id}/fulfill", json=fulfill_body, headers=hq
    )
    assert fulfilled.status_code == 200
    assert fulfilled.json()["status"] == "fulfilled"

    on_hand = await client.get("/api/v1/supply/on-hand", headers=op)
    row = next(r for r in on_hand.json() if r["lot_id"] == str(world["lot_id"]))
    assert row["on_hand"] == 12  # the ledger, not the order, holds the truth


async def test_fulfill_rejects_wrong_product_lot(client: AsyncClient, settings: Settings) -> None:
    world = await build_supply_world(shipped=0, admins=0)
    other = await build_supply_world(shipped=0, admins=0)  # different product+lot
    op = _headers(settings, str(world["org_id"]), "operator")
    hq = _headers(settings, HQ_ORG_ID, "hq_admin")

    order = await client.post(
        "/api/v1/portal/orders",
        json={
            "location_id": str(world["location_id"]),
            "lines": [{"product_id": str(world["product_id"]), "qty": 3}],
        },
        headers=op,
    )
    order_id = order.json()["id"]
    await client.post(f"/api/v1/portal/orders/{order_id}/submit", headers=op)

    mismatch = await client.post(
        f"/api/v1/portal/orders/{order_id}/fulfill",
        json={
            "assignments": [
                {"product_id": str(world["product_id"]), "lot_id": str(other["lot_id"])}
            ]
        },
        headers=hq,
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "lot_product_mismatch"
