"""Named invariant tests per CLAUDE.md §2.5. Phase 1 covers invariants 1 and 5."""

import uuid
from datetime import UTC, date, datetime
from typing import Any, cast

import pytest
from sqlalchemy import CursorResult, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from tests.conftest import HQ_ORG_ID, plain_session, tenant_session, unique

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


async def _create_org_with_location(kind: str = "operator") -> tuple[uuid.UUID, uuid.UUID]:
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        org_id = (
            await s.execute(
                text(
                    "INSERT INTO orgs (id, kind, name)"
                    " VALUES (gen_random_uuid(), :k, :n) RETURNING id"
                ),
                {"k": kind, "n": unique("org")},
            )
        ).scalar_one()
        loc_id = (
            await s.execute(
                text(
                    "INSERT INTO locations (id, org_id, name, activated_on)"
                    " VALUES (gen_random_uuid(), :org, :n, :d) RETURNING id"
                ),
                {"org": org_id, "n": unique("loc"), "d": date(2026, 1, 1)},
            )
        ).scalar_one()
    return org_id, loc_id


async def _create_lot() -> uuid.UUID:
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        product_id = (
            await s.execute(
                text(
                    "INSERT INTO products (id, sku, name, unit, price_cents)"
                    " VALUES (gen_random_uuid(), :sku, 'Test Vial', 'vial', 45000) RETURNING id"
                ),
                {"sku": unique("sku")},
            )
        ).scalar_one()
        lot_id: uuid.UUID = (
            await s.execute(
                text(
                    "INSERT INTO lots (id, product_id, lot_code, supplier, expiry)"
                    " VALUES (gen_random_uuid(), :p, :c, 'Test Supplier', :e) RETURNING id"
                ),
                {"p": product_id, "c": unique("lot"), "e": date(2027, 1, 1)},
            )
        ).scalar_one()
        return lot_id


async def _ship(org_id: uuid.UUID, loc_id: uuid.UUID, lot_id: uuid.UUID, qty: int) -> None:
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        await s.execute(
            text(
                "INSERT INTO shipments (id, org_id, location_id, lot_id, qty, shipped_at)"
                " VALUES (gen_random_uuid(), :org, :loc, :lot, :q, :t)"
            ),
            {"org": org_id, "loc": loc_id, "lot": lot_id, "q": qty, "t": NOW},
        )


async def _administer(org_id: uuid.UUID, loc_id: uuid.UUID, lot_id: uuid.UUID, qty: int) -> None:
    async with tenant_session(str(org_id), "operator") as s:
        await s.execute(
            text(
                "INSERT INTO administrations"
                " (id, org_id, location_id, lot_id, synthetic_patient_ref, qty, administered_at)"
                " VALUES (gen_random_uuid(), :org, :loc, :lot, :ref, :q, :t)"
            ),
            {"org": org_id, "loc": loc_id, "lot": lot_id, "ref": unique("pt"), "q": qty, "t": NOW},
        )


async def test_administrations_ledger_cannot_drive_location_on_hand_negative() -> None:
    """Invariant 1: DB-enforced via trigger-maintained balance + CHECK."""
    org_id, loc_id = await _create_org_with_location()
    lot_id = await _create_lot()
    await _ship(org_id, loc_id, lot_id, 5)

    # More than on-hand in one go → CHECK rejects.
    with pytest.raises(IntegrityError, match="ck_on_hand_non_negative"):
        await _administer(org_id, loc_id, lot_id, 6)

    # Draining exactly is fine; one more unit is not.
    await _administer(org_id, loc_id, lot_id, 5)
    with pytest.raises(IntegrityError, match="ck_on_hand_non_negative"):
        await _administer(org_id, loc_id, lot_id, 1)

    async with tenant_session(str(org_id), "operator") as s:
        on_hand = (
            await s.execute(
                text(
                    "SELECT on_hand FROM location_lot_on_hand"
                    " WHERE location_id = :loc AND lot_id = :lot"
                ),
                {"loc": loc_id, "lot": lot_id},
            )
        ).scalar_one()
    assert on_hand == 0


async def test_ledger_rows_are_append_only() -> None:
    """ADR-0003: updates/deletes on ledger tables are trigger-rejected."""
    org_id, loc_id = await _create_org_with_location()
    lot_id = await _create_lot()
    await _ship(org_id, loc_id, lot_id, 3)

    with pytest.raises(DBAPIError, match="append-only"):
        async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
            await s.execute(
                text("UPDATE shipments SET qty = 99 WHERE location_id = :loc"), {"loc": loc_id}
            )
    with pytest.raises(DBAPIError, match="append-only"):
        async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
            await s.execute(text("DELETE FROM shipments WHERE location_id = :loc"), {"loc": loc_id})


async def test_operator_cannot_read_or_write_another_orgs_rows() -> None:
    """Invariant 5: RLS isolation between two seeded operators."""
    org_a, loc_a = await _create_org_with_location()
    org_b, loc_b = await _create_org_with_location()

    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        for org, loc in ((org_a, loc_a), (org_b, loc_b)):
            await s.execute(
                text(
                    "INSERT INTO leads (id, org_id, location_id, source)"
                    " VALUES (gen_random_uuid(), :org, :loc, 'seed')"
                ),
                {"org": org, "loc": loc},
            )

    # A reads: only A's rows visible, across tables.
    async with tenant_session(str(org_a), "operator") as s:
        lead_orgs = (
            (
                await s.execute(
                    text("SELECT DISTINCT org_id FROM leads WHERE org_id IN (:a, :b)").bindparams(
                        a=org_a, b=org_b
                    )
                )
            )
            .scalars()
            .all()
        )
        assert lead_orgs == [org_a]
        loc_rows = (
            (
                await s.execute(
                    text("SELECT id FROM locations WHERE id IN (:la, :lb)").bindparams(
                        la=loc_a, lb=loc_b
                    )
                )
            )
            .scalars()
            .all()
        )
        assert loc_rows == [loc_a]
        org_rows = (
            (
                await s.execute(
                    text("SELECT id FROM orgs WHERE id IN (:a, :b)").bindparams(a=org_a, b=org_b)
                )
            )
            .scalars()
            .all()
        )
        assert org_rows == [org_a]

    # A writes into B: INSERT rejected by policy WITH CHECK.
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with tenant_session(str(org_a), "operator") as s:
            await s.execute(
                text(
                    "INSERT INTO leads (id, org_id, location_id, source)"
                    " VALUES (gen_random_uuid(), :org, :loc, 'intrusion')"
                ),
                {"org": org_b, "loc": loc_b},
            )

    # A updating/deleting B rows: policies filter them out — zero rows affected.
    async with tenant_session(str(org_a), "operator") as s:
        updated = cast(
            CursorResult[Any],
            await s.execute(
                text("UPDATE locations SET name = 'hacked' WHERE id = :loc"), {"loc": loc_b}
            ),
        )
        assert updated.rowcount == 0
        deleted = cast(
            CursorResult[Any],
            await s.execute(text("DELETE FROM leads WHERE org_id = :org"), {"org": org_b}),
        )
        assert deleted.rowcount == 0

    # HQ sees both orgs (policy-level bypass, not a code branch).
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        both = (
            await s.execute(
                text("SELECT count(*) FROM orgs WHERE id IN (:a, :b)").bindparams(a=org_a, b=org_b)
            )
        ).scalar_one()
        assert both == 2


async def test_unauthenticated_context_sees_nothing() -> None:
    """No app.org_id/app.role set → every policy evaluates false."""
    org_a, _ = await _create_org_with_location()
    async with plain_session() as s:
        rows = (await s.execute(text("SELECT id FROM orgs WHERE id = :a"), {"a": org_a})).all()
        assert rows == []
