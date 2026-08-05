from datetime import date
from typing import Literal

from pydantic import BaseModel


class VarianceFlagOut(BaseModel):
    id: str
    location_id: str
    location_name: str
    org_name: str
    period: date
    reported_net_base_cents: int
    expected_floor_cents: int
    administrations: int
    avg_net_ticket_cents: int
    ratio: float  # reported / floor; < threshold is why the flag exists
    status: Literal["open", "reviewed", "resolved"]
    resolution_reason: str | None


class ComputeVarianceResponse(BaseModel):
    period: date
    threshold: float
    avg_net_ticket_cents: int
    flags: list[VarianceFlagOut]


class ResolveVarianceRequest(BaseModel):
    status: Literal["reviewed", "resolved"]
    reason: str | None = None
