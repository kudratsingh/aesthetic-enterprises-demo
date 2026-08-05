from datetime import date

from pydantic import BaseModel


class NetworkPeriodKpis(BaseModel):
    period: date
    leads: int
    consults: int
    sales: int
    treatments_completed: int
    plan_value_cents: int
    reported_net_base_cents: int


class LocationKpiRow(BaseModel):
    location_id: str
    location_name: str
    org_name: str
    months_active: int
    treatments_completed: int
    target_treatments: int
    attainment: float  # completed / target, 0.0 when target is 0
    reported_net_base_cents: int
