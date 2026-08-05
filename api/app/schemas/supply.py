from datetime import date, datetime

from pydantic import BaseModel, Field


class ProductOut(BaseModel):
    id: str
    sku: str
    name: str
    unit: str
    price_cents: int


class ReceiveLotRequest(BaseModel):
    product_id: str
    lot_code: str
    supplier: str
    expiry: date


class LotOut(BaseModel):
    id: str
    product_id: str
    product_name: str
    lot_code: str
    supplier: str
    expiry: date


class ShipRequest(BaseModel):
    location_id: str
    lot_id: str
    qty: int = Field(gt=0)


class AdministerRequest(BaseModel):
    location_id: str
    lot_id: str
    synthetic_patient_ref: str
    treatment_id: str | None = None
    qty: int = Field(default=1, gt=0)


class OnHandRow(BaseModel):
    location_id: str
    location_name: str
    lot_id: str
    lot_code: str
    product_name: str
    expiry: date
    on_hand: int


class RecallRow(BaseModel):
    administration_id: str
    location_name: str
    org_name: str
    synthetic_patient_ref: str
    qty: int
    administered_at: datetime


class RecallResponse(BaseModel):
    lot_id: str
    lot_code: str
    product_name: str
    supplier: str
    expiry: date
    total_administrations: int
    rows: list[RecallRow]
