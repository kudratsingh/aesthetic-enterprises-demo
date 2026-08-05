import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampedTenantMixin, location_fk

order_status = Enum("draft", "submitted", "fulfilled", name="order_status")


class OnboardingTask(Base, TimestampedTenantMixin):
    """One task instance on an operator's 60-day onboarding checklist.

    Instances are stamped per org from the seed's fixed template (ADR-0009) —
    no separate template table until per-network templates are a real need.
    """

    __tablename__ = "onboarding_tasks"
    __table_args__ = (
        CheckConstraint("due_offset_days >= 0", name="ck_onboarding_due_offset_non_negative"),
        UniqueConstraint("org_id", "sort_order", name="uq_onboarding_tasks_org_sort"),
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    due_offset_days: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class PortalDocument(Base, TimestampedTenantMixin):
    """Document vault entry. Text-only for the demo — real file storage is an
    object-store integration deliberately out of scope (ADR-0009). Never PHI."""

    __tablename__ = "portal_documents"

    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ProductOrder(Base, TimestampedTenantMixin):
    """Operator product reorder. Fulfillment (HQ) writes real shipments into the
    supply ledger — the order is the request, the ledger stays the truth."""

    __tablename__ = "product_orders"

    location_id: Mapped[location_fk]
    status: Mapped[str] = mapped_column(order_status, nullable=False, default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ProductOrderLine(Base, TimestampedTenantMixin):
    __tablename__ = "product_order_lines"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_order_lines_qty_positive"),
        UniqueConstraint("order_id", "product_id", name="uq_order_lines_order_product"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_orders.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
