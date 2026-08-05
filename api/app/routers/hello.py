from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.security import CurrentUser
from app.db.tenancy import TenantSession
from app.schemas.hello import HelloResponse
from app.services.hello import hello_roundtrip

router = APIRouter(tags=["hello"])


@router.get("/hello")
async def hello(
    user: CurrentUser,
    session: TenantSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> HelloResponse:
    return await hello_roundtrip(session, user, settings.environment)
