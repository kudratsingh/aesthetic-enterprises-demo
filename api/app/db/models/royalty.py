import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import (
    Base,
    TimestampedTenantMixin,
    cents,
    created_at_col,
    location_fk,
    uuid_pk,
)

report_status = Enum("draft", "submitted", "locked", name="report_status")
invoice_status = Enum("issued", "paid", "overdue", name="invoice_status")
variance_status = Enum("open", "reviewed", "resolved", name="variance_status")


class RevenueReport(Base, TimestampedTenantMixin):
    """Operator's monthly statement per location. period is the first day of the
    month (boundaries computed in network_timezone). Locked reports are immutable
    (invariant 2, enforced in Phase 2 services + a DB trigger); corrections create
    a successor row via supersedes."""

    __tablename__ = "revenue_reports"
    __table_args__ = (
        CheckConstraint("gross_cents >= 0", name="ck_revenue_reports_gross_non_negative"),
        CheckConstraint("refunds_cents >= 0", name="ck_revenue_reports_refunds_non_negative"),
    )

    location_id: Mapped[location_fk]
    period: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    gross_cents: Mapped[cents]
    refunds_cents: Mapped[cents]
    net_base_cents: Mapped[int] = mapped_column(
        BigInteger, Computed("gross_cents - refunds_cents", persisted=True), nullable=False
    )
    status: Mapped[str] = mapped_column(report_status, nullable=False, default="draft")
    attested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    attested_at: Mapped[datetime | None] = mapped_column(nullable=True)
    supersedes: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("revenue_reports.id"), nullable=True
    )


class RoyaltyRun(Base):
    """HQ-only artifact: one versioned execution of royalty calculation for a
    period. Append-only + idempotent per input fingerprint (invariant 3, Phase 2)."""

    __tablename__ = "royalty_runs"
    __table_args__ = (UniqueConstraint("period", "version", name="uq_royalty_runs_period_version"),)

    id: Mapped[uuid_pk]
    period: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[created_at_col]


class RoyaltyLineItem(Base, TimestampedTenantMixin):
    __tablename__ = "royalty_line_items"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("royalty_runs.id"), nullable=False, index=True
    )
    location_id: Mapped[location_fk]
    base_cents: Mapped[cents]
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    minimum_applied: Mapped[bool] = mapped_column(nullable=False, default=False)
    adjustments_cents: Mapped[cents]
    amount_due_cents: Mapped[cents]


class Invoice(Base, TimestampedTenantMixin):
    """One invoice per (run version, org). References exactly one royalty_run
    (invariant 6); regeneration supersedes, never edits."""

    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("run_id", "org_id", name="uq_invoices_run_org"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("royalty_runs.id"), nullable=False, index=True
    )
    amount_due_cents: Mapped[cents]
    status: Mapped[str] = mapped_column(invoice_status, nullable=False, default="issued")
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoices.id"), nullable=True
    )


class VarianceFlag(Base, TimestampedTenantMixin):
    """Reported net_base vs supply-derived expected floor (R5). Operators see
    their own rows via RLS; service layer restricts them to resolved ones."""

    __tablename__ = "variance_flags"

    location_id: Mapped[location_fk]
    period: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    reported_net_base_cents: Mapped[cents]
    expected_floor_cents: Mapped[cents]
    status: Mapped[str] = mapped_column(variance_status, nullable=False, default="open")
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
