import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings, get_settings
from app.core.security import CurrentUser, HqUser
from app.db.tenancy import TenantSession
from app.schemas.variance import (
    ComputeVarianceResponse,
    ResolveVarianceRequest,
    VarianceFlagOut,
)
from app.services import variance

router = APIRouter(tags=["variance"])


@router.post("/variance/compute")
async def compute_variance(
    user: HqUser,
    session: TenantSession,
    settings: Annotated[Settings, Depends(get_settings)],
    period: Annotated[date, Query(description="first day of month")],
) -> ComputeVarianceResponse:
    return await variance.compute_flags(
        session, settings.network_timezone, period, settings.variance_threshold
    )


@router.get("/variance/flags")
async def list_variance_flags(
    user: CurrentUser,
    session: TenantSession,
    settings: Annotated[Settings, Depends(get_settings)],
    period: Annotated[date | None, Query()] = None,
    status: Annotated[str | None, Query(pattern="^(open|reviewed|resolved)$")] = None,
) -> list[VarianceFlagOut]:
    # Permissions matrix: operators see their own flags in resolved view only;
    # RLS already scopes rows to their org.
    if user.role != "hq_admin":
        status = "resolved"
    return await variance.list_flags(session, settings.network_timezone, period, status)


@router.post("/variance/flags/{flag_id}/resolve")
async def resolve_variance_flag(
    flag_id: uuid.UUID,
    body: ResolveVarianceRequest,
    user: HqUser,
    session: TenantSession,
) -> dict[str, str]:
    await variance.resolve_flag(session, flag_id, body.status, body.reason)
    return {"status": body.status}
