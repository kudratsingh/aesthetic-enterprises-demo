import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import (
    Base,
    TimestampedTenantMixin,
    cents,
    created_at_col,
    location_fk,
    org_fk,
    uuid_pk,
)


class Product(Base):
    """Network-shared catalog: readable by all tenants, HQ-writable (single
    network-wide price list, assumption A6)."""

    __tablename__ = "products"

    id: Mapped[uuid_pk]
    sku: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False, default="vial")
    price_cents: Mapped[cents]
    created_at: Mapped[created_at_col]


class Lot(Base):
    """Network-shared: operators must resolve lots on shipments they receive."""

    __tablename__ = "lots"

    id: Mapped[uuid_pk]
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    lot_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    supplier: Mapped[str] = mapped_column(Text, nullable=False)
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[created_at_col]


class Shipment(Base, TimestampedTenantMixin):
    """Append-only ledger row (ADR-0003): lot quantity moved to a location.
    Corrections are reversing entries (negative qty, reversal_of set)."""

    __tablename__ = "shipments"
    __table_args__ = (CheckConstraint("qty <> 0", name="ck_shipments_qty_nonzero"),)

    location_id: Mapped[location_fk]
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lots.id"), nullable=False, index=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    shipped_at: Mapped[datetime] = mapped_column(nullable=False)
    reversal_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shipments.id"), nullable=True)


class Administration(Base, TimestampedTenantMixin):
    """Append-only ledger row (ADR-0003): one treatment consuming product from a
    specific lot. Only opaque synthetic_patient_ref — never PHI."""

    __tablename__ = "administrations"
    __table_args__ = (CheckConstraint("qty <> 0", name="ck_administrations_qty_nonzero"),)

    location_id: Mapped[location_fk]
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lots.id"), nullable=False, index=True)
    treatment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("treatments.id"), nullable=True, index=True
    )
    synthetic_patient_ref: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    administered_at: Mapped[datetime] = mapped_column(nullable=False)
    reversal_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("administrations.id"), nullable=True
    )


class LocationLotOnHand(Base):
    """Trigger-maintained balance per (location, lot). The CHECK here is
    invariant 1: the ledger can never drive on-hand negative (DB-enforced)."""

    __tablename__ = "location_lot_on_hand"
    __table_args__ = (CheckConstraint("on_hand >= 0", name="ck_on_hand_non_negative"),)

    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), primary_key=True)
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lots.id"), primary_key=True)
    org_id: Mapped[org_fk]
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False)
