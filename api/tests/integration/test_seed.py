"""Seed-world smoke tests: Phase 1 exit requires one-command reset that
deterministically rebuilds the demo world (PROJECT_CONTEXT §7)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
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


def test_seed_world_is_synthetic_only() -> None:
    """Guardrail: no seed row can carry PHI — patient refs are opaque synthetics."""
    world = build_world()
    assert all(
        r["synthetic_patient_ref"].startswith("synthpt-") for r in world.rows["administrations"]
    )
