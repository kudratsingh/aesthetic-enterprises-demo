"""Collections (Phase 6, ADR-0010): payment attempts against invoices.

One row per checkout session with a provider. Unlike the supply ledgers,
payments are mutable state machines (initiated → succeeded | failed, and
failed → succeeded on payer retry); `provider_ref` is the provider's identity
for the session and is UNIQUE so webhook replays land on the same row.
"""

import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampedTenantMixin, cents

payment_status = Enum("initiated", "succeeded", "failed", name="payment_status")


class Payment(Base, TimestampedTenantMixin):
    """A payment attempt for exactly one invoice, keyed to the provider by
    provider_ref. Tenant-scoped (RLS on org_id): an operator sees only its own
    payments; the webhook writes in the machine hq_admin context (ADR-0002)."""

    __tablename__ = "payments"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_ref: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    amount_cents: Mapped[cents]
    status: Mapped[str] = mapped_column(payment_status, nullable=False, default="initiated")
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
