"""Request/response models for the royalty cycle. Money is integer cents; rates
are Decimal strings; periods are the first day of a calendar month."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ReportStatus = Literal["draft", "submitted", "locked"]
InvoiceStatus = Literal["issued", "paid", "overdue"]
AgingBucketName = Literal["0-30", "31-60", "61-90", "90+"]


def _validate_period(value: date) -> date:
    if value.day != 1:
        raise ValueError("period must be the first day of a calendar month")
    return value


class RevenueReportCreate(BaseModel):
    location_id: uuid.UUID
    period: date
    gross_cents: int = Field(ge=0)
    refunds_cents: int = Field(ge=0)

    _period_first_of_month = field_validator("period")(_validate_period)


class RevenueReportUpdate(BaseModel):
    gross_cents: int = Field(ge=0)
    refunds_cents: int = Field(ge=0)


class RevenueReportOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    location_id: uuid.UUID
    period: date
    gross_cents: int
    refunds_cents: int
    net_base_cents: int
    status: ReportStatus
    attested_by: uuid.UUID | None
    attested_at: datetime | None
    supersedes: uuid.UUID | None
    created_at: datetime


class RoyaltyRunRequest(BaseModel):
    period: date

    _period_first_of_month = field_validator("period")(_validate_period)


class RunExclusionOut(BaseModel):
    location_id: uuid.UUID
    org_id: uuid.UUID
    reason: str


class RoyaltyLineItemOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    org_id: uuid.UUID
    location_id: uuid.UUID
    base_cents: int
    rate: Decimal
    minimum_applied: bool
    adjustments_cents: int
    amount_due_cents: int


class RoyaltyRunOut(BaseModel):
    id: uuid.UUID
    period: date
    version: int
    input_fingerprint: str
    generated_at: datetime
    reused: bool = Field(
        description="True when idempotency returned an existing version instead of creating one"
    )
    line_items: list[RoyaltyLineItemOut]
    exclusions: list[RunExclusionOut]


class RoyaltyRunSummaryOut(BaseModel):
    id: uuid.UUID
    period: date
    version: int
    input_fingerprint: str
    generated_at: datetime


class InvoiceOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    org_id: uuid.UUID
    amount_due_cents: int
    status: InvoiceStatus
    due_date: date
    issued_at: datetime
    superseded_by: uuid.UUID | None


class IssueInvoicesOut(BaseModel):
    run_id: uuid.UUID
    reused: bool = Field(
        description="True when invoices for this run already existed and were returned as-is"
    )
    invoices: list[InvoiceOut]


class AgingInvoiceOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    run_id: uuid.UUID
    amount_due_cents: int
    due_date: date
    issued_at: datetime
    days_outstanding: int
    bucket: AgingBucketName


class AgingBucketOut(BaseModel):
    bucket: AgingBucketName
    invoice_count: int
    amount_due_cents: int


class AgingOut(BaseModel):
    as_of: date
    buckets: list[AgingBucketOut]
    invoices: list[AgingInvoiceOut]
