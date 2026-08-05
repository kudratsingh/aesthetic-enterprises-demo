"""Seed-world smoke tests: Phase 1 exit requires one-command reset that
deterministically rebuilds the demo world (PROJECT_CONTEXT §7)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings, get_settings
from app.core.security import TokenClaims, mint_token
from scripts.seed import (
    AVG_NET_TICKET_CENTS,
    HQ_EMAIL,
    PERIODS,
    UNDERREPORTER_LOCATION,
    build_world,
    run_seed,
)
from tests.conftest import HQ_ORG_ID, tenant_session

pytestmark = pytest.mark.integration


def _admin_engine_url() -> str:
    settings = get_settings()
    return settings.migrations_database_url or settings.database_url


async def _reseed() -> dict[str, int]:
    return await run_seed(create_async_engine(_admin_engine_url()))


async def test_seed_reset_is_one_command_and_deterministic() -> None:
    first = await _reseed()
    assert first["locations"] == 20
    assert first["orgs"] == 16  # 1 HQ + 15 operators
    assert first["revenue_reports"] == 120  # 20 locations x 6 periods
    assert first["administrations"] > 2000

    # World content is RNG-seeded: a rebuild lands on identical counts.
    second = await _reseed()
    assert second == first


async def test_seed_world_contains_designated_underreporter() -> None:
    await _reseed()
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        row = (
            await s.execute(
                text(
                    """
                    SELECT rr.net_base_cents, count(a.id) AS admins
                      FROM revenue_reports rr
                      JOIN locations l ON l.id = rr.location_id
                      LEFT JOIN administrations a
                        ON a.location_id = rr.location_id
                       AND a.administered_at >= rr.period
                       AND a.administered_at < rr.period + INTERVAL '1 month'
                     WHERE l.name = :name AND rr.period = :period
                     GROUP BY rr.net_base_cents
                    """
                ),
                {"name": UNDERREPORTER_LOCATION, "period": PERIODS[-1]},
            )
        ).one()
        floor = row.admins * AVG_NET_TICKET_CENTS
        # ~40% below the supply-implied floor — safely past the 0.75 threshold (R5).
        assert row.net_base_cents < floor * 0.75

        # Every seeded report is locked and attested.
        unlocked = (
            await s.execute(text("SELECT count(*) FROM revenue_reports WHERE status <> 'locked'"))
        ).scalar_one()
        assert unlocked == 0


async def test_seeded_users_can_log_in_with_documented_passwords(client: AsyncClient) -> None:
    await _reseed()
    for email, password in [
        (HQ_EMAIL, "demo-hq-2026!"),
        ("operator-1@clinic-network-os.demo", "demo-operator-2026!"),
    ]:
        resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, email


async def test_seed_world_respects_rls_between_seeded_operators() -> None:
    """Phase 1 exit: the two-operator RLS check holds on the real seed world."""
    await _reseed()
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        org_a, org_b = (
            (
                await s.execute(
                    text("SELECT id FROM orgs WHERE kind = 'operator' ORDER BY name LIMIT 2")
                )
            )
            .scalars()
            .all()
        )
    async with tenant_session(str(org_a), "operator") as s:
        visible = (await s.execute(text("SELECT DISTINCT org_id FROM leads"))).scalars().all()
        assert visible == [org_a]
        foreign_reports = (
            await s.execute(
                text("SELECT count(*) FROM revenue_reports WHERE org_id = :b"), {"b": org_b}
            )
        ).scalar_one()
        assert foreign_reports == 0


async def test_seed_variance_flags_exactly_the_designated_underreporter(
    client: AsyncClient, settings: Settings
) -> None:
    """PROJECT_CONTEXT §7: exactly one variance flag per recent period. Reports
    are derived from calendar-month administration counts — the same bucketing
    the variance floor uses — so honest locations never false-flag."""
    await _reseed()
    token = mint_token(TokenClaims(sub="seed-check", org_id=HQ_ORG_ID, role="hq_admin"), settings)
    for period in PERIODS:
        resp = await client.post(
            f"/api/v1/variance/compute?period={period.isoformat()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        names = [f["location_name"] for f in resp.json()["flags"]]
        assert names == [UNDERREPORTER_LOCATION], f"{period}: {names}"


async def test_seed_builds_royalty_history_with_aging_spread(
    client: AsyncClient, settings: Settings
) -> None:
    """Feb-Jun get real runs + invoices (July stays unrun for the live demo
    beat); paid fractions leave older unpaid invoices spread across aging
    buckets so the invoices/aging screens are populated from seed."""
    counts = await _reseed()
    assert counts["royalty_runs"] == 5
    assert counts["invoices"] == 75  # 15 orgs x 5 periods

    token = mint_token(TokenClaims(sub="seed-check", org_id=HQ_ORG_ID, role="hq_admin"), settings)
    headers = {"Authorization": f"Bearer {token}"}

    runs = await client.get("/api/v1/royalty/runs", headers=headers)
    assert {r["period"] for r in runs.json()} == {p.isoformat() for p in PERIODS[:-1]}

    invoices = await client.get("/api/v1/royalty/invoices", headers=headers)
    paid = sum(1 for r in invoices.json() if r["status"] == "paid")
    overdue = sum(1 for r in invoices.json() if r["status"] == "overdue")
    # Deterministic payment pattern: 15+15+13+9+4 paid; the rest are past due
    # and derive 'overdue' at read time.
    assert paid == 56
    assert overdue == 19

    aging = (await client.get("/api/v1/royalty/invoices/aging", headers=headers)).json()
    populated = {b["bucket"] for b in aging["buckets"] if b["invoice_count"] > 0}
    assert {"31-60", "61-90", "90+"} <= populated


def test_seed_world_is_synthetic_only() -> None:
    """Guardrail: no seed row can carry PHI — patient refs are opaque synthetics."""
    world = build_world()
    assert all(
        r["synthetic_patient_ref"].startswith("synthpt-") for r in world.rows["administrations"]
    )
