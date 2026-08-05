from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import CurrentUser
from app.db.engine import get_session
from app.schemas.hello import HelloResponse
from app.services.hello import hello_roundtrip

router = APIRouter(tags=["hello"])


@router.get("/hello")
async def hello(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HelloResponse:
    return await hello_roundtrip(session, user, settings.environment)
