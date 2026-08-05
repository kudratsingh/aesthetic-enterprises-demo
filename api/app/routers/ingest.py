"""Funnel ingestion endpoints — thin HTTP layer over app.services.ingest.

Both take the RAW request body on purpose: the webhook's HMAC covers the exact
bytes sent, and the CSV import is text/csv, not JSON. Verification, parsing,
and all domain rules live in the service (R7, ADR-0005).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings, get_settings
from app.core.security import CurrentUser
from app.db.tenancy import TenantSession
from app.schemas.ingest import LeadImportResultOut, WebhookResultOut
from app.services import ingest

router = APIRouter(tags=["ingest"])


@router.post("/webhooks/ghl")
async def ghl_webhook(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> WebhookResultOut:
    """HMAC-verified CRM event → idempotent lead/consult upsert.

    No JWT: authentication is the HMAC-SHA256 signature of the raw body in the
    X-Webhook-Signature header (401 on mismatch, 503 if no secret configured).
    Payload shape: docs/runbooks/integrations.md.
    """
    return await ingest.process_ghl_webhook(
        await request.body(), request.headers.get(ingest.SIGNATURE_HEADER), settings
    )


@router.post("/imports/leads")
async def import_leads(
    request: Request, user: CurrentUser, session: TenantSession
) -> LeadImportResultOut:
    """Bulk lead import from a raw text/csv body (hq_admin only).

    Columns: source, external_id, location_id[, created_at] — same idempotent
    upsert path as the webhook. Returns imported/skipped counts and per-row
    errors keyed by CSV line number.
    """
    return await ingest.import_leads_csv(session, user, await request.body())
