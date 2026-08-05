"""Supply endpoints: R6 expiry rule, invariant-1 translation, recall, RLS scoping."""

from datetime import date

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.security import Role, TokenClaims, mint_token
from tests.conftest import HQ_ORG_ID
from tests.integration.test_phase4_fixtures import build_supply_world

pytestmark = pytest.mark.integration


def _headers(settings: Settings, org_id: str, role: Role) -> dict[str, str]:
    token = mint_token(TokenClaims(sub="p4-user", org_id=org_id, role=role), settings)
    return {"Authorization": f"Bearer {token}"}


async def test_administering_expired_lot_is_rejected(
    client: AsyncClient, settings: Settings
) -> None:
    world = await build_supply_world(shipped=10, admins=0, lot_expiry=date(2026, 1, 1))
    resp = await client.post(
        "/api/v1/supply/administrations",
        json={
            "location_id": str(world["location_id"]),
            "lot_id": str(world["lot_id"]),
            "synthetic_patient_ref": "synthpt-expired-check",
        },
        headers=_headers(settings, str(world["org_id"]), "operator"),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "expired_lot"


async def test_administering_beyond_stock_translates_invariant_1(
    client: AsyncClient, settings: Settings
) -> None:
    world = await build_supply_world(shipped=1, admins=0)
    op = _headers(settings, str(world["org_id"]), "operator")
    body = {
        "location_id": str(world["location_id"]),
        "lot_id": str(world["lot_id"]),
        "synthetic_patient_ref": "synthpt-stock-check",
    }
    first = await client.post("/api/v1/supply/administrations", json=body, headers=op)
    assert first.status_code == 201
    second = await client.post("/api/v1/supply/administrations", json=body, headers=op)
    assert second.status_code == 409
    assert second.json()["code"] == "insufficient_stock"


async def test_recall_lists_every_administration_for_a_lot(
    client: AsyncClient, settings: Settings
) -> None:
    world = await build_supply_world(shipped=10, admins=3)
    resp = await client.get(
        f"/api/v1/supply/recall/{world['lot_id']}",
        headers=_headers(settings, HQ_ORG_ID, "hq_admin"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_administrations"] == 3
    assert all(r["synthetic_patient_ref"].startswith("synthpt") for r in body["rows"])


async def test_on_hand_is_rls_scoped_per_operator(client: AsyncClient, settings: Settings) -> None:
    world_a = await build_supply_world(shipped=5, admins=2)
    world_b = await build_supply_world(shipped=7, admins=0)

    a_view = await client.get(
        "/api/v1/supply/on-hand", headers=_headers(settings, str(world_a["org_id"]), "operator")
    )
    lots_a = {row["lot_id"] for row in a_view.json()}
    assert str(world_a["lot_id"]) in lots_a
    assert str(world_b["lot_id"]) not in lots_a

    hq_view = await client.get(
        "/api/v1/supply/on-hand", headers=_headers(settings, HQ_ORG_ID, "hq_admin")
    )
    lots_hq = {row["lot_id"] for row in hq_view.json()}
    assert {str(world_a["lot_id"]), str(world_b["lot_id"])} <= lots_hq

    balance_a = next(row for row in a_view.json() if row["lot_id"] == str(world_a["lot_id"]))
    assert balance_a["on_hand"] == 3  # 5 shipped - 2 administered


async def test_receive_and_ship_are_hq_only(client: AsyncClient, settings: Settings) -> None:
    world = await build_supply_world(shipped=0, admins=0)
    op = _headers(settings, str(world["org_id"]), "operator")
    hq = _headers(settings, HQ_ORG_ID, "hq_admin")

    receive_body = {
        "product_id": str(world["product_id"]),
        "lot_code": f"P4-RCV-{world['lot_id']}",
        "supplier": "P4 Supplier",
        "expiry": "2027-09-01",
    }
    assert (
        await client.post("/api/v1/supply/lots", json=receive_body, headers=op)
    ).status_code == 403
    received = await client.post("/api/v1/supply/lots", json=receive_body, headers=hq)
    assert received.status_code == 201

    ship_body = {
        "location_id": str(world["location_id"]),
        "lot_id": received.json()["id"],
        "qty": 4,
    }
    assert (
        await client.post("/api/v1/supply/shipments", json=ship_body, headers=op)
    ).status_code == 403
    assert (
        await client.post("/api/v1/supply/shipments", json=ship_body, headers=hq)
    ).status_code == 201
