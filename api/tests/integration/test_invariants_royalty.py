"""Named invariant tests per CLAUDE.md §2.5. Phase 2 covers invariants 2, 3, 4, 6.

Each test drives the real service layer inside tenant-scoped sessions (RLS on),
and invariant 2 is additionally proven at the database: the lock trigger rejects
raw SQL mutation even from HQ.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.errors import InvoiceStateError, ReportLockedError
from app.services import royalty
from tests.conftest import HQ_ORG_ID, tenant_session
from tests.integration.royalty_helpers import (
    HQ_ACTOR,
    create_operator,
    lock_report,
    operator_actor,
    unique_period,
)

pytestmark = pytest.mark.integration


async def test_a_locked_revenue_report_is_immutable_corrections_create_a_new_report_version() -> (
    None
):
    """Invariant 2: service raises ReportLockedError, the DB trigger blocks raw
    SQL (even HQ), and the correction path never touches the locked row."""
    org_id, loc_id, user_id = await create_operator()
    period = unique_period()
    actor = operator_actor(org_id, user_id)
    locked = await lock_report(org_id, loc_id, user_id, period, gross_cents=1_000_000)
    assert locked.status == "locked"
    assert locked.attested_by == user_id
    assert locked.attested_at is not None

    # Service layer: typed error on any mutation attempt.
    with pytest.raises(ReportLockedError):
        async with tenant_session(str(org_id), "operator") as s:
            await royalty.update_report(s, actor, locked.id, 1, 0)
    with pytest.raises(ReportLockedError):
        async with tenant_session(str(org_id), "operator") as s:
            await royalty.submit_report(s, actor, locked.id)

    # Database layer: the trigger rejects raw UPDATE/DELETE — even from HQ.
    for stmt in (
        "UPDATE revenue_reports SET gross_cents = 1 WHERE id = :id",
        "UPDATE revenue_reports SET status = 'draft' WHERE id = :id",
        "DELETE FROM revenue_reports WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="immutable"):
            async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
                await s.execute(text(stmt), {"id": locked.id})

    # Correction: a NEW draft version linked via supersedes; original untouched.
    async with tenant_session(str(org_id), "operator") as s:
        correction = await royalty.create_correction(s, actor, locked.id)
    assert correction.id != locked.id
    assert correction.status == "draft"
    assert correction.supersedes == locked.id
    assert correction.gross_cents == locked.gross_cents

    async with tenant_session(str(org_id), "operator") as s:
        await royalty.update_report(s, actor, correction.id, 900_000, 0)
    async with tenant_session(str(org_id), "operator") as s:
        corrected = await royalty.submit_report(s, actor, correction.id)
    assert corrected.status == "locked"

    async with tenant_session(str(org_id), "operator") as s:
        original = (
            await s.execute(
                text("SELECT gross_cents, status FROM revenue_reports WHERE id = :id"),
                {"id": locked.id},
            )
        ).one()
    assert original.gross_cents == 1_000_000
    assert original.status == "locked"


async def test_run_royalty_period_is_idempotent_per_period_inputs_and_versioned() -> None:
    """Invariant 3: identical inputs return the existing run; changed inputs
    create version N+1; prior versions are never mutated."""
    org_a, loc_a, user_a = await create_operator(royalty_rate="0.0700")
    org_b, loc_b, user_b = await create_operator(royalty_rate="0.0500")
    period = unique_period()
    report_a = await lock_report(
        org_a, loc_a, user_a, period, gross_cents=2_000_000, refunds_cents=100_000
    )
    await lock_report(org_b, loc_b, user_b, period, gross_cents=3_000_000)

    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        run1 = await royalty.run_royalty_period(s, HQ_ACTOR, period)
    assert run1.reused is False
    by_loc = {li.location_id: li for li in run1.line_items}
    assert by_loc[loc_a].amount_due_cents == 133_000  # 7% of 1,900,000
    assert by_loc[loc_b].amount_due_cents == 150_000  # 5% of 3,000,000

    # Rerun with identical inputs: the SAME run version comes back untouched.
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        run2 = await royalty.run_royalty_period(s, HQ_ACTOR, period)
    assert run2.reused is True
    assert run2.id == run1.id
    assert run2.version == run1.version
    assert run2.input_fingerprint == run1.input_fingerprint

    # Change the inputs: correct A's report and lock the correction.
    actor_a = operator_actor(org_a, user_a)
    async with tenant_session(str(org_a), "operator") as s:
        correction = await royalty.create_correction(s, actor_a, report_a.id)
    async with tenant_session(str(org_a), "operator") as s:
        await royalty.update_report(s, actor_a, correction.id, 2_500_000, 100_000)
    async with tenant_session(str(org_a), "operator") as s:
        await royalty.submit_report(s, actor_a, correction.id)

    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        run3 = await royalty.run_royalty_period(s, HQ_ACTOR, period)
    assert run3.reused is False
    assert run3.id != run1.id
    assert run3.version == run1.version + 1
    assert run3.input_fingerprint != run1.input_fingerprint
    by_loc3 = {li.location_id: li for li in run3.line_items}
    assert by_loc3[loc_a].amount_due_cents == 168_000  # 7% of 2,400,000
    assert by_loc3[loc_a].id != by_loc[loc_a].id  # line items belong to one version

    # Prior version is never mutated: row and line items are byte-identical.
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        stored = (
            await s.execute(
                text(
                    "SELECT version, input_fingerprint FROM royalty_runs WHERE id = :id",
                ),
                {"id": run1.id},
            )
        ).one()
        stored_items = (
            await s.execute(
                text(
                    "SELECT location_id, amount_due_cents FROM royalty_line_items"
                    " WHERE run_id = :id ORDER BY location_id"
                ),
                {"id": run1.id},
            )
        ).all()
    assert stored.version == run1.version
    assert stored.input_fingerprint == run1.input_fingerprint
    assert {(row.location_id, row.amount_due_cents) for row in stored_items} == {
        (li.location_id, li.amount_due_cents) for li in run1.line_items
    }


async def test_minimum_royalty_applies_when_seven_percent_of_base_below_monthly_minimum() -> None:
    """Invariant 4: the monthly minimum is the floor when rate x base is under it."""
    org_low, loc_low, user_low = await create_operator(monthly_minimum_cents=200_000)
    org_high, loc_high, user_high = await create_operator(monthly_minimum_cents=200_000)
    period = unique_period()
    # 7% of 1,000,000 = 70,000 < 200,000 minimum -> floor binds.
    await lock_report(org_low, loc_low, user_low, period, gross_cents=1_000_000)
    # 7% of 10,000,000 = 700,000 > 200,000 minimum -> percentage wins.
    await lock_report(org_high, loc_high, user_high, period, gross_cents=10_000_000)

    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        run = await royalty.run_royalty_period(s, HQ_ACTOR, period)
    by_loc = {li.location_id: li for li in run.line_items}

    assert by_loc[loc_low].amount_due_cents == 200_000
    assert by_loc[loc_low].minimum_applied is True
    assert by_loc[loc_high].amount_due_cents == 700_000
    assert by_loc[loc_high].minimum_applied is False


async def test_invoices_reference_exactly_one_royalty_run_version_regeneration_supersedes() -> None:
    """Invariant 6: an invoice references exactly one run version; regeneration
    supersedes prior invoices (superseded_by) and never edits them."""
    org_id, loc_id, user_id = await create_operator()
    period = unique_period()
    report = await lock_report(org_id, loc_id, user_id, period, gross_cents=2_000_000)

    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        run1 = await royalty.run_royalty_period(s, HQ_ACTOR, period)
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        issued1 = await royalty.issue_invoices(s, HQ_ACTOR, run1.id)
    assert issued1.reused is False
    inv1 = next(inv for inv in issued1.invoices if inv.org_id == org_id)
    assert inv1.run_id == run1.id
    assert inv1.amount_due_cents == 140_000  # 7% of 2,000,000

    # Reissuing for the same run is idempotent — same rows, no edits.
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        again = await royalty.issue_invoices(s, HQ_ACTOR, run1.id)
    assert again.reused is True
    assert {inv.id for inv in again.invoices} == {inv.id for inv in issued1.invoices}

    # Corrected inputs -> new run version -> regeneration supersedes.
    actor = operator_actor(org_id, user_id)
    async with tenant_session(str(org_id), "operator") as s:
        correction = await royalty.create_correction(s, actor, report.id)
    async with tenant_session(str(org_id), "operator") as s:
        await royalty.update_report(s, actor, correction.id, 3_000_000, 0)
    async with tenant_session(str(org_id), "operator") as s:
        await royalty.submit_report(s, actor, correction.id)
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        run2 = await royalty.run_royalty_period(s, HQ_ACTOR, period)
    assert run2.version == run1.version + 1

    # Until regeneration, v1's invoices remain the live ones (idempotent reuse).
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        still_live = await royalty.issue_invoices(s, HQ_ACTOR, run1.id)
    assert still_live.reused is True

    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        issued2 = await royalty.issue_invoices(s, HQ_ACTOR, run2.id)
    inv2 = next(inv for inv in issued2.invoices if inv.org_id == org_id)
    assert inv2.run_id == run2.id
    assert inv2.amount_due_cents == 210_000  # 7% of 3,000,000

    # Once superseded, a stale run version can never be re-invoiced.
    with pytest.raises(InvoiceStateError):
        async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
            await royalty.issue_invoices(s, HQ_ACTOR, run1.id)

    # The old invoice is superseded, not edited: figures and run ref unchanged.
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        old = (
            await s.execute(
                text(
                    "SELECT run_id, amount_due_cents, status, superseded_by"
                    " FROM invoices WHERE id = :id"
                ),
                {"id": inv1.id},
            )
        ).one()
    assert old.run_id == run1.id
    assert old.amount_due_cents == 140_000
    assert old.status == "issued"
    assert old.superseded_by == inv2.id
