"""Collections (Phase 6, ADR-0010): checkout sessions with a payment provider
and the provider's payment-status webhook, so invoices become money movement.

The provider lives behind a small Protocol seam. The only implementation is
`MockStripeProvider` — deterministic refs, fake URLs, zero I/O — because no
real provider account exists yet; a real Stripe (or ACH) implementation slots
in behind the same Protocol without touching this module's callers.

Rules encoded here:
- A checkout refuses paid or superseded invoices; the live successor carries
  the balance (invariant 6). One open payment per invoice: an existing
  initiated (or failed — payer retry) payment is returned, never duplicated.
- /webhooks/payments follows the ingest webhook pattern exactly (ADR-0005):
  HMAC-SHA256 over the raw body, constant-time compare, 503 when the secret is
  unset (fail closed), 401 on mismatch. Events run in the machine hq_admin RLS
  context via the standard set_config pattern (ADR-0002) — a policy-level
  role, never a bypass.
- Success marks the payment succeeded AND the invoice paid by calling
  royalty.mark_invoice_paid (the one sanctioned payment path); failure marks
  only the payment — the invoice stays collectible. `succeeded` is terminal:
  replays and out-of-order failure events no-op; `failed → succeeded` is
  allowed (the payer retried the same checkout session).

Typed domain errors live in this module (not core/errors.py) because they are
collections-specific; main.py translates them like any other DomainError.
"""

import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

import pydantic
import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import DomainError, NotFoundError, RoleForbiddenError
from app.core.security import TokenClaims
from app.db.engine import get_session_factory
from app.db.models import Invoice, Payment
from app.db.models.base import utcnow
from app.schemas.collections import (
    CheckoutOut,
    PaymentEvent,
    PaymentEventIn,
    PaymentOut,
    PaymentResultOut,
)
from app.services import royalty

log = structlog.get_logger()

SIGNATURE_HEADER = "X-Webhook-Signature"

# ---------------------------------------------------------------------------
# Collections-specific domain errors (module-local by design; see docstring)
# ---------------------------------------------------------------------------


class PaymentWebhookNotConfiguredError(DomainError):
    """PAYMENT_WEBHOOK_SECRET is unset — fail closed, never accept unsigned events."""

    code = "payment_webhook_not_configured"
    status_code = 503


class InvalidPaymentSignatureError(DomainError):
    """Missing or mismatched HMAC signature on the raw request body."""

    code = "invalid_signature"
    status_code = 401


class PaymentPayloadError(DomainError):
    """Body is not valid JSON or does not match the documented payload shape."""

    code = "invalid_payload"
    status_code = 400


class UnknownProviderRefError(DomainError):
    """Event references a provider_ref no payment row carries."""

    code = "unknown_provider_ref"
    status_code = 400


class ProviderNotConfiguredError(DomainError):
    """payment_provider names an implementation this build does not ship."""

    code = "payment_provider_not_configured"
    status_code = 503


class InvoiceAlreadyPaidError(DomainError):
    """Checkout refused: the invoice is already paid."""

    code = "invoice_already_paid"
    status_code = 409


class InvoiceSupersededError(DomainError):
    """Checkout refused: a superseded invoice is never collectible (invariant 6)."""

    code = "invoice_superseded"
    status_code = 409


# ---------------------------------------------------------------------------
# Provider seam (ADR-0010) — a real Stripe/ACH implementation slots in here
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckoutSession:
    """What any provider hands back for one hosted-checkout attempt."""

    provider_ref: str
    checkout_url: str


class PaymentProvider(Protocol):
    """The whole provider contract. Implementations own ref format and URL;
    callers persist provider_ref and treat both as opaque."""

    def create_checkout(self, invoice: Invoice) -> CheckoutSession: ...


class MockStripeProvider:
    """Deterministic, zero-I/O stand-in for a hosted-checkout provider.

    Refs derive from the invoice id, so re-creating a checkout for the same
    invoice yields the same session — which is exactly the idempotency a real
    integration gets by persisting the provider's ref. URLs live under a
    reserved .local domain that can never resolve to a real host.
    """

    def create_checkout(self, invoice: Invoice) -> CheckoutSession:
        ref = f"mock_cs_{invoice.id.hex[:12]}"
        return CheckoutSession(
            provider_ref=ref, checkout_url=f"https://checkout.mock.local/session/{ref}"
        )


def get_payment_provider(settings: Settings) -> PaymentProvider:
    if settings.payment_provider == "mock":
        return MockStripeProvider()
    raise ProviderNotConfiguredError(
        f"payment provider '{settings.payment_provider}' is not available in this build"
    )


# ---------------------------------------------------------------------------
# Signature verification (unit-tested directly; tests/unit/test_collections_provider.py)
# ---------------------------------------------------------------------------


def verify_payment_webhook_signature(
    raw_body: bytes, signature: str | None, settings: Settings
) -> None:
    """HMAC-SHA256 over the raw body, hex-encoded, constant-time compare.

    Mirrors ingest.verify_webhook_signature (ADR-0005): raw bytes so signer and
    verifier hash identical input; 503 when no secret is configured — a deploy
    that forgot the secret must reject events loudly, not accept them silently.
    """
    if not settings.payment_webhook_secret:
        raise PaymentWebhookNotConfiguredError("payment webhook secret is not configured")
    if not signature:
        raise InvalidPaymentSignatureError(f"missing {SIGNATURE_HEADER} header")
    expected = hmac.new(
        settings.payment_webhook_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature.strip().lower()):
        raise InvalidPaymentSignatureError("signature mismatch")


# ---------------------------------------------------------------------------
# Machine tenancy context (no JWT on provider webhooks; ingest session pattern)
# ---------------------------------------------------------------------------

_MACHINE_HQ_ACTOR = TokenClaims(sub="payments-webhook", org_id="", role="hq_admin")

_SET_MACHINE_CONTEXT = text(
    "SELECT set_config('app.org_id', '', true), set_config('app.role', 'hq_admin', true)"
)


@asynccontextmanager
async def _machine_session() -> AsyncIterator[AsyncSession]:
    """hq_admin RLS context via the standard set_config pattern (ADR-0002/0005).

    Provider callbacks carry no JWT; the HMAC shared secret authenticates them
    as the licensor's payment provider, acting network-wide. app.org_id is ''
    (reads as NULL through the policies' NULLIF) — the hq_admin role clause is
    what grants access. RLS stays enabled and enforced; this is a policy-level
    role, not a bypass.
    """
    async with get_session_factory()() as session, session.begin():
        await session.execute(_SET_MACHINE_CONTEXT)
        yield session


# ---------------------------------------------------------------------------
# Checkout (operator pays own invoice; HQ may start collection)
# ---------------------------------------------------------------------------


def _require_role(actor: TokenClaims, *roles: str) -> None:
    if actor.role not in roles:
        raise RoleForbiddenError(f"role '{actor.role}' may not perform this operation")


def _payment_out(payment: Payment) -> PaymentOut:
    return PaymentOut.model_validate(payment, from_attributes=True)


async def create_checkout(
    session: AsyncSession, actor: TokenClaims, invoice_id: uuid.UUID, settings: Settings
) -> CheckoutOut:
    """Open (or return) the checkout session for one live, unpaid invoice.

    RLS scopes the invoice lookup: an operator can only ever reach its own
    invoices (another org's read as not found). Idempotent per invoice — an
    existing open payment (initiated, or failed awaiting payer retry) is
    returned, never duplicated; the UNIQUE provider_ref backs this at the DB.
    """
    _require_role(actor, "operator", "hq_admin")
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        raise NotFoundError("invoice not found")
    if invoice.superseded_by is not None:
        raise InvoiceSupersededError(
            "superseded invoices cannot be collected; pay the live successor"
        )
    if invoice.status == "paid":
        raise InvoiceAlreadyPaidError("invoice is already paid")

    checkout = get_payment_provider(settings).create_checkout(invoice)
    existing = (
        await session.execute(
            select(Payment)
            .where(Payment.invoice_id == invoice_id)
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status == "succeeded":  # unreachable while invoice status is honest
            raise InvoiceAlreadyPaidError("a succeeded payment already exists for this invoice")
        return CheckoutOut(
            payment=_payment_out(existing), checkout_url=checkout.checkout_url, reused=True
        )

    payment = Payment(
        org_id=invoice.org_id,
        invoice_id=invoice.id,
        provider=settings.payment_provider,
        provider_ref=checkout.provider_ref,
        amount_cents=invoice.amount_due_cents,
        status="initiated",
    )
    session.add(payment)
    await session.flush()
    await session.refresh(payment)
    log.info(
        "payment_checkout_created",
        invoice_id=str(invoice.id),
        provider=payment.provider,
        provider_ref=payment.provider_ref,
    )
    return CheckoutOut(
        payment=_payment_out(payment), checkout_url=checkout.checkout_url, reused=False
    )


async def list_payments(
    session: AsyncSession, actor: TokenClaims, invoice_id: uuid.UUID | None = None
) -> list[PaymentOut]:
    """Payments visible to the caller (RLS-scoped), optionally for one invoice."""
    _require_role(actor, "operator", "hq_admin")
    query = select(Payment).order_by(Payment.created_at, Payment.id)
    if invoice_id is not None:
        query = query.where(Payment.invoice_id == invoice_id)
    payments = (await session.execute(query)).scalars().all()
    return [_payment_out(p) for p in payments]


# ---------------------------------------------------------------------------
# Provider events (webhook + the mock's simulate stand-in share one path)
# ---------------------------------------------------------------------------


async def _apply_event(
    session: AsyncSession, payment: Payment, event: PaymentEvent
) -> PaymentResultOut:
    """Apply one provider event to a payment inside the machine HQ context.

    succeeded is terminal (replays and late failure events no-op — an
    out-of-order 'failed' can never un-pay an invoice); failed may still
    succeed later (payer retried the same session). Success is the only path
    that touches the invoice, and only via royalty.mark_invoice_paid.
    """
    if payment.status == "succeeded":
        invoice = await session.get(Invoice, payment.invoice_id)
        return PaymentResultOut(
            payment_id=payment.id,
            invoice_id=payment.invoice_id,
            payment_status="succeeded",
            invoice_status="paid" if invoice is not None and invoice.status == "paid" else None,
            applied=False,
        )

    if event == "payment_succeeded":
        payment.status = "succeeded"
        payment.updated_at = utcnow()
        await session.flush()
        invoice_out = await royalty.mark_invoice_paid(
            session, _MACHINE_HQ_ACTOR, payment.invoice_id
        )
        log.info(
            "payment_succeeded",
            payment_id=str(payment.id),
            invoice_id=str(payment.invoice_id),
        )
        return PaymentResultOut(
            payment_id=payment.id,
            invoice_id=payment.invoice_id,
            payment_status="succeeded",
            invoice_status=invoice_out.status,
            applied=True,
        )

    applied = payment.status != "failed"
    if applied:
        payment.status = "failed"
        payment.updated_at = utcnow()
        await session.flush()
        log.info(
            "payment_failed",
            payment_id=str(payment.id),
            invoice_id=str(payment.invoice_id),
        )
    return PaymentResultOut(
        payment_id=payment.id,
        invoice_id=payment.invoice_id,
        payment_status="failed",
        invoice_status=None,
        applied=applied,
    )


def _parse_event_payload(raw_body: bytes) -> PaymentEventIn:
    try:
        data = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PaymentPayloadError("body is not valid JSON") from exc
    try:
        return PaymentEventIn.model_validate(data)
    except pydantic.ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "payload"
        raise PaymentPayloadError(f"invalid payload: {where}: {first['msg']}") from exc


async def _payment_by_ref(session: AsyncSession, provider_ref: str) -> Payment:
    payment = (
        await session.execute(select(Payment).where(Payment.provider_ref == provider_ref))
    ).scalar_one_or_none()
    if payment is None:
        raise UnknownProviderRefError(f"unknown provider_ref {provider_ref}")
    return payment


async def process_payment_webhook(
    raw_body: bytes, signature: str | None, settings: Settings
) -> PaymentResultOut:
    """Verify, parse, and apply one provider payment event (idempotent)."""
    verify_payment_webhook_signature(raw_body, signature, settings)
    payload = _parse_event_payload(raw_body)
    async with _machine_session() as session:
        payment = await _payment_by_ref(session, payload.provider_ref)
        return await _apply_event(session, payment, payload.event)


async def simulate_payment_success(
    session: AsyncSession, actor: TokenClaims, payment_id: uuid.UUID
) -> PaymentResultOut:
    """Dev/demo stand-in for the provider's hosted-checkout redirect flow.

    With a real provider, the payer completes checkout on the provider's page
    and the provider calls /webhooks/payments; the mock has no page, so this
    endpoint is that completion. The caller's tenant session only proves the
    payment is visible to them (operator: own org via RLS; HQ: any) — the
    mutation itself runs through _apply_event in the machine HQ context,
    exactly the webhook's path.
    """
    _require_role(actor, "operator", "hq_admin")
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError("payment not found")
    provider_ref = payment.provider_ref
    async with _machine_session() as machine:
        machine_payment = await _payment_by_ref(machine, provider_ref)
        return await _apply_event(machine, machine_payment, "payment_succeeded")
