"""Royalty cycle endpoints — thin HTTP layer over app.services.royalty.

Role enforcement and all domain rules live in the service; RLS (via
TenantSession) is the tenancy boundary. Routers only bind requests to calls.
"""

import uuid
from datetime import date

from fastapi import APIRouter

from app.core.security import CurrentUser
from app.db.tenancy import TenantSession
from app.schemas.royalty import (
    AgingOut,
    InvoiceOut,
    IssueInvoicesOut,
    RevenueReportCreate,
    RevenueReportOut,
    RevenueReportUpdate,
    RoyaltyLineItemOut,
    RoyaltyRunOut,
    RoyaltyRunRequest,
    RoyaltyRunSummaryOut,
)
from app.services import royalty

router = APIRouter(prefix="/royalty", tags=["royalty"])


@router.post("/reports", status_code=201)
async def create_report(
    body: RevenueReportCreate, user: CurrentUser, session: TenantSession
) -> RevenueReportOut:
    """Create a draft revenue report for one location and period (operator)."""
    return await royalty.create_report(
        session, user, body.location_id, body.period, body.gross_cents, body.refunds_cents
    )


@router.get("/reports")
async def list_reports(
    user: CurrentUser,
    session: TenantSession,
    period: date | None = None,
    location_id: uuid.UUID | None = None,
) -> list[RevenueReportOut]:
    """Reports visible to the caller (RLS-scoped), optionally filtered."""
    return await royalty.list_reports(session, user, period, location_id)


@router.patch("/reports/{report_id}")
async def update_report(
    report_id: uuid.UUID,
    body: RevenueReportUpdate,
    user: CurrentUser,
    session: TenantSession,
) -> RevenueReportOut:
    """Edit a draft's figures; a locked report raises report_locked (409)."""
    return await royalty.update_report(
        session, user, report_id, body.gross_cents, body.refunds_cents
    )


@router.post("/reports/{report_id}/submit")
async def submit_report(
    report_id: uuid.UUID, user: CurrentUser, session: TenantSession
) -> RevenueReportOut:
    """Attest and submit: draft→submitted→locked atomically (R3)."""
    return await royalty.submit_report(session, user, report_id)


@router.post("/reports/{report_id}/corrections", status_code=201)
async def create_correction(
    report_id: uuid.UUID, user: CurrentUser, session: TenantSession
) -> RevenueReportOut:
    """Correct a locked report: new draft linked to it via supersedes."""
    return await royalty.create_correction(session, user, report_id)


@router.post("/runs", status_code=201)
async def run_royalty_period(
    body: RoyaltyRunRequest, user: CurrentUser, session: TenantSession
) -> RoyaltyRunOut:
    """Run the period over current locked reports (HQ). Idempotent + versioned (R4)."""
    return await royalty.run_royalty_period(session, user, body.period)


@router.get("/runs")
async def list_runs(
    user: CurrentUser, session: TenantSession, period: date | None = None
) -> list[RoyaltyRunSummaryOut]:
    """All run versions, optionally for one period (HQ)."""
    return await royalty.list_runs(session, user, period)


@router.get("/runs/{run_id}/line-items")
async def list_line_items(
    run_id: uuid.UUID, user: CurrentUser, session: TenantSession
) -> list[RoyaltyLineItemOut]:
    """A run's line items; operators see only their own rows (RLS)."""
    return await royalty.list_line_items(session, user, run_id)


@router.post("/runs/{run_id}/invoices", status_code=201)
async def issue_invoices(
    run_id: uuid.UUID, user: CurrentUser, session: TenantSession
) -> IssueInvoicesOut:
    """Issue one net-30 invoice per (run, org) (HQ). Reissuing supersedes, never edits."""
    return await royalty.issue_invoices(session, user, run_id)


@router.get("/invoices")
async def list_invoices(
    user: CurrentUser, session: TenantSession, run_id: uuid.UUID | None = None
) -> list[InvoiceOut]:
    """Invoices visible to the caller (RLS-scoped), optionally for one run."""
    return await royalty.list_invoices(session, user, run_id)


@router.get("/invoices/aging")
async def invoice_aging(
    user: CurrentUser, session: TenantSession, as_of: date | None = None
) -> AgingOut:
    """Unpaid live invoices bucketed 0-30 / 31-60 / 61-90 / 90+ days (HQ)."""
    return await royalty.invoice_aging(session, user, as_of)


@router.post("/invoices/{invoice_id}/pay")
async def pay_invoice(
    invoice_id: uuid.UUID, user: CurrentUser, session: TenantSession
) -> InvoiceOut:
    """Record payment manually (HQ). Stripe replaces this in Phase 6."""
    return await royalty.mark_invoice_paid(session, user, invoice_id)
