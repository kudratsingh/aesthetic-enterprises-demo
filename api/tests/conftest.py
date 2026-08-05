import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import Role, TokenClaims, mint_token
from app.db.engine import get_session_factory
from app.main import app

# Stable context for tests acting as HQ; policies check only the role for HQ.
HQ_ORG_ID = "00000000-0000-0000-0000-00000000c105"


def unique(prefix: str) -> str:
    """Collision-free names so integration tests can append to a shared DB."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@asynccontextmanager
async def tenant_session(org_id: str, role: Role) -> AsyncIterator[AsyncSession]:
    """Mirror of app.db.tenancy.get_tenant_session for direct test access."""
    async with get_session_factory()() as session, session.begin():
        await session.execute(
            text(
                "SELECT set_config('app.org_id', :org_id, true),"
                " set_config('app.role', :role, true)"
            ),
            {"org_id": org_id, "role": role},
        )
        yield session


@asynccontextmanager
async def plain_session() -> AsyncIterator[AsyncSession]:
    """Session with NO tenant context — used to prove RLS denies by default."""
    async with get_session_factory()() as session, session.begin():
        yield session


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def hq_token(settings: Settings) -> str:
    return mint_token(TokenClaims(sub="test-user", org_id=HQ_ORG_ID, role="hq_admin"), settings)
