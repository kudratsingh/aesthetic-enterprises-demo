"""Supply chain operations on the append-only ledger (ADR-0003).

Receive (HQ) → ship (HQ) → administer (operator/staff) → recall/on-hand queries.
Stock floors are DB-enforced (invariant 1); this layer adds the business rules
the database can't know: expired lots can't be administered (R6), shipments only
target real locations.
"""

import uuid as uuidlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.errors import DomainError
from app.schemas.supply import (
    AdministerRequest,
    LotOut,
    OnHandRow,
    ProductOut,
    RecallResponse,
    RecallRow,
    ReceiveLotRequest,
    ShipRequest,
)


class SupplyNotFoundError(DomainError):
    code = "supply_not_found"
    status_code = 404


class ExpiredLotError(DomainError):
    code = "expired_lot"
    status_code = 422


class InsufficientStockError(DomainError):
    code = "insufficient_stock"
    status_code = 409


def _parse_uuid(value: str, what: str) -> UUID:
    try:
        return uuidlib.UUID(value)
    except ValueError as exc:
        raise SupplyNotFoundError(f"{what} is not a valid id") from exc


async def list_products(session: AsyncSession) -> list[ProductOut]:
    rows = (
        await session.execute(
            text("SELECT id, sku, name, unit, price_cents FROM products ORDER BY sku")
        )
    ).all()
    return [
        ProductOut(id=str(i), sku=sku, name=name, unit=unit, price_cents=price)
        for i, sku, name, unit, price in rows
    ]


async def list_lots(session: AsyncSession) -> list[LotOut]:
    rows = (
        await session.execute(
            text(
                "SELECT lo.id, lo.product_id, p.name, lo.lot_code, lo.supplier, lo.expiry"
                "  FROM lots lo JOIN products p ON p.id = lo.product_id"
                " ORDER BY lo.lot_code"
            )
        )
    ).all()
    return [
        LotOut(
            id=str(i),
            product_id=str(pid),
            product_name=pname,
            lot_code=code,
            supplier=supplier,
            expiry=expiry,
        )
        for i, pid, pname, code, supplier, expiry in rows
    ]


async def receive_lot(session: AsyncSession, req: ReceiveLotRequest) -> LotOut:
    product = (
        await session.execute(
            text("SELECT id, name FROM products WHERE id = :id"),
            {"id": _parse_uuid(req.product_id, "product_id")},
        )
    ).one_or_none()
    if product is None:
        raise SupplyNotFoundError("product not found")
    lot_id = uuid7()
    await session.execute(
        text(
            "INSERT INTO lots (id, product_id, lot_code, supplier, expiry)"
            " VALUES (:id, :product_id, :lot_code, :supplier, :expiry)"
        ),
        {
            "id": lot_id,
            "product_id": product.id,
            "lot_code": req.lot_code,
            "supplier": req.supplier,
            "expiry": req.expiry,
        },
    )
    return LotOut(
        id=str(lot_id),
        product_id=str(product.id),
        product_name=product.name,
        lot_code=req.lot_code,
        supplier=req.supplier,
        expiry=req.expiry,
    )


async def ship(session: AsyncSession, req: ShipRequest) -> None:
    """HQ ships lot quantity to a location; org_id derives from the location so
    the on-hand row lands in the receiving tenant."""
    loc = (
        await session.execute(
            text("SELECT id, org_id FROM locations WHERE id = :id"),
            {"id": _parse_uuid(req.location_id, "location_id")},
        )
    ).one_or_none()
    if loc is None:
        raise SupplyNotFoundError("location not found")
    lot = (
        await session.execute(
            text("SELECT id FROM lots WHERE id = :id"),
            {"id": _parse_uuid(req.lot_id, "lot_id")},
        )
    ).one_or_none()
    if lot is None:
        raise SupplyNotFoundError("lot not found")
    await session.execute(
        text(
            "INSERT INTO shipments (id, org_id, location_id, lot_id, qty, shipped_at)"
            " VALUES (:id, :org, :loc, :lot, :qty, :at)"
        ),
        {
            "id": uuid7(),
            "org": loc.org_id,
            "loc": loc.id,
            "lot": lot.id,
            "qty": req.qty,
            "at": datetime.now(UTC),
        },
    )


async def administer(session: AsyncSession, org_id: str, req: AdministerRequest) -> None:
    """Record one administration. Expiry is checked here (R6); the stock floor
    is the database's job (invariant 1) — we translate its refusal."""
    now = datetime.now(UTC)
    lot = (
        await session.execute(
            text("SELECT id, expiry, lot_code FROM lots WHERE id = :id"),
            {"id": _parse_uuid(req.lot_id, "lot_id")},
        )
    ).one_or_none()
    if lot is None:
        raise SupplyNotFoundError("lot not found")
    if lot.expiry <= now.date():
        raise ExpiredLotError(f"lot {lot.lot_code} expired {lot.expiry.isoformat()}")

    try:
        await session.execute(
            text(
                "INSERT INTO administrations (id, org_id, location_id, lot_id, treatment_id,"
                " synthetic_patient_ref, qty, administered_at)"
                " VALUES (:id, :org, :loc, :lot, :treatment, :ref, :qty, :at)"
            ),
            {
                "id": uuid7(),
                "org": UUID(org_id),
                "loc": _parse_uuid(req.location_id, "location_id"),
                "lot": lot.id,
                "treatment": (
                    _parse_uuid(req.treatment_id, "treatment_id")
                    if req.treatment_id is not None
                    else None
                ),
                "ref": req.synthetic_patient_ref,
                "qty": req.qty,
                "at": now,
            },
        )
    except IntegrityError as exc:
        if "ck_on_hand_non_negative" in str(exc):
            raise InsufficientStockError(
                f"insufficient on-hand for lot {lot.lot_code} at this location"
            ) from exc
        raise


async def on_hand(session: AsyncSession) -> list[OnHandRow]:
    """Balances visible in the caller's tenant context (RLS scopes rows)."""
    rows = (
        await session.execute(
            text(
                """
                SELECT b.location_id, l.name, b.lot_id, lo.lot_code, p.name, lo.expiry, b.on_hand
                  FROM location_lot_on_hand b
                  JOIN locations l ON l.id = b.location_id
                  JOIN lots lo ON lo.id = b.lot_id
                  JOIN products p ON p.id = lo.product_id
                 ORDER BY l.name, lo.lot_code
                """
            )
        )
    ).all()
    return [
        OnHandRow(
            location_id=str(loc_id),
            location_name=loc_name,
            lot_id=str(lot_id),
            lot_code=lot_code,
            product_name=product_name,
            expiry=expiry,
            on_hand=qty,
        )
        for loc_id, loc_name, lot_id, lot_code, product_name, expiry, qty in rows
    ]


async def recall(session: AsyncSession, lot_id: str) -> RecallResponse:
    """One query, any time window: every administration that used lot X."""
    lot = (
        await session.execute(
            text(
                "SELECT lo.id, lo.lot_code, p.name, lo.supplier, lo.expiry"
                "  FROM lots lo JOIN products p ON p.id = lo.product_id WHERE lo.id = :id"
            ),
            {"id": _parse_uuid(lot_id, "lot_id")},
        )
    ).one_or_none()
    if lot is None:
        raise SupplyNotFoundError("lot not found")
    rows = (
        await session.execute(
            text(
                """
                SELECT a.id, l.name, o.name, a.synthetic_patient_ref, a.qty, a.administered_at
                  FROM administrations a
                  JOIN locations l ON l.id = a.location_id
                  JOIN orgs o ON o.id = a.org_id
                 WHERE a.lot_id = :lot
                 ORDER BY a.administered_at
                """
            ),
            {"lot": lot.id},
        )
    ).all()
    return RecallResponse(
        lot_id=str(lot.id),
        lot_code=lot.lot_code,
        product_name=lot.name,
        supplier=lot.supplier,
        expiry=lot.expiry,
        total_administrations=len(rows),
        rows=[
            RecallRow(
                administration_id=str(aid),
                location_name=loc_name,
                org_name=org_name,
                synthetic_patient_ref=ref,
                qty=qty,
                administered_at=at,
            )
            for aid, loc_name, org_name, ref, qty, at in rows
        ],
    )
