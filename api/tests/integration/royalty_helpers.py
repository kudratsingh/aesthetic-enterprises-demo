"""Shared setup for royalty integration tests.

Tests append to a shared database (CI recreates it from zero), so every test
uses collision-free names and its own calendar month: run_royalty_period scans
the whole network for a period, and a private period keeps each test's inputs
stable between its own reruns.
"""

import itertools
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.core.security import TokenClaims
from app.schemas.royalty import RevenueReportOut
from app.services import royalty
from tests.conftest import HQ_ORG_ID, tenant_session, unique

HQ_ACTOR = TokenClaims(sub="hq-admin-test", org_id=HQ_ORG_ID, role="hq_admin")

_period_counter = itertools.count()


def unique_period() -> date:
    """A month no other test in this suite run touches (far future, synthetic)."""
    n = next(_period_counter)
    return date(2040 + n // 12, n % 12 + 1, 1)


def operator_actor(org_id: uuid.UUID, user_id: uuid.UUID) -> TokenClaims:
    return TokenClaims(sub=str(user_id), org_id=str(org_id), role="operator")


async def create_operator(
    royalty_rate: str = "0.0700",
    monthly_minimum_cents: int | None = None,
    activated_on: date = date(2035, 1, 1),
    with_agreement: bool = True,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """One operator org with one location, one user, and (optionally) an
    agreement in force from 2035 onward. Returns (org_id, location_id, user_id)."""
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        org_id: uuid.UUID = (
            await s.execute(
                text(
                    "INSERT INTO orgs (id, kind, name)"
                    " VALUES (gen_random_uuid(), 'operator', :n) RETURNING id"
                ),
                {"n": unique("org")},
            )
        ).scalar_one()
        loc_id: uuid.UUID = (
            await s.execute(
                text(
                    "INSERT INTO locations (id, org_id, name, activated_on)"
                    " VALUES (gen_random_uuid(), :org, :n, :d) RETURNING id"
                ),
                {"org": org_id, "n": unique("loc"), "d": activated_on},
            )
        ).scalar_one()
        user_id: uuid.UUID = (
            await s.execute(
                text(
                    "INSERT INTO users (id, org_id, email, password_hash, role, full_name,"
                    " is_active) VALUES (gen_random_uuid(), :org, :email, 'x', 'operator',"
                    " 'Test Operator', true) RETURNING id"
                ),
                {"org": org_id, "email": f"{unique('user')}@clinic-network-os.test"},
            )
        ).scalar_one()
        if with_agreement:
            await s.execute(
                text(
                    "INSERT INTO license_agreements (id, org_id, royalty_rate, base_definition,"
                    " monthly_minimum_cents, effective_from)"
                    " VALUES (gen_random_uuid(), :org, :rate, 'net_treatment_revenue', :min, :d)"
                ),
                {
                    "org": org_id,
                    "rate": Decimal(royalty_rate),
                    "min": monthly_minimum_cents,
                    "d": date(2035, 1, 1),
                },
            )
    return org_id, loc_id, user_id


async def lock_report(
    org_id: uuid.UUID,
    loc_id: uuid.UUID,
    user_id: uuid.UUID,
    period: date,
    gross_cents: int,
    refunds_cents: int = 0,
) -> RevenueReportOut:
    """Create and submit (lock) a report through the real service path."""
    actor = operator_actor(org_id, user_id)
    async with tenant_session(str(org_id), "operator") as s:
        draft = await royalty.create_report(s, actor, loc_id, period, gross_cents, refunds_cents)
    async with tenant_session(str(org_id), "operator") as s:
        return await royalty.submit_report(s, actor, draft.id)
