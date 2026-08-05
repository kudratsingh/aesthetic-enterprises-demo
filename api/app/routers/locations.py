from fastapi import APIRouter

from app.core.security import CurrentUser
from app.db.tenancy import TenantSession
from app.schemas.locations import LocationOut
from app.services import identity

router = APIRouter(tags=["locations"])


@router.get("/locations")
async def list_locations(user: CurrentUser, session: TenantSession) -> list[LocationOut]:
    return await identity.list_locations(session)
