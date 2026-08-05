from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser
from app.db.engine import get_session_factory

_SET_TENANT_CONTEXT = text(
    "SELECT set_config('app.org_id', :org_id, true), set_config('app.role', :role, true)"
)


async def get_tenant_session(user: CurrentUser) -> AsyncIterator[AsyncSession]:
    """The only sanctioned path to a DB session for request handlers (CLAUDE.md §2.3).

    Opens one transaction and pins app.org_id / app.role to the verified JWT claims
    for its whole duration — set_config(..., true) is transaction-local, so the
    context can never leak across pooled connections. Every RLS policy keys on
    these settings; there is no code-level tenancy branch anywhere.
    """
    async with get_session_factory()() as session, session.begin():
        await session.execute(_SET_TENANT_CONTEXT, {"org_id": user.org_id, "role": user.role})
        yield session


TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
