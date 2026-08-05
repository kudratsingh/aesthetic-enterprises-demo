from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings, get_settings
from app.core.security import HqUser
from app.db.tenancy import TenantSession
from app.schemas.kpi import LocationKpiRow, NetworkPeriodKpis
from app.services import funnel

router = APIRouter(tags=["kpi"])


@router.get("/kpi/network")
async def network_kpis(
    user: HqUser,
    session: TenantSession,
    settings: Annotated[Settings, Depends(get_settings)],
    months: Annotated[int, Query(ge=1, le=24)] = 6,
) -> list[NetworkPeriodKpis]:
    return await funnel.network_kpis(session, settings.network_timezone, months)


@router.get("/kpi/locations")
async def location_kpis(
    user: HqUser,
    session: TenantSession,
    settings: Annotated[Settings, Depends(get_settings)],
    period: Annotated[date, Query(description="first day of month")],
) -> list[LocationKpiRow]:
    return await funnel.location_kpis(session, settings.network_timezone, period)
