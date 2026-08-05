"""Shared fixture-builders for Phase 4 integration tests (new file — conftest is
shared surface and stays untouched)."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text

from tests.conftest import HQ_ORG_ID, tenant_session, unique

PERIOD = date(2026, 7, 1)
MID_PERIOD = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)


async def build_supply_world(
    *,
    shipped: int = 10,
    admins: int = 4,
    reported_net_base: int | None = None,
    lot_expiry: date = date(2027, 6, 1),
) -> dict[str, Any]:
    """One operator org with a location, a lot shipped to it, N administrations
    in PERIOD, and optionally a locked revenue report for PERIOD."""
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        org_id = (
            await s.execute(
                text(
                    "INSERT INTO orgs (id, kind, name)"
                    " VALUES (gen_random_uuid(), 'operator', :n) RETURNING id"
                ),
                {"n": unique("p4-org")},
            )
        ).scalar_one()
        loc_id = (
            await s.execute(
                text(
                    "INSERT INTO locations (id, org_id, name, activated_on)"
                    " VALUES (gen_random_uuid(), :org, :n, :d) RETURNING id"
                ),
                {"org": org_id, "n": unique("p4-loc"), "d": date(2026, 1, 1)},
            )
        ).scalar_one()
        product_id = (
            await s.execute(
                text(
                    "INSERT INTO products (id, sku, name, unit, price_cents)"
                    " VALUES (gen_random_uuid(), :sku, 'P4 Vial', 'vial', 50000) RETURNING id"
                ),
                {"sku": unique("p4-sku")},
            )
        ).scalar_one()
        lot_id = (
            await s.execute(
                text(
                    "INSERT INTO lots (id, product_id, lot_code, supplier, expiry)"
                    " VALUES (gen_random_uuid(), :p, :c, 'P4 Supplier', :e) RETURNING id"
                ),
                {"p": product_id, "c": unique("p4-lot"), "e": lot_expiry},
            )
        ).scalar_one()
        if shipped:
            await s.execute(
                text(
                    "INSERT INTO shipments (id, org_id, location_id, lot_id, qty, shipped_at)"
                    " VALUES (gen_random_uuid(), :org, :loc, :lot, :q, :t)"
                ),
                {"org": org_id, "loc": loc_id, "lot": lot_id, "q": shipped, "t": MID_PERIOD},
            )
        for _ in range(admins):
            await s.execute(
                text(
                    "INSERT INTO administrations (id, org_id, location_id, lot_id,"
                    " synthetic_patient_ref, qty, administered_at)"
                    " VALUES (gen_random_uuid(), :org, :loc, :lot, :ref, 1, :t)"
                ),
                {
                    "org": org_id,
                    "loc": loc_id,
                    "lot": lot_id,
                    "ref": unique("synthpt"),
                    "t": MID_PERIOD,
                },
            )
        if reported_net_base is not None:
            await s.execute(
                text(
                    "INSERT INTO revenue_reports (id, org_id, location_id, period,"
                    " gross_cents, refunds_cents, status)"
                    " VALUES (gen_random_uuid(), :org, :loc, :period, :gross, 0, 'locked')"
                ),
                {"org": org_id, "loc": loc_id, "period": PERIOD, "gross": reported_net_base},
            )
    return {"org_id": org_id, "location_id": loc_id, "lot_id": lot_id, "product_id": product_id}


def as_uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
