from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.core.security import TokenClaims, mint_token
from app.main import app


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def hq_token(settings: Settings) -> str:
    return mint_token(TokenClaims(sub="test-user", org_id="org-hq", role="hq_admin"), settings)
