from functools import lru_cache

from sqlalchemy import text
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


async def connected_role_bypasses_rls() -> bool:
    """True when the app's DB role would skip RLS policies entirely.

    SUPERUSER and BYPASSRLS both do — and FORCE ROW LEVEL SECURITY does NOT
    defend against the BYPASSRLS *attribute* (learned the hard way: Neon grants
    BYPASSRLS to the database owner, so an app connecting as neondb_owner runs
    with tenancy silently off; see ADR-0002 amendment). The startup guard uses
    this to refuse such a connection in prod.
    """
    async with get_engine().connect() as conn:
        result = (
            await conn.execute(
                text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
        ).scalar_one()
    return bool(result)
