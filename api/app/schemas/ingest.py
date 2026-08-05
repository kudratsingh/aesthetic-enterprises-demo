"""Request/response models for funnel ingestion (R7, ADR-0005).

The webhook payload shape is the *demo contract* this repo defines for a
GHL-style marketing CRM: every event embeds the full contact (so lead upsert is
always possible), and `location_id` is OUR location UUID, carried by a
licensor-configured custom field in the CRM. Timestamps are ISO 8601; naive
values are interpreted as UTC.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EventType = Literal["contact", "appointment"]
ConsultOutcome = Literal["no_show", "no_sale", "sale"]


def _assume_utc(value: datetime | None) -> datetime | None:
    """Naive timestamps are treated as UTC (storage is UTC; PROJECT_CONTEXT §3)."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class ContactIn(BaseModel):
    external_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    created_at: datetime | None = None

    _created_at_utc = field_validator("created_at")(_assume_utc)


class AppointmentIn(BaseModel):
    # Accepted for forward-compatibility; not persisted in the MVP — consult
    # identity is (lead, scheduled_at). See ADR-0005.
    external_id: str | None = None
    scheduled_at: datetime
    occurred_at: datetime | None = None
    outcome: ConsultOutcome | None = None

    _scheduled_at_utc = field_validator("scheduled_at")(_assume_utc)
    _occurred_at_utc = field_validator("occurred_at")(_assume_utc)


class GhlWebhookPayload(BaseModel):
    """One CRM event. The sender collapses CRM event subtypes (created/updated/
    rescheduled) into two types because ingestion is an idempotent upsert of
    current state either way — we sync state, we don't replay CRM history."""

    event_type: EventType
    location_id: uuid.UUID
    contact: ContactIn
    appointment: AppointmentIn | None = None

    @model_validator(mode="after")
    def _appointment_events_carry_appointment(self) -> "GhlWebhookPayload":
        if self.event_type == "appointment" and self.appointment is None:
            raise ValueError("appointment events must include an appointment object")
        return self


class WebhookResultOut(BaseModel):
    lead_created: bool
    consult_created: bool
    consult_updated: bool


class ImportRowError(BaseModel):
    line: int
    message: str


class LeadImportResultOut(BaseModel):
    imported: int
    skipped: int
    errors: list[ImportRowError]
