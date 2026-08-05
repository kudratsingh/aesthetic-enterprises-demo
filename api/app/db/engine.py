from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Request handlers must not use this directly — go through
    app.db.tenancy.TenantSession so the RLS context is always set (CLAUDE.md §2.3).
    Only the auth service (pre-tenant login lookup) opens sessions here."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)
