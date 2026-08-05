"""Network KPI aggregation vs ramp targets (Phase 4, ADR-0008).

Targets are a formula, not a table: plateau expectation scaled by the same ramp
curve the seed world grows on. Month bucketing happens in the network timezone
(assumption A4) — storage stays UTC.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.kpi import LocationKpiRow, NetworkPeriodKpis

# Demo-shaped plateau mirroring PROJECT_CONTEXT §7; a real network would source
# per-location targets from license agreements (ADR-0008 records the tradeoff).
TARGET_TREATMENTS_PLATEAU = 28
RAMP_FLOOR = 0.3
RAMP_SLOPE = 0.06


def months_active(activated_on: date, period: date) -> int:
    return (period.year - activated_on.year) * 12 + (period.month - activated_on.month) + 1


def ramp_fraction(months: int) -> float:
    if months <= 0:
        return 0.0
    return min(1.0, RAMP_FLOOR + RAMP_SLOPE * months)


def target_treatments(months: int) -> int:
    return round(TARGET_TREATMENTS_PLATEAU * ramp_fraction(months))


async def network_kpis(session: AsyncSession, tz: str, months: int) -> list[NetworkPeriodKpis]:
    """Per-month network totals across the funnel + reported revenue."""
    rows = (
        await session.execute(
            text(
                """
                WITH months AS (
                    -- The month spine unions every source: a period with reports
                    -- but no leads (or vice versa) must still get a row.
                    SELECT date_trunc('month', created_at AT TIME ZONE :tz)::date AS p
                      FROM leads
                     UNION
                    SELECT date_trunc('month', scheduled_at AT TIME ZONE :tz)::date
                      FROM consults
                     UNION
                    SELECT date_trunc('month', sold_at AT TIME ZONE :tz)::date
                      FROM sales
                     UNION
                    SELECT date_trunc('month', completed_at AT TIME ZONE :tz)::date
                      FROM treatments WHERE completed_at IS NOT NULL
                     UNION
                    SELECT period FROM revenue_reports WHERE status = 'locked'
                ),
                lead_agg AS (
                    SELECT date_trunc('month', created_at AT TIME ZONE :tz)::date AS p,
                           count(*) AS n
                      FROM leads GROUP BY 1
                ),
                consult_agg AS (
                    SELECT date_trunc('month', scheduled_at AT TIME ZONE :tz)::date AS p,
                           count(*) AS n
                      FROM consults GROUP BY 1
                ),
                sale_agg AS (
                    SELECT date_trunc('month', sold_at AT TIME ZONE :tz)::date AS p,
                           count(*) AS n, coalesce(sum(plan_value_cents), 0) AS plan_value
                      FROM sales GROUP BY 1
                ),
                treatment_agg AS (
                    SELECT date_trunc('month', completed_at AT TIME ZONE :tz)::date AS p,
                           count(*) AS n
                      FROM treatments WHERE completed_at IS NOT NULL GROUP BY 1
                ),
                report_agg AS (
                    SELECT period AS p, coalesce(sum(net_base_cents), 0) AS net_base
                      FROM revenue_reports WHERE status = 'locked' GROUP BY 1
                )
                SELECT m.p,
                       coalesce(l.n, 0), coalesce(c.n, 0), coalesce(s.n, 0),
                       coalesce(t.n, 0), coalesce(s.plan_value, 0), coalesce(r.net_base, 0)
                  FROM months m
                  LEFT JOIN lead_agg l ON l.p = m.p
                  LEFT JOIN consult_agg c ON c.p = m.p
                  LEFT JOIN sale_agg s ON s.p = m.p
                  LEFT JOIN treatment_agg t ON t.p = m.p
                  LEFT JOIN report_agg r ON r.p = m.p
                 ORDER BY m.p DESC
                 LIMIT :months
                """
            ),
            {"tz": tz, "months": months},
        )
    ).all()
    return [
        NetworkPeriodKpis(
            period=p,
            leads=leads,
            consults=consults,
            sales=sales,
            treatments_completed=treatments,
            plan_value_cents=plan_value,
            reported_net_base_cents=net_base,
        )
        for p, leads, consults, sales, treatments, plan_value, net_base in rows
    ]


async def location_kpis(session: AsyncSession, tz: str, period: date) -> list[LocationKpiRow]:
    """Per-location actuals vs ramp target for one period."""
    rows = (
        await session.execute(
            text(
                """
                SELECT l.id, l.name, o.name, l.activated_on,
                       coalesce(t.n, 0) AS completed,
                       coalesce(r.net_base, 0) AS net_base
                  FROM locations l
                  JOIN orgs o ON o.id = l.org_id
                  LEFT JOIN (
                        SELECT location_id, count(*) AS n
                          FROM treatments
                         WHERE completed_at IS NOT NULL
                           AND date_trunc('month', completed_at AT TIME ZONE :tz)::date = :period
                         GROUP BY 1
                       ) t ON t.location_id = l.id
                  LEFT JOIN (
                        SELECT location_id, sum(net_base_cents) AS net_base
                          FROM revenue_reports
                         WHERE status = 'locked' AND period = :period
                         GROUP BY 1
                       ) r ON r.location_id = l.id
                 ORDER BY o.name, l.name
                """
            ),
            {"tz": tz, "period": period},
        )
    ).all()
    out: list[LocationKpiRow] = []
    for loc_id, loc_name, org_name, activated_on, completed, net_base in rows:
        active = months_active(activated_on, period)
        target = target_treatments(active)
        out.append(
            LocationKpiRow(
                location_id=str(loc_id),
                location_name=loc_name,
                org_name=org_name,
                months_active=active,
                treatments_completed=completed,
                target_treatments=target,
                attainment=round(completed / target, 3) if target > 0 else 0.0,
                reported_net_base_cents=net_base,
            )
        )
    return out
