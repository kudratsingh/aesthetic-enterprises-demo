from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenClaims
from app.schemas.hello import HelloResponse


async def hello_roundtrip(
    session: AsyncSession, user: TokenClaims, environment: str
) -> HelloResponse:
    db_time = (await session.execute(text("SELECT now()"))).scalar_one()
    return HelloResponse(
        message=f"Hello {user.sub} ({user.role}) — round trip web → api → db complete.",
        db_time=db_time,
        environment=environment,
    )
