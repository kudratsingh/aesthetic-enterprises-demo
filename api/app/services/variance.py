"""Variance reconciliation (rule R5): reported revenue vs supply-implied floor.

The floor is deliberately a *floor*, not a truth estimate — it can only say
"reported revenue is implausibly low given product consumed". Threshold and the
ticket model are config so false positives can be tuned away (they destroy trust
in the feature).
"""

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.errors import DomainError
from app.schemas.variance import ComputeVarianceResponse, VarianceFlagOut

FALLBACK_AVG_NET_TICKET_CENTS = 100_000  # matches the seed's stable value


class VarianceFlagNotFoundError(DomainError):
    code = "variance_flag_not_found"
    status_code = 404


async def avg_net_ticket_cents(session: AsyncSession, period: date) -> int:
    """Trailing-90-day network average of plan_value ÷ planned_treatments (R5)."""
    period_end = (period.replace(day=1) + timedelta(days=32)).replace(day=1)
    value = (
        await session.execute(
            text(
                """
                SELECT avg(plan_value_cents::float / planned_treatments)
                  FROM sales
                 WHERE sold_at >= :start AND sold_at < :end
                """
            ),
            {"start": period_end - timedelta(days=90), "end": period_end},
        )
    ).scalar_one()
    return round(value) if value is not None else FALLBACK_AVG_NET_TICKET_CENTS


async def compute_flags(
    session: AsyncSession, tz: str, period: date, threshold: float
) -> ComputeVarianceResponse:
    """Open/update flags for every location whose locked report sits below the
    consumption-implied floor. Idempotent per (location, period): existing flags
    get refreshed numbers, their review status is preserved."""
    ticket = await avg_net_ticket_cents(session, period)
    rows = (
        await session.execute(
            text(
                """
                SELECT l.id, l.org_id, coalesce(a.n, 0) AS admins,
                       coalesce(r.net_base, 0) AS reported
                  FROM locations l
                  LEFT JOIN (
                        SELECT location_id, count(*) AS n
                          FROM administrations
                         WHERE date_trunc('month', administered_at AT TIME ZONE :tz)::date
                               = :period
                         GROUP BY 1
                       ) a ON a.location_id = l.id
                  LEFT JOIN (
                        SELECT location_id, sum(net_base_cents) AS net_base
                          FROM revenue_reports
                         WHERE status = 'locked' AND period = :period
                         GROUP BY 1
                       ) r ON r.location_id = l.id
                """
            ),
            {"tz": tz, "period": period},
        )
    ).all()

    for loc_id, org_id, admins, reported in rows:
        floor = admins * ticket
        if floor == 0 or reported >= floor * threshold:
            continue
        existing = (
            await session.execute(
                text("SELECT id FROM variance_flags WHERE location_id = :loc AND period = :period"),
                {"loc": loc_id, "period": period},
            )
        ).scalar_one_or_none()
        if existing is None:
            await session.execute(
                text(
                    "INSERT INTO variance_flags (id, org_id, location_id, period,"
                    " reported_net_base_cents, expected_floor_cents, status)"
                    " VALUES (:id, :org, :loc, :period, :reported, :floor, 'open')"
                ),
                {
                    "id": uuid7(),
                    "org": org_id,
                    "loc": loc_id,
                    "period": period,
                    "reported": reported,
                    "floor": floor,
                },
            )
        else:
            await session.execute(
                text(
                    "UPDATE variance_flags SET reported_net_base_cents = :reported,"
                    " expected_floor_cents = :floor WHERE id = :id"
                ),
                {"reported": reported, "floor": floor, "id": existing},
            )

    flags = await list_flags(session, tz, period=period, status=None)
    return ComputeVarianceResponse(
        period=period, threshold=threshold, avg_net_ticket_cents=ticket, flags=flags
    )


async def list_flags(
    session: AsyncSession, tz: str, period: date | None, status: str | None
) -> list[VarianceFlagOut]:
    """Flags with the math shown. RLS scopes rows; operators additionally see
    only resolved flags (permissions matrix — service-level refinement)."""
    rows = (
        await session.execute(
            text(
                """
                SELECT f.id, f.location_id, l.name, o.name, f.period,
                       f.reported_net_base_cents, f.expected_floor_cents,
                       f.status, f.resolution_reason,
                       coalesce(a.n, 0) AS admins
                  FROM variance_flags f
                  JOIN locations l ON l.id = f.location_id
                  JOIN orgs o ON o.id = f.org_id
                  LEFT JOIN (
                        SELECT location_id,
                               date_trunc('month', administered_at AT TIME ZONE :tz)::date AS p,
                               count(*) AS n
                          FROM administrations GROUP BY 1, 2
                       ) a ON a.location_id = f.location_id AND a.p = f.period
                 WHERE (CAST(:period AS date) IS NULL OR f.period = :period)
                   AND (CAST(:status AS text) IS NULL OR f.status::text = :status)
                 ORDER BY f.period DESC, o.name
                """
            ),
            {"tz": tz, "period": period, "status": status},
        )
    ).all()
    out: list[VarianceFlagOut] = []
    for fid, loc_id, loc_name, org_name, fperiod, reported, floor, fstatus, reason, admins in rows:
        ticket = round(floor / admins) if admins else 0
        out.append(
            VarianceFlagOut(
                id=str(fid),
                location_id=str(loc_id),
                location_name=loc_name,
                org_name=org_name,
                period=fperiod,
                reported_net_base_cents=reported,
                expected_floor_cents=floor,
                administrations=admins,
                avg_net_ticket_cents=ticket,
                ratio=round(reported / floor, 3) if floor else 0.0,
                status=fstatus,
                resolution_reason=reason,
            )
        )
    return out


async def resolve_flag(
    session: AsyncSession, flag_id: UUID, status: str, reason: str | None
) -> None:
    updated = (
        await session.execute(
            text(
                "UPDATE variance_flags SET status = :status, resolution_reason = :reason"
                " WHERE id = :id RETURNING id"
            ),
            {"status": status, "reason": reason, "id": flag_id},
        )
    ).scalar_one_or_none()
    if updated is None:
        raise VarianceFlagNotFoundError("variance flag not found")
