from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OnboardingTaskOut(BaseModel):
    id: str
    org_id: str
    org_name: str
    title: str
    category: str
    sort_order: int
    due_offset_days: int
    completed_at: datetime | None


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1)
    category: Literal["license_agreement", "playbook", "policy", "other"] = "other"
    body: str = Field(min_length=1)


class DocumentOut(BaseModel):
    id: str
    org_id: str
    org_name: str
    title: str
    category: str
    body: str
    created_at: datetime


class OrderLineIn(BaseModel):
    product_id: str
    qty: int = Field(gt=0)


class OrderCreate(BaseModel):
    location_id: str
    lines: list[OrderLineIn] = Field(min_length=1)


class OrderLineOut(BaseModel):
    product_id: str
    product_name: str
    qty: int


class OrderOut(BaseModel):
    id: str
    org_id: str
    org_name: str
    location_id: str
    location_name: str
    status: Literal["draft", "submitted", "fulfilled"]
    submitted_at: datetime | None
    fulfilled_at: datetime | None
    lines: list[OrderLineOut]


class LotAssignment(BaseModel):
    product_id: str
    lot_id: str


class FulfillRequest(BaseModel):
    assignments: list[LotAssignment] = Field(min_length=1)
