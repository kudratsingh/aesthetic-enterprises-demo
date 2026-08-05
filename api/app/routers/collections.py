"""Collections endpoints — thin HTTP layer over app.services.collections.

The webhook takes the RAW request body on purpose: the HMAC covers the exact
bytes the provider sent (ADR-0005 pattern). All domain rules, the provider
seam, and the machine tenancy context live in the service (ADR-0010).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings, get_settings
from app.core.security import CurrentUser
from app.db.tenancy import TenantSession
from app.schemas.collections import CheckoutOut, PaymentOut, PaymentResultOut
from app.services import collections

router = APIRouter(tags=["collections"])


@router.post("/collections/invoices/{invoice_id}/checkout", status_code=201)
async def create_checkout(
    invoice_id: uuid.UUID,
    user: CurrentUser,
    session: TenantSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CheckoutOut:
    """Open a provider checkout session for a live, unpaid invoice (operator
    pays own via RLS; HQ may start collection). Idempotent per invoice."""
    return await collections.create_checkout(session, user, invoice_id, settings)


@router.get("/collections/payments")
async def list_payments(
    user: CurrentUser, session: TenantSession, invoice_id: uuid.UUID | None = None
) -> list[PaymentOut]:
    """Payments visible to the caller (RLS-scoped), optionally for one invoice."""
    return await collections.list_payments(session, user, invoice_id)


@router.post("/collections/payments/{payment_id}/simulate")
async def simulate_payment(
    payment_id: uuid.UUID, user: CurrentUser, session: TenantSession
) -> PaymentResultOut:
    """Dev/demo stand-in for the mock provider's hosted-checkout redirect: marks
    the payment succeeded through the same internal path the webhook uses. The
    payment must be visible to the caller (operator: own org; HQ: any)."""
    return await collections.simulate_payment_success(session, user, payment_id)


@router.post("/webhooks/payments")
async def payments_webhook(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> PaymentResultOut:
    """HMAC-verified provider callback → idempotent payment/invoice update.

    No JWT: authentication is the HMAC-SHA256 signature of the raw body in the
    X-Webhook-Signature header (401 on mismatch, 503 if no secret configured).
    Payload: {"provider_ref": str, "event": "payment_succeeded"|"payment_failed"}.
    """
    return await collections.process_payment_webhook(
        await request.body(), request.headers.get(collections.SIGNATURE_HEADER), settings
    )
