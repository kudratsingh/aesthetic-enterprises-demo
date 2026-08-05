"""Funnel ingestion (Phase 5, R7, ADR-0005): HMAC-verified GHL-style webhook
and HQ CSV lead import, both landing on one idempotent upsert path.

Rules encoded here:
- Lead identity is (source, external_id); the partial unique index
  `uq_leads_source_external_id` makes replays no-ops (ON CONFLICT DO NOTHING —
  first write wins; a lead is a point-in-time acquisition fact).
- Consult identity is (lead, scheduled_at); replays update only non-null
  mutable fields (occurred_at, outcome) — monotone enrichment, so out-of-order
  deliveries can never erase state. See ADR-0005 for why consults carry no
  external_id column in the MVP.
- Ingestion runs in an hq_admin RLS context via the standard set_config
  pattern (ADR-0002): licensor-managed systems feed the funnel, rows carry the
  destination location's org_id, and every policy still applies — no bypass.
- Ingestion NEVER touches royalty or supply aggregates (R7); it only feeds the
  funnel/KPI layer.

Typed domain errors live in this module (not core/errors.py) because they are
ingestion-specific; main.py translates them like any other DomainError.
"""

import csv
import hashlib
import hmac
import io
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pydantic
import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import DomainError, RoleForbiddenError
from app.core.security import TokenClaims
from app.db.engine import get_session_factory
from app.db.models import Consult, Lead, Location
from app.schemas.ingest import (
    AppointmentIn,
    GhlWebhookPayload,
    ImportRowError,
    LeadImportResultOut,
    WebhookResultOut,
)

log = structlog.get_logger()

SIGNATURE_HEADER = "X-Webhook-Signature"

# ---------------------------------------------------------------------------
# Ingestion-specific domain errors (module-local by design; see docstring)
# ---------------------------------------------------------------------------


class WebhookNotConfiguredError(DomainError):
    """GHL_WEBHOOK_SECRET is unset — fail closed, never accept unsigned events."""

    code = "webhook_not_configured"
    status_code = 503


class InvalidSignatureError(DomainError):
    """Missing or mismatched HMAC signature on the raw request body."""

    code = "invalid_signature"
    status_code = 401


class PayloadError(DomainError):
    """Body is not valid JSON or does not match the documented payload shape."""

    code = "invalid_payload"
    status_code = 400


class UnknownLocationError(DomainError):
    """Payload references a location UUID this network does not know."""

    code = "unknown_location"
    status_code = 400


class ImportFormatError(DomainError):
    """CSV body is undecodable or missing required header columns."""

    code = "import_format"
    status_code = 400


# ---------------------------------------------------------------------------
# Signature verification (unit-tested directly; tests/unit/test_ingest_signature.py)
# ---------------------------------------------------------------------------


def verify_webhook_signature(raw_body: bytes, signature: str | None, settings: Settings) -> None:
    """HMAC-SHA256 over the raw body, hex-encoded, constant-time compare.

    Raw body (not parsed/re-serialized JSON) so the signed bytes are exactly
    what the sender hashed. 503 when no secret is configured — a deploy that
    forgot the secret must reject events loudly, not accept them silently.
    """
    if not settings.ghl_webhook_secret:
        raise WebhookNotConfiguredError("webhook secret is not configured")
    if not signature:
        raise InvalidSignatureError(f"missing {SIGNATURE_HEADER} header")
    expected = hmac.new(settings.ghl_webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.strip().lower()):
        raise InvalidSignatureError("signature mismatch")


# ---------------------------------------------------------------------------
# Tenancy context for machine ingestion (no JWT on webhooks)
# ---------------------------------------------------------------------------

_SET_INGEST_CONTEXT = text(
    "SELECT set_config('app.org_id', '', true), set_config('app.role', 'hq_admin', true)"
)


@asynccontextmanager
async def _ingest_session() -> AsyncIterator[AsyncSession]:
    """hq_admin RLS context via the standard set_config pattern (ADR-0002/0005).

    Webhooks carry no JWT, so this mirrors app.db.tenancy.get_tenant_session
    with the role every policy already knows: licensor-managed marketing
    systems feed the funnel, authenticated by the HMAC shared secret, acting as
    the licensor. app.org_id is set to '' (reads as NULL through the policies'
    NULLIF) — the hq_admin role clause is what grants access. RLS remains
    enabled and enforced; this is a policy-level role, not a bypass.
    """
    async with get_session_factory()() as session, session.begin():
        await session.execute(_SET_INGEST_CONTEXT)
        yield session


# ---------------------------------------------------------------------------
# Shared upsert path (webhook and CSV both land here)
# ---------------------------------------------------------------------------


async def _location_org(session: AsyncSession, location_id: uuid.UUID) -> uuid.UUID | None:
    return (
        await session.execute(select(Location.org_id).where(Location.id == location_id))
    ).scalar_one_or_none()


async def _upsert_lead(
    session: AsyncSession,
    org_id: uuid.UUID,
    location_id: uuid.UUID,
    source: str,
    external_id: str,
    created_at: datetime | None,
) -> tuple[uuid.UUID, bool]:
    """Insert-if-absent on the (source, external_id) partial unique index.

    Returns (lead_id, created). First write wins: a replay (or a re-import)
    hits ON CONFLICT DO NOTHING and the original row — including its original
    location attribution — stands. RETURNING only yields a row when the insert
    actually happened, which is the created signal.
    """
    values: dict[str, object] = {
        "org_id": org_id,
        "location_id": location_id,
        "source": source,
        "external_id": external_id,
    }
    if created_at is not None:
        values["created_at"] = created_at
    stmt = (
        pg_insert(Lead)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=[Lead.source, Lead.external_id],
            index_where=Lead.external_id.is_not(None),
        )
        .returning(Lead.id)
    )
    lead_id: uuid.UUID | None = (await session.execute(stmt)).scalar_one_or_none()
    if lead_id is not None:
        return lead_id, True
    existing: uuid.UUID = (
        await session.execute(
            select(Lead.id).where(Lead.source == source, Lead.external_id == external_id)
        )
    ).scalar_one()
    return existing, False


async def _upsert_consult(
    session: AsyncSession,
    org_id: uuid.UUID,
    location_id: uuid.UUID,
    lead_id: uuid.UUID,
    appointment: AppointmentIn,
) -> tuple[bool, bool]:
    """Consult keyed by (lead, scheduled_at); returns (created, updated).

    Replays update only non-null mutable fields that actually differ
    (occurred_at, outcome) — fields gain information, never lose it, so an
    out-of-order "booked" event cannot erase a completed consult's outcome.
    The original row's location attribution stands, like the lead's.
    """
    consult = (
        (
            await session.execute(
                select(Consult)
                .where(Consult.lead_id == lead_id, Consult.scheduled_at == appointment.scheduled_at)
                .order_by(Consult.created_at)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if consult is None:
        session.add(
            Consult(
                org_id=org_id,
                location_id=location_id,
                lead_id=lead_id,
                scheduled_at=appointment.scheduled_at,
                occurred_at=appointment.occurred_at,
                outcome=appointment.outcome,
            )
        )
        await session.flush()
        return True, False

    updated = False
    if appointment.occurred_at is not None and consult.occurred_at != appointment.occurred_at:
        consult.occurred_at = appointment.occurred_at
        updated = True
    if appointment.outcome is not None and consult.outcome != appointment.outcome:
        consult.outcome = appointment.outcome
        updated = True
    if updated:
        await session.flush()
    return False, updated


# ---------------------------------------------------------------------------
# Webhook entry point
# ---------------------------------------------------------------------------


def _parse_webhook_payload(raw_body: bytes) -> GhlWebhookPayload:
    try:
        data = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PayloadError("body is not valid JSON") from exc
    try:
        return GhlWebhookPayload.model_validate(data)
    except pydantic.ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "payload"
        raise PayloadError(f"invalid payload: {where}: {first['msg']}") from exc


async def process_ghl_webhook(
    raw_body: bytes, signature: str | None, settings: Settings
) -> WebhookResultOut:
    """Verify, parse, and upsert one CRM event into the funnel (R7)."""
    verify_webhook_signature(raw_body, signature, settings)
    payload = _parse_webhook_payload(raw_body)

    async with _ingest_session() as session:
        org_id = await _location_org(session, payload.location_id)
        if org_id is None:
            raise UnknownLocationError(f"unknown location {payload.location_id}")

        lead_id, lead_created = await _upsert_lead(
            session,
            org_id,
            payload.location_id,
            payload.contact.source,
            payload.contact.external_id,
            payload.contact.created_at,
        )
        consult_created = consult_updated = False
        if payload.event_type == "appointment" and payload.appointment is not None:
            consult_created, consult_updated = await _upsert_consult(
                session, org_id, payload.location_id, lead_id, payload.appointment
            )

    log.info(
        "ghl_webhook_processed",
        event_type=payload.event_type,
        lead_created=lead_created,
        consult_created=consult_created,
        consult_updated=consult_updated,
    )
    return WebhookResultOut(
        lead_created=lead_created,
        consult_created=consult_created,
        consult_updated=consult_updated,
    )


# ---------------------------------------------------------------------------
# CSV lead import (HQ only; documented in docs/runbooks/integrations.md)
# ---------------------------------------------------------------------------

CSV_REQUIRED_COLUMNS = ("source", "external_id", "location_id")
CSV_OPTIONAL_COLUMNS = ("created_at",)


def _parse_row_created_at(value: str) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


async def import_leads_csv(
    session: AsyncSession, actor: TokenClaims, raw_body: bytes
) -> LeadImportResultOut:
    """Bulk lead import over the same idempotent upsert path as the webhook.

    Runs on the caller's tenant session — the endpoint is HQ-only, so that IS
    the hq_admin RLS context. Row-level tolerance: malformed rows are reported
    with their line number and skipped; well-formed rows still land. Duplicates
    (already-known (source, external_id)) count as skipped, not errors.
    """
    if actor.role != "hq_admin":
        raise RoleForbiddenError("lead import is restricted to hq_admin")

    try:
        content = raw_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ImportFormatError("body must be UTF-8 encoded CSV") from exc

    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None:
        raise ImportFormatError("empty CSV body")
    missing = [c for c in CSV_REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise ImportFormatError(f"missing required column(s): {', '.join(missing)}")

    imported = skipped = 0
    errors: list[ImportRowError] = []
    location_orgs: dict[uuid.UUID, uuid.UUID | None] = {}

    for row in reader:
        line = reader.line_num
        source = (row.get("source") or "").strip()
        external_id = (row.get("external_id") or "").strip()
        if not source or not external_id:
            errors.append(ImportRowError(line=line, message="source and external_id are required"))
            continue
        try:
            location_id = uuid.UUID((row.get("location_id") or "").strip())
        except ValueError:
            errors.append(ImportRowError(line=line, message="location_id is not a valid UUID"))
            continue
        try:
            created_at = _parse_row_created_at((row.get("created_at") or "").strip())
        except ValueError:
            errors.append(
                ImportRowError(line=line, message="created_at is not a valid ISO 8601 timestamp")
            )
            continue

        if location_id not in location_orgs:
            location_orgs[location_id] = await _location_org(session, location_id)
        org_id = location_orgs[location_id]
        if org_id is None:
            errors.append(ImportRowError(line=line, message=f"unknown location {location_id}"))
            continue

        _, created = await _upsert_lead(
            session, org_id, location_id, source, external_id, created_at
        )
        if created:
            imported += 1
        else:
            skipped += 1

    log.info("leads_csv_imported", imported=imported, skipped=skipped, errors=len(errors))
    return LeadImportResultOut(imported=imported, skipped=skipped, errors=errors)
