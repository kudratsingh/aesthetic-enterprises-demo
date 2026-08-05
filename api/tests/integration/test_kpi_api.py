"""KPI endpoints: aggregation shape, ramp targets, HQ-only gating."""

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.security import TokenClaims, mint_token
from tests.conftest import HQ_ORG_ID
from tests.integration.test_phase4_fixtures import PERIOD, build_supply_world

pytestmark = pytest.mark.integration


def _hq(settings: Settings) -> dict[str, str]:
    token = mint_token(TokenClaims(sub="p4-kpi", org_id=HQ_ORG_ID, role="hq_admin"), settings)
    return {"Authorization": f"Bearer {token}"}


async def test_location_kpis_report_target_and_attainment(
    client: AsyncClient, settings: Settings
) -> None:
    world = await build_supply_world(admins=0, reported_net_base=500_000)
    resp = await client.get(
        f"/api/v1/kpi/locations?period={PERIOD.isoformat()}", headers=_hq(settings)
    )
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["location_id"] == str(world["location_id"]))
    # activated 2026-01-01 → 7 months active in July → ramp 0.3 + 7*0.06 = 0.72
    assert row["months_active"] == 7
    assert row["target_treatments"] == 20  # round(28 * 0.72)
    assert row["reported_net_base_cents"] == 500_000
    assert row["attainment"] == 0.0  # fixture completed no treatments


async def test_kpi_endpoints_are_hq_only(client: AsyncClient, settings: Settings) -> None:
    world = await build_supply_world(admins=0)
    op_token = mint_token(
        TokenClaims(sub="p4-op", org_id=str(world["org_id"]), role="operator"), settings
    )
    op = {"Authorization": f"Bearer {op_token}"}
    assert (await client.get("/api/v1/kpi/network", headers=op)).status_code == 403
    assert (
        await client.get(f"/api/v1/kpi/locations?period={PERIOD.isoformat()}", headers=op)
    ).status_code == 403


async def test_network_kpis_return_per_period_rows(client: AsyncClient, settings: Settings) -> None:
    await build_supply_world(admins=2, reported_net_base=300_000)
    resp = await client.get("/api/v1/kpi/network?months=12", headers=_hq(settings))
    assert resp.status_code == 200
    rows = resp.json()
    assert rows, "expected at least one period row"
    july = next((r for r in rows if r["period"] == PERIOD.isoformat()), None)
    assert july is not None
    assert july["reported_net_base_cents"] >= 300_000
