import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampedTenantMixin, cents, location_fk


class Lead(Base, TimestampedTenantMixin):
    """Source-attributed top of funnel. (source, external_id) is the idempotency
    key for webhook/CSV ingestion (R7)."""

    __tablename__ = "leads"
    __table_args__ = (
        Index(
            "uq_leads_source_external_id",
            "source",
            "external_id",
            unique=True,
            postgresql_where="external_id IS NOT NULL",
        ),
    )

    location_id: Mapped[location_fk]
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class Consult(Base, TimestampedTenantMixin):
    __tablename__ = "consults"
    __table_args__ = (
        CheckConstraint("outcome IN ('no_show', 'no_sale', 'sale')", name="ck_consults_outcome"),
    )

    location_id: Mapped[location_fk]
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), nullable=False, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)


class Sale(Base, TimestampedTenantMixin):
    """planned_treatments feeds the R5 avg-ticket model (plan_value ÷ planned_treatments)."""

    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("plan_value_cents > 0", name="ck_sales_plan_value_positive"),
        CheckConstraint("planned_treatments > 0", name="ck_sales_planned_treatments_positive"),
    )

    location_id: Mapped[location_fk]
    consult_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("consults.id"), nullable=False, index=True
    )
    plan_value_cents: Mapped[cents]
    planned_treatments: Mapped[int] = mapped_column(nullable=False)
    financing_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sold_at: Mapped[datetime] = mapped_column(nullable=False)


class Treatment(Base, TimestampedTenantMixin):
    __tablename__ = "treatments"

    location_id: Mapped[location_fk]
    sale_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales.id"), nullable=False, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
