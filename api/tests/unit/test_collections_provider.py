"""Unit tests for the collections provider seam and webhook HMAC verification
(app.services.collections). Pure functions, no DB, no I/O."""

import hashlib
import hmac
import uuid

import pytest

from app.core.config import Settings
from app.db.models import Invoice
from app.services.collections import (
    InvalidPaymentSignatureError,
    MockStripeProvider,
    PaymentProvider,
    PaymentWebhookNotConfiguredError,
    ProviderNotConfiguredError,
    get_payment_provider,
    verify_payment_webhook_signature,
)

# ---------------------------------------------------------------------------
# MockStripeProvider determinism
# ---------------------------------------------------------------------------


def _invoice(invoice_id: uuid.UUID) -> Invoice:
    return Invoice(id=invoice_id)


def test_provider_refs_are_deterministic_per_invoice() -> None:
    invoice = _invoice(uuid.uuid4())
    first = MockStripeProvider().create_checkout(invoice)
    again = MockStripeProvider().create_checkout(invoice)
    assert first == again


def test_provider_ref_derives_from_invoice_id() -> None:
    invoice_id = uuid.UUID("0198c0de-0000-7000-8000-000000000001")
    session = MockStripeProvider().create_checkout(_invoice(invoice_id))
    assert session.provider_ref == f"mock_cs_{invoice_id.hex[:12]}"


def test_distinct_invoices_get_distinct_refs_and_urls() -> None:
    provider = MockStripeProvider()
    a = provider.create_checkout(_invoice(uuid.uuid4()))
    b = provider.create_checkout(_invoice(uuid.uuid4()))
    assert a.provider_ref != b.provider_ref
    assert a.checkout_url != b.checkout_url


def test_checkout_url_is_a_mock_local_url_containing_the_ref() -> None:
    session = MockStripeProvider().create_checkout(_invoice(uuid.uuid4()))
    assert session.checkout_url.startswith("https://checkout.mock.local/")
    assert session.provider_ref in session.checkout_url


def test_configured_mock_provider_is_selected() -> None:
    provider: PaymentProvider = get_payment_provider(Settings(payment_provider="mock"))
    assert isinstance(provider, MockStripeProvider)


def test_unknown_provider_fails_closed() -> None:
    with pytest.raises(ProviderNotConfiguredError):
        get_payment_provider(Settings(payment_provider="stripe"))
    assert ProviderNotConfiguredError.status_code == 503


# ---------------------------------------------------------------------------
# Webhook signature verification (mirrors the ingest webhook contract)
# ---------------------------------------------------------------------------

SECRET = "test-payment-webhook-secret"
BODY = b'{"provider_ref": "mock_cs_0123456789ab", "event": "payment_succeeded"}'


def _settings(secret: str | None = SECRET) -> Settings:
    return Settings(payment_webhook_secret=secret)


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_passes() -> None:
    verify_payment_webhook_signature(BODY, _sign(BODY), _settings())


def test_uppercase_and_padded_signature_passes() -> None:
    verify_payment_webhook_signature(BODY, f"  {_sign(BODY).upper()}  ", _settings())


def test_wrong_secret_is_rejected() -> None:
    with pytest.raises(InvalidPaymentSignatureError):
        verify_payment_webhook_signature(BODY, _sign(BODY, secret="wrong-secret"), _settings())


def test_tampered_body_is_rejected() -> None:
    with pytest.raises(InvalidPaymentSignatureError):
        verify_payment_webhook_signature(BODY + b" ", _sign(BODY), _settings())


def test_missing_signature_is_rejected() -> None:
    with pytest.raises(InvalidPaymentSignatureError):
        verify_payment_webhook_signature(BODY, None, _settings())


def test_empty_signature_is_rejected() -> None:
    with pytest.raises(InvalidPaymentSignatureError):
        verify_payment_webhook_signature(BODY, "", _settings())


def test_unconfigured_secret_fails_closed() -> None:
    with pytest.raises(PaymentWebhookNotConfiguredError):
        verify_payment_webhook_signature(BODY, _sign(BODY), _settings(secret=None))


def test_error_status_codes() -> None:
    assert PaymentWebhookNotConfiguredError.status_code == 503
    assert InvalidPaymentSignatureError.status_code == 401
