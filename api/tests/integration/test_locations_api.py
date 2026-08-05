import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.security import TokenClaims, mint_token
from tests.conftest import HQ_ORG_ID
from tests.integration.test_phase4_fixtures import build_supply_world

pytestmark = pytest.mark.integration


async def test_locations_list_is_rls_scoped(client: AsyncClient, settings: Settings) -> None:
    world_a = await build_supply_world(shipped=0, admins=0)
    world_b = await build_supply_world(shipped=0, admins=0)

    op_token = mint_token(
        TokenClaims(sub="loc-test", org_id=str(world_a["org_id"]), role="operator"), settings
    )
    mine = await client.get("/api/v1/locations", headers={"Authorization": f"Bearer {op_token}"})
    assert mine.status_code == 200
    ids = {row["id"] for row in mine.json()}
    assert str(world_a["location_id"]) in ids
    assert str(world_b["location_id"]) not in ids

    hq_token = mint_token(TokenClaims(sub="loc-test", org_id=HQ_ORG_ID, role="hq_admin"), settings)
    all_locs = await client.get(
        "/api/v1/locations", headers={"Authorization": f"Bearer {hq_token}"}
    )
    all_ids = {row["id"] for row in all_locs.json()}
    assert {str(world_a["location_id"]), str(world_b["location_id"])} <= all_ids
