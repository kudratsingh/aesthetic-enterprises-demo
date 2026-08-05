"""Unit tests for webhook HMAC verification (app.services.ingest).

Pure function, no DB: covers valid / invalid / missing signatures, tampered
bodies, and the fail-closed 503 path when no secret is configured.
"""

import hashlib
import hmac

import pytest

from app.core.config import Settings
from app.services.ingest import (
    InvalidSignatureError,
    WebhookNotConfiguredError,
    verify_webhook_signature,
)

SECRET = "test-webhook-secret"
BODY = b'{"event_type": "contact", "location_id": "00000000-0000-0000-0000-000000000001"}'


def _settings(secret: str | None = SECRET) -> Settings:
    return Settings(ghl_webhook_secret=secret)


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_passes() -> None:
    verify_webhook_signature(BODY, _sign(BODY), _settings())


def test_uppercase_and_padded_signature_passes() -> None:
    verify_webhook_signature(BODY, f"  {_sign(BODY).upper()}  ", _settings())


def test_wrong_secret_is_rejected() -> None:
    with pytest.raises(InvalidSignatureError):
        verify_webhook_signature(BODY, _sign(BODY, secret="wrong-secret"), _settings())


def test_tampered_body_is_rejected() -> None:
    with pytest.raises(InvalidSignatureError):
        verify_webhook_signature(BODY + b" ", _sign(BODY), _settings())


def test_garbage_signature_is_rejected() -> None:
    with pytest.raises(InvalidSignatureError):
        verify_webhook_signature(BODY, "not-a-hex-digest", _settings())


def test_missing_signature_is_rejected() -> None:
    with pytest.raises(InvalidSignatureError):
        verify_webhook_signature(BODY, None, _settings())


def test_empty_signature_is_rejected() -> None:
    with pytest.raises(InvalidSignatureError):
        verify_webhook_signature(BODY, "", _settings())


def test_unconfigured_secret_fails_closed() -> None:
    with pytest.raises(WebhookNotConfiguredError):
        verify_webhook_signature(BODY, _sign(BODY), _settings(secret=None))


def test_error_status_codes() -> None:
    assert WebhookNotConfiguredError.status_code == 503
    assert InvalidSignatureError.status_code == 401
