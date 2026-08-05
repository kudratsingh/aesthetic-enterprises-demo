"""Variance reconciliation (R5): the seeded-underreporter mechanic, in miniature."""

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.security import TokenClaims, mint_token
from tests.conftest import HQ_ORG_ID
from tests.integration.test_phase4_fixtures import PERIOD, build_supply_world

pytestmark = pytest.mark.integration


def _headers(settings: Settings, org_id: str, role: str = "operator") -> dict[str, str]:
    token = mint_token(TokenClaims(sub="p4-user", org_id=org_id, role=role), settings)  # type: ignore[arg-type]
    return {"Authorization": f"Bearer {token}"}


async def test_underreporting_location_gets_flagged_with_the_math(
    client: AsyncClient, settings: Settings
) -> None:
    # 4 administrations; sales history is empty in this fixture so the ticket
    # model falls back to the stable seed value ($1,000) → floor $4,000.
    # Reported $1,000 → ratio 0.25 < 0.75 threshold.
    world = await build_supply_world(admins=4, reported_net_base=100_000)
    resp = await client.post(
        f"/api/v1/variance/compute?period={PERIOD.isoformat()}",
        headers=_headers(settings, HQ_ORG_ID, "hq_admin"),
    )
    assert resp.status_code == 200
    body = resp.json()
    flags = [f for f in body["flags"] if f["location_id"] == str(world["location_id"])]
    assert len(flags) == 1
    flag = flags[0]
    assert flag["expected_floor_cents"] == 4 * body["avg_net_ticket_cents"]
    assert flag["reported_net_base_cents"] == 100_000
    assert flag["administrations"] == 4
    assert flag["ratio"] < 0.75
    assert flag["status"] == "open"


async def test_honest_location_is_not_flagged(client: AsyncClient, settings: Settings) -> None:
    world = await build_supply_world(admins=4, reported_net_base=450_000)
    resp = await client.post(
        f"/api/v1/variance/compute?period={PERIOD.isoformat()}",
        headers=_headers(settings, HQ_ORG_ID, "hq_admin"),
    )
    assert resp.status_code == 200
    assert all(f["location_id"] != str(world["location_id"]) for f in resp.json()["flags"])


async def test_recompute_is_idempotent_and_preserves_review_status(
    client: AsyncClient, settings: Settings
) -> None:
    world = await build_supply_world(admins=4, reported_net_base=100_000)
    hq = _headers(settings, HQ_ORG_ID, "hq_admin")
    first = await client.post(f"/api/v1/variance/compute?period={PERIOD.isoformat()}", headers=hq)
    flag = next(f for f in first.json()["flags"] if f["location_id"] == str(world["location_id"]))

    resolve = await client.post(
        f"/api/v1/variance/flags/{flag['id']}/resolve",
        json={"status": "resolved", "reason": "operator provided bank statements"},
        headers=hq,
    )
    assert resolve.status_code == 200

    second = await client.post(f"/api/v1/variance/compute?period={PERIOD.isoformat()}", headers=hq)
    again = next(f for f in second.json()["flags"] if f["location_id"] == str(world["location_id"]))
    assert again["id"] == flag["id"]  # no duplicate flag
    assert again["status"] == "resolved"  # review outcome survives recompute


async def test_operator_sees_only_resolved_flags_for_own_org(
    client: AsyncClient, settings: Settings
) -> None:
    world = await build_supply_world(admins=4, reported_net_base=100_000)
    hq = _headers(settings, HQ_ORG_ID, "hq_admin")
    await client.post(f"/api/v1/variance/compute?period={PERIOD.isoformat()}", headers=hq)

    op = _headers(settings, str(world["org_id"]), "operator")
    open_view = await client.get("/api/v1/variance/flags", headers=op)
    assert open_view.status_code == 200
    assert open_view.json() == []  # own flag exists but is open, not resolved

    # Operators cannot compute or resolve.
    assert (
        await client.post(f"/api/v1/variance/compute?period={PERIOD.isoformat()}", headers=op)
    ).status_code == 403
