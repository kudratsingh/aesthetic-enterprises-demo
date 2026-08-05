from fastapi import APIRouter

from app.core.security import CurrentUser, HqUser
from app.db.tenancy import TenantSession
from app.schemas.supply import (
    AdministerRequest,
    LotOut,
    OnHandRow,
    ProductOut,
    RecallResponse,
    ReceiveLotRequest,
    ShipRequest,
)
from app.services import supply

router = APIRouter(tags=["supply"])


@router.get("/supply/products")
async def list_products(user: CurrentUser, session: TenantSession) -> list[ProductOut]:
    return await supply.list_products(session)


@router.get("/supply/lots")
async def list_lots(user: CurrentUser, session: TenantSession) -> list[LotOut]:
    return await supply.list_lots(session)


@router.post("/supply/lots", status_code=201)
async def receive_lot(body: ReceiveLotRequest, user: HqUser, session: TenantSession) -> LotOut:
    return await supply.receive_lot(session, body)


@router.post("/supply/shipments", status_code=201)
async def ship(body: ShipRequest, user: HqUser, session: TenantSession) -> dict[str, str]:
    await supply.ship(session, body)
    return {"status": "shipped"}


@router.post("/supply/administrations", status_code=201)
async def administer(
    body: AdministerRequest, user: CurrentUser, session: TenantSession
) -> dict[str, str]:
    await supply.administer(session, user.org_id, body)
    return {"status": "recorded"}


@router.get("/supply/on-hand")
async def on_hand(user: CurrentUser, session: TenantSession) -> list[OnHandRow]:
    return await supply.on_hand(session)


@router.get("/supply/recall/{lot_id}")
async def recall(lot_id: str, user: CurrentUser, session: TenantSession) -> RecallResponse:
    return await supply.recall(session, lot_id)
