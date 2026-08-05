"""Request/response models for collections (Phase 6, ADR-0010). Money is
integer cents; provider refs are opaque strings owned by the provider."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.royalty import InvoiceStatus

PaymentStatus = Literal["initiated", "succeeded", "failed"]
PaymentEvent = Literal["payment_succeeded", "payment_failed"]


class PaymentOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    invoice_id: uuid.UUID
    provider: str
    provider_ref: str
    amount_cents: int
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime | None


class CheckoutOut(BaseModel):
    payment: PaymentOut
    checkout_url: str = Field(
        description="Provider-hosted checkout page for this session (mock URL in dev/demo)"
    )
    reused: bool = Field(
        description="True when an existing open payment for the invoice was returned"
    )


class PaymentEventIn(BaseModel):
    """Provider callback payload for /webhooks/payments (HMAC-authenticated)."""

    provider_ref: str
    event: PaymentEvent


class PaymentResultOut(BaseModel):
    """Outcome of applying one provider event (webhook or simulate)."""

    payment_id: uuid.UUID
    invoice_id: uuid.UUID
    payment_status: PaymentStatus
    invoice_status: InvoiceStatus | None = Field(
        description="Invoice status after the event; None when the event left it untouched"
    )
    applied: bool = Field(
        description="False when the event was an idempotent replay and changed nothing"
    )
