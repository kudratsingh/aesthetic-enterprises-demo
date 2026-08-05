import uuid

from fastapi import APIRouter

from app.core.security import CurrentUser, HqUser
from app.db.tenancy import TenantSession
from app.schemas.portal import (
    DocumentCreate,
    DocumentOut,
    FulfillRequest,
    OnboardingTaskOut,
    OrderCreate,
    OrderOut,
)
from app.services import portal

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/onboarding")
async def list_onboarding(user: CurrentUser, session: TenantSession) -> list[OnboardingTaskOut]:
    return await portal.list_onboarding(session)


@router.post("/onboarding/{task_id}/complete")
async def complete_onboarding_task(
    task_id: uuid.UUID, user: CurrentUser, session: TenantSession
) -> dict[str, str]:
    await portal.complete_task(session, user, task_id)
    return {"status": "completed"}


@router.get("/documents")
async def list_documents(user: CurrentUser, session: TenantSession) -> list[DocumentOut]:
    return await portal.list_documents(session)


@router.post("/documents", status_code=201)
async def create_document(
    body: DocumentCreate, user: CurrentUser, session: TenantSession
) -> DocumentOut:
    return await portal.create_document(session, user, body)


@router.get("/orders")
async def list_orders(user: CurrentUser, session: TenantSession) -> list[OrderOut]:
    return await portal.list_orders(session)


@router.post("/orders", status_code=201)
async def create_order(body: OrderCreate, user: CurrentUser, session: TenantSession) -> OrderOut:
    return await portal.create_order(session, user, body)


@router.post("/orders/{order_id}/submit")
async def submit_order(order_id: uuid.UUID, user: CurrentUser, session: TenantSession) -> OrderOut:
    return await portal.submit_order(session, order_id)


@router.post("/orders/{order_id}/fulfill")
async def fulfill_order(
    order_id: uuid.UUID, body: FulfillRequest, user: HqUser, session: TenantSession
) -> OrderOut:
    """HQ fulfillment writes real shipments into the supply ledger (ADR-0003)."""
    return await portal.fulfill_order(session, user, order_id, body)
