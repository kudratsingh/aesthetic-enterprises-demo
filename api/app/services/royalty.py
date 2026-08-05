"""Royalty domain core (Phase 2): revenue report lifecycle (R3), versioned
idempotent royalty runs (R1/R4, ADR-0004), invoice issuance and aging.

Every function takes the request's tenant-scoped session (RLS is the tenancy
boundary; role checks here implement the permissions matrix on top of it) and
raises typed domain errors that main.py translates to HTTP.
"""

import calendar
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import (
    InvoiceStateError,
    NotFoundError,
    ReportLockedError,
    ReportStateError,
    RoleForbiddenError,
)
from app.core.security import TokenClaims
from app.db.models import (
    Invoice,
    LicenseAgreement,
    Location,
    Org,
    RevenueReport,
    RoyaltyLineItem,
    RoyaltyRun,
    RoyaltyRunExclusion,
)
from app.db.models.base import utcnow
from app.schemas.royalty import (
    AgingBucketName,
    AgingBucketOut,
    AgingInvoiceOut,
    AgingOut,
    InvoiceOut,
    IssueInvoicesOut,
    RevenueReportOut,
    RoyaltyLineItemOut,
    RoyaltyRunOut,
    RoyaltyRunSummaryOut,
    RunExclusionOut,
)

# Exclusion reasons recorded on a run (policy A3; ADR-0004).
EXCLUDED_NO_LOCKED_REPORT = "no_locked_report"
EXCLUDED_NO_ACTIVE_AGREEMENT = "no_active_agreement"


def _require_role(actor: TokenClaims, *roles: str) -> None:
    if actor.role not in roles:
        raise RoleForbiddenError(f"role '{actor.role}' may not perform this operation")


def _actor_user_id(actor: TokenClaims) -> uuid.UUID:
    try:
        return uuid.UUID(actor.sub)
    except ValueError as exc:
        raise RoleForbiddenError("attestation requires a real user identity") from exc


# ---------------------------------------------------------------------------
# Pure royalty math (unit-tested directly; see tests/unit/test_royalty_math.py)
# ---------------------------------------------------------------------------


def round_half_up_cents(value: Decimal) -> int:
    """Round to integer cents, half away from zero upward (PROJECT_CONTEXT §4)."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def prorated_minimum_cents(
    monthly_minimum_cents: int, active_days: int, days_in_period: int
) -> int:
    """R1: mid-period activation prorates the minimum by active days ÷ days in period."""
    return round_half_up_cents(
        Decimal(monthly_minimum_cents) * Decimal(active_days) / Decimal(days_in_period)
    )


def compute_line_amount(
    net_base_cents: int,
    rate: Decimal,
    monthly_minimum_cents: int | None,
    active_days: int,
    days_in_period: int,
) -> tuple[int, bool]:
    """R1: amount_due = max(round(rate * net_base), prorated minimum or 0).

    The percentage component never prorates (it already scales with revenue).
    Returns (amount_due_cents, minimum_applied); the flag is set only when a
    configured minimum is the binding floor.
    """
    percentage = round_half_up_cents(rate * Decimal(net_base_cents))
    if monthly_minimum_cents is None:
        return max(percentage, 0), False
    floor = prorated_minimum_cents(monthly_minimum_cents, active_days, days_in_period)
    return max(percentage, floor), floor > percentage


@dataclass(frozen=True)
class LineInput:
    """Everything that determines one location's line item — the fingerprint unit."""

    location_id: uuid.UUID
    org_id: uuid.UUID
    report_id: uuid.UUID
    net_base_cents: int
    rate: Decimal
    monthly_minimum_cents: int | None
    active_days: int
    days_in_period: int


@dataclass(frozen=True)
class ExclusionInput:
    location_id: uuid.UUID
    org_id: uuid.UUID
    reason: str


def compute_fingerprint(
    period: date, lines: list[LineInput], exclusions: list[ExclusionInput]
) -> str:
    """Canonical SHA-256 over everything that determines the run's output (ADR-0004).

    Includes report ids so a locked correction (same figures, new report row)
    still reads as changed inputs — the run must be traceable to the exact
    attested documents it billed from.
    """
    payload = {
        "period": period.isoformat(),
        "lines": [
            {
                "location_id": str(li.location_id),
                "report_id": str(li.report_id),
                "net_base_cents": li.net_base_cents,
                "rate": str(li.rate),
                "monthly_minimum_cents": li.monthly_minimum_cents,
                "active_days": li.active_days,
                "days_in_period": li.days_in_period,
            }
            for li in sorted(lines, key=lambda li: str(li.location_id))
        ],
        "excluded": [
            {"location_id": str(ex.location_id), "reason": ex.reason}
            for ex in sorted(exclusions, key=lambda ex: str(ex.location_id))
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _period_days(period: date) -> tuple[date, int]:
    days = calendar.monthrange(period.year, period.month)[1]
    return period.replace(day=days), days


def _active_days(activated_on: date, period: date, period_end: date, days: int) -> int:
    if activated_on <= period:
        return days
    return (period_end - activated_on).days + 1


# ---------------------------------------------------------------------------
# Revenue report lifecycle (R3)
# ---------------------------------------------------------------------------


def _report_out(report: RevenueReport) -> RevenueReportOut:
    return RevenueReportOut.model_validate(report, from_attributes=True)


async def create_report(
    session: AsyncSession,
    actor: TokenClaims,
    location_id: uuid.UUID,
    period: date,
    gross_cents: int,
    refunds_cents: int,
) -> RevenueReportOut:
    """Create a draft revenue report for (location, period). Operator only."""
    _require_role(actor, "operator")
    location = (
        await session.execute(select(Location).where(Location.id == location_id))
    ).scalar_one_or_none()
    if location is None:  # includes locations RLS hides from this tenant
        raise NotFoundError("location not found")

    existing = (
        (
            await session.execute(
                select(RevenueReport).where(
                    RevenueReport.location_id == location_id, RevenueReport.period == period
                )
            )
        )
        .scalars()
        .all()
    )
    if any(r.status != "locked" for r in existing):
        raise ReportStateError("an open report already exists for this location and period")
    if existing:
        raise ReportStateError(
            "a locked report exists for this location and period; create a correction instead"
        )

    report = RevenueReport(
        org_id=location.org_id,
        location_id=location_id,
        period=period,
        gross_cents=gross_cents,
        refunds_cents=refunds_cents,
        status="draft",
    )
    session.add(report)
    await session.flush()
    await session.refresh(report)  # server-computed net_base_cents
    return _report_out(report)


async def _get_report(session: AsyncSession, report_id: uuid.UUID) -> RevenueReport:
    report = (
        await session.execute(select(RevenueReport).where(RevenueReport.id == report_id))
    ).scalar_one_or_none()
    if report is None:
        raise NotFoundError("revenue report not found")
    return report


async def update_report(
    session: AsyncSession,
    actor: TokenClaims,
    report_id: uuid.UUID,
    gross_cents: int,
    refunds_cents: int,
) -> RevenueReportOut:
    """Edit a draft's figures. Locked reports raise ReportLockedError (invariant 2)."""
    _require_role(actor, "operator")
    report = await _get_report(session, report_id)
    if report.status == "locked":
        raise ReportLockedError("locked reports are immutable; create a correction instead")
    if report.status != "draft":
        raise ReportStateError("only draft reports can be edited")
    report.gross_cents = gross_cents
    report.refunds_cents = refunds_cents
    await session.flush()
    await session.refresh(report)
    return _report_out(report)


async def submit_report(
    session: AsyncSession, actor: TokenClaims, report_id: uuid.UUID
) -> RevenueReportOut:
    """R3: submission requires attestation and runs draft→submitted→locked
    atomically — both transitions inside this one transaction, so no observable
    state ever holds an unlocked attested report."""
    _require_role(actor, "operator")
    report = await _get_report(session, report_id)
    if report.status == "locked":
        raise ReportLockedError("report is already locked")
    if report.status != "draft":
        raise ReportStateError("only draft reports can be submitted")

    report.status = "submitted"
    report.attested_by = _actor_user_id(actor)
    report.attested_at = utcnow()
    await session.flush()
    report.status = "locked"
    await session.flush()
    await session.refresh(report)
    return _report_out(report)


async def create_correction(
    session: AsyncSession, actor: TokenClaims, report_id: uuid.UUID
) -> RevenueReportOut:
    """Correction path for a locked report: a new draft linked by supersedes.
    The locked row is never touched (invariant 2 — the DB trigger has no
    exception path because none is needed)."""
    _require_role(actor, "operator")
    original = await _get_report(session, report_id)
    if original.status != "locked":
        raise ReportStateError("only locked reports can be corrected; edit the draft instead")
    successor = (
        await session.execute(select(RevenueReport).where(RevenueReport.supersedes == report_id))
    ).scalar_one_or_none()
    if successor is not None:
        raise ReportStateError("a correction already exists for this report")

    correction = RevenueReport(
        org_id=original.org_id,
        location_id=original.location_id,
        period=original.period,
        gross_cents=original.gross_cents,
        refunds_cents=original.refunds_cents,
        status="draft",
        supersedes=original.id,
    )
    session.add(correction)
    await session.flush()
    await session.refresh(correction)
    return _report_out(correction)


async def list_reports(
    session: AsyncSession,
    actor: TokenClaims,
    period: date | None = None,
    location_id: uuid.UUID | None = None,
) -> list[RevenueReportOut]:
    _require_role(actor, "operator", "hq_admin")
    query = select(RevenueReport).order_by(RevenueReport.created_at)
    if period is not None:
        query = query.where(RevenueReport.period == period)
    if location_id is not None:
        query = query.where(RevenueReport.location_id == location_id)
    reports = (await session.execute(query)).scalars().all()
    return [_report_out(r) for r in reports]


# ---------------------------------------------------------------------------
# run_royalty_period (R1, R4; ADR-0004)
# ---------------------------------------------------------------------------


async def _current_locked_reports(
    session: AsyncSession, period: date
) -> dict[uuid.UUID, RevenueReport]:
    """Latest locked report per location for the period: locked rows not
    superseded by another *locked* row (a pending draft correction does not
    un-lock its predecessor)."""
    successor = aliased(RevenueReport)
    rows = (
        (
            await session.execute(
                select(RevenueReport)
                .where(
                    RevenueReport.period == period,
                    RevenueReport.status == "locked",
                    ~select(successor.id)
                    .where(successor.supersedes == RevenueReport.id, successor.status == "locked")
                    .exists(),
                )
                .order_by(RevenueReport.created_at)
            )
        )
        .scalars()
        .all()
    )
    return {r.location_id: r for r in rows}


async def _effective_agreements(
    session: AsyncSession, period: date
) -> dict[uuid.UUID, LicenseAgreement]:
    """Per org, the agreement in force at the period start (latest effective_from wins)."""
    rows = (
        (
            await session.execute(
                select(LicenseAgreement)
                .where(
                    LicenseAgreement.effective_from <= period,
                    (LicenseAgreement.effective_to.is_(None))
                    | (LicenseAgreement.effective_to >= period),
                )
                .order_by(LicenseAgreement.effective_from)
            )
        )
        .scalars()
        .all()
    )
    return {a.org_id: a for a in rows}


def _run_out(
    run: RoyaltyRun,
    line_items: list[RoyaltyLineItem],
    exclusions: list[RoyaltyRunExclusion],
    reused: bool,
) -> RoyaltyRunOut:
    return RoyaltyRunOut(
        id=run.id,
        period=run.period,
        version=run.version,
        input_fingerprint=run.input_fingerprint,
        generated_at=run.generated_at,
        reused=reused,
        line_items=[
            RoyaltyLineItemOut.model_validate(li, from_attributes=True) for li in line_items
        ],
        exclusions=[
            RunExclusionOut(location_id=ex.location_id, org_id=ex.org_id, reason=ex.reason)
            for ex in exclusions
        ],
    )


async def _load_run_children(
    session: AsyncSession, run_id: uuid.UUID
) -> tuple[list[RoyaltyLineItem], list[RoyaltyRunExclusion]]:
    line_items = (
        (
            await session.execute(
                select(RoyaltyLineItem)
                .where(RoyaltyLineItem.run_id == run_id)
                .order_by(RoyaltyLineItem.location_id)
            )
        )
        .scalars()
        .all()
    )
    exclusions = (
        (
            await session.execute(
                select(RoyaltyRunExclusion)
                .where(RoyaltyRunExclusion.run_id == run_id)
                .order_by(RoyaltyRunExclusion.location_id)
            )
        )
        .scalars()
        .all()
    )
    return list(line_items), list(exclusions)


async def run_royalty_period(
    session: AsyncSession, actor: TokenClaims, period: date
) -> RoyaltyRunOut:
    """Compute royalty line items for a period over the current locked reports.

    Idempotent per (period, inputs): if the input fingerprint matches the
    latest existing version, that version is returned untouched; changed inputs
    append version N+1. Prior versions are never mutated (invariant 3).
    Locations with an unlocked/missing report or no in-force agreement are
    excluded and recorded on the run (policy A3). HQ only.
    """
    _require_role(actor, "hq_admin")
    period_end, days = _period_days(period)

    locations = (
        (
            await session.execute(
                select(Location)
                .join(Org, Location.org_id == Org.id)
                .where(Org.kind == "operator", Location.activated_on <= period_end)
                .order_by(Location.id)
            )
        )
        .scalars()
        .all()
    )
    reports = await _current_locked_reports(session, period)
    agreements = await _effective_agreements(session, period)

    lines: list[LineInput] = []
    exclusions: list[ExclusionInput] = []
    for loc in locations:
        report = reports.get(loc.id)
        agreement = agreements.get(loc.org_id)
        if report is None:
            exclusions.append(ExclusionInput(loc.id, loc.org_id, EXCLUDED_NO_LOCKED_REPORT))
            continue
        if agreement is None:
            exclusions.append(ExclusionInput(loc.id, loc.org_id, EXCLUDED_NO_ACTIVE_AGREEMENT))
            continue
        lines.append(
            LineInput(
                location_id=loc.id,
                org_id=loc.org_id,
                report_id=report.id,
                net_base_cents=report.net_base_cents,
                rate=agreement.royalty_rate,
                monthly_minimum_cents=agreement.monthly_minimum_cents,
                active_days=_active_days(loc.activated_on, period, period_end, days),
                days_in_period=days,
            )
        )

    fingerprint = compute_fingerprint(period, lines, exclusions)

    latest = (
        await session.execute(
            select(RoyaltyRun)
            .where(RoyaltyRun.period == period)
            .order_by(RoyaltyRun.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is not None and latest.input_fingerprint == fingerprint:
        line_items, excl_rows = await _load_run_children(session, latest.id)
        return _run_out(latest, line_items, excl_rows, reused=True)

    run = RoyaltyRun(
        period=period,
        version=1 if latest is None else latest.version + 1,
        input_fingerprint=fingerprint,
    )
    session.add(run)
    await session.flush()

    line_items = []
    for li in sorted(lines, key=lambda li: str(li.location_id)):
        amount, minimum_applied = compute_line_amount(
            li.net_base_cents, li.rate, li.monthly_minimum_cents, li.active_days, li.days_in_period
        )
        line_items.append(
            RoyaltyLineItem(
                run_id=run.id,
                org_id=li.org_id,
                location_id=li.location_id,
                base_cents=li.net_base_cents,
                rate=li.rate,
                minimum_applied=minimum_applied,
                adjustments_cents=0,  # manual adjustments are post-MVP; fingerprinted as absent
                amount_due_cents=amount,
            )
        )
    excl_rows = [
        RoyaltyRunExclusion(
            run_id=run.id, org_id=ex.org_id, location_id=ex.location_id, reason=ex.reason
        )
        for ex in sorted(exclusions, key=lambda ex: str(ex.location_id))
    ]
    session.add_all(line_items)
    session.add_all(excl_rows)
    await session.flush()
    await session.refresh(run)  # server-generated generated_at
    return _run_out(run, line_items, excl_rows, reused=False)


async def list_runs(
    session: AsyncSession, actor: TokenClaims, period: date | None = None
) -> list[RoyaltyRunSummaryOut]:
    _require_role(actor, "hq_admin")
    query = select(RoyaltyRun).order_by(RoyaltyRun.period, RoyaltyRun.version)
    if period is not None:
        query = query.where(RoyaltyRun.period == period)
    runs = (await session.execute(query)).scalars().all()
    return [RoyaltyRunSummaryOut.model_validate(r, from_attributes=True) for r in runs]


async def _get_run(session: AsyncSession, run_id: uuid.UUID) -> RoyaltyRun:
    run = (
        await session.execute(select(RoyaltyRun).where(RoyaltyRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("royalty run not found")
    return run


async def list_line_items(
    session: AsyncSession, actor: TokenClaims, run_id: uuid.UUID
) -> list[RoyaltyLineItemOut]:
    """Line items for a run. Operators see only their own rows (RLS)."""
    _require_role(actor, "operator", "hq_admin")
    await _get_run(session, run_id)  # 404 before returning an empty list
    line_items, _ = await _load_run_children(session, run_id)
    return [RoyaltyLineItemOut.model_validate(li, from_attributes=True) for li in line_items]


# ---------------------------------------------------------------------------
# Invoices (invariant 6) and aging
# ---------------------------------------------------------------------------

NET_TERMS_DAYS = 30  # A5: invoices are net-30


def _invoice_out(invoice: Invoice) -> InvoiceOut:
    out = InvoiceOut.model_validate(invoice, from_attributes=True)
    # Overdue is derived at read time: storage keeps 'issued' until payment, so
    # nothing has to sweep statuses on a clock. Paid/superseded never regress.
    if out.status == "issued" and out.due_date < utcnow().date():
        out.status = "overdue"
    return out


async def mark_invoice_paid(
    session: AsyncSession, actor: TokenClaims, invoice_id: uuid.UUID
) -> InvoiceOut:
    """Record payment manually (Phase 6 replaces this with Stripe webhooks).

    Idempotent: paying a paid invoice returns it unchanged. Superseded invoices
    can't be paid — the live successor carries the balance (invariant 6).
    HQ only.
    """
    _require_role(actor, "hq_admin")
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        raise NotFoundError("invoice not found")
    if invoice.superseded_by is not None:
        raise InvoiceStateError("superseded invoices cannot be paid; pay the live successor")
    if invoice.status != "paid":
        invoice.status = "paid"
        await session.flush()
    return _invoice_out(invoice)


async def issue_invoices(
    session: AsyncSession, actor: TokenClaims, run_id: uuid.UUID
) -> IssueInvoicesOut:
    """One invoice per (run, org), aggregating the run's line items, due net-30.

    Idempotent per run: existing live invoices are returned as-is. Regeneration
    happens by issuing from a newer run version — the new invoices supersede
    the period's prior ones per org (superseded_by); rows are never edited
    (invariant 6). Only the latest run version for a period may be invoiced,
    so supersession is monotone. HQ only.
    """
    _require_role(actor, "hq_admin")
    run = await _get_run(session, run_id)

    existing = (
        (await session.execute(select(Invoice).where(Invoice.run_id == run_id))).scalars().all()
    )
    live = [inv for inv in existing if inv.superseded_by is None]
    if live:
        return IssueInvoicesOut(
            run_id=run_id, reused=True, invoices=[_invoice_out(inv) for inv in live]
        )
    if existing:
        raise InvoiceStateError(
            "this run's invoices were superseded; issue from the current run version"
        )

    latest_version = (
        await session.execute(
            select(RoyaltyRun)
            .where(RoyaltyRun.period == run.period)
            .order_by(RoyaltyRun.version.desc())
            .limit(1)
        )
    ).scalar_one()
    if latest_version.id != run.id:
        raise InvoiceStateError(
            f"run version {run.version} is not the latest for {run.period}; "
            f"issue from version {latest_version.version}"
        )

    # amount_due_cents is the line's full obligation (adjustments, when they
    # exist post-MVP, fold into it at computation time — never summed twice).
    line_items, _ = await _load_run_children(session, run_id)
    totals: dict[uuid.UUID, int] = {}
    for li in line_items:
        totals[li.org_id] = totals.get(li.org_id, 0) + li.amount_due_cents

    issued_at = utcnow()
    due = issued_at.date() + timedelta(days=NET_TERMS_DAYS)
    invoices = [
        Invoice(
            run_id=run_id,
            org_id=org_id,
            amount_due_cents=amount,
            status="issued",
            due_date=due,
            issued_at=issued_at,
        )
        for org_id, amount in sorted(totals.items(), key=lambda kv: str(kv[0]))
    ]
    session.add_all(invoices)
    await session.flush()

    # Supersede the period's prior live invoices for orgs re-billed here. Only
    # superseded_by is ever written on an existing invoice — never its figures.
    prior = (
        (
            await session.execute(
                select(Invoice)
                .join(RoyaltyRun, Invoice.run_id == RoyaltyRun.id)
                .where(
                    RoyaltyRun.period == run.period,
                    Invoice.run_id != run_id,
                    Invoice.superseded_by.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    replacement = {inv.org_id: inv.id for inv in invoices}
    for old in prior:
        new_id = replacement.get(old.org_id)
        if new_id is not None:
            old.superseded_by = new_id
    await session.flush()

    return IssueInvoicesOut(
        run_id=run_id, reused=False, invoices=[_invoice_out(inv) for inv in invoices]
    )


async def list_invoices(
    session: AsyncSession, actor: TokenClaims, run_id: uuid.UUID | None = None
) -> list[InvoiceOut]:
    _require_role(actor, "operator", "hq_admin")
    query = select(Invoice).order_by(Invoice.issued_at, Invoice.id)
    if run_id is not None:
        query = query.where(Invoice.run_id == run_id)
    invoices = (await session.execute(query)).scalars().all()
    return [_invoice_out(inv) for inv in invoices]


_BUCKETS: list[AgingBucketName] = ["0-30", "31-60", "61-90", "90+"]


def aging_bucket(days_outstanding: int) -> AgingBucketName:
    if days_outstanding <= 30:
        return "0-30"
    if days_outstanding <= 60:
        return "31-60"
    if days_outstanding <= 90:
        return "61-90"
    return "90+"


async def invoice_aging(
    session: AsyncSession, actor: TokenClaims, as_of: date | None = None
) -> AgingOut:
    """Unpaid, live invoices bucketed by days since issue. HQ only."""
    _require_role(actor, "hq_admin")
    as_of = as_of or utcnow().date()

    unpaid = (
        (
            await session.execute(
                select(Invoice)
                .where(Invoice.superseded_by.is_(None), Invoice.status != "paid")
                .order_by(Invoice.issued_at, Invoice.id)
            )
        )
        .scalars()
        .all()
    )

    rows: list[AgingInvoiceOut] = []
    totals = {
        name: AgingBucketOut(bucket=name, invoice_count=0, amount_due_cents=0) for name in _BUCKETS
    }
    for inv in unpaid:
        days = max((as_of - inv.issued_at.date()).days, 0)
        bucket = aging_bucket(days)
        rows.append(
            AgingInvoiceOut(
                id=inv.id,
                org_id=inv.org_id,
                run_id=inv.run_id,
                amount_due_cents=inv.amount_due_cents,
                due_date=inv.due_date,
                issued_at=inv.issued_at,
                days_outstanding=days,
                bucket=bucket,
            )
        )
        totals[bucket].invoice_count += 1
        totals[bucket].amount_due_cents += inv.amount_due_cents

    return AgingOut(as_of=as_of, buckets=[totals[name] for name in _BUCKETS], invoices=rows)
