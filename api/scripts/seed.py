"""Deterministic synthetic seed world (PROJECT_CONTEXT §7).

Every number here is fabricated. Rebuilds the same world on every run:
truncate-all + reinsert with a fixed RNG seed. Content (counts, values, the
designated underreporter) is deterministic; row UUIDs are not, and nothing
depends on them.

Runs as the admin/owner role (TRUNCATE needs ownership):
    make seed            # local
    MIGRATIONS_DATABASE_URL=<owner-url> uv run python -m scripts.seed   # any env
"""

import asyncio
import random
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from uuid6 import uuid7

from app.core.config import get_settings
from app.db import models as m
from app.services.auth import hash_password

RNG_SEED = 42
# Fixed anchor: the seed world ends just before this date; 6 complete months back.
ANCHOR = date(2026, 8, 1)
PERIODS = [date(2026, month, 1) for month in range(2, 8)]  # Feb..Jul 2026

HQ_EMAIL = "hq_admin@clinic-network-os.demo"
DEMO_PASSWORDS = {
    "hq_admin": "demo-hq-2026!",
    "operator": "demo-operator-2026!",
    "clinic_staff": "demo-staff-2026!",
}

# One designated underreporter: reports land ~40% below the supply-implied floor.
UNDERREPORTER_LOCATION = "Vista Glow Clinic — Chandler"
UNDERREPORT_FACTOR = 0.60

CITIES = [
    "Phoenix",
    "Scottsdale",
    "Tempe",
    "Mesa",
    "Chandler",
    "Gilbert",
    "Glendale",
    "Peoria",
    "Tucson",
    "Flagstaff",
    "Sedona",
    "Yuma",
    "Prescott",
    "Goodyear",
    "Surprise",
    "Avondale",
    "Queen Creek",
    "Maricopa",
    "Buckeye",
    "Casa Grande",
]

PRODUCTS: list[dict[str, Any]] = [
    {"sku": "NTX-100", "name": "Neurotoxin Vial 100u", "unit": "vial", "price_cents": 45_000},
    {
        "sku": "FIL-1ML",
        "name": "Dermal Filler Syringe 1ml",
        "unit": "syringe",
        "price_cents": 60_000,
    },
    {"sku": "BIO-VL", "name": "Biostimulator Vial", "unit": "vial", "price_cents": 80_000},
]

AVG_NET_TICKET_CENTS = 100_000  # $1,000 — the stable seed value the R5 model uses


@dataclass
class World:
    """Accumulates rows per table for one bulk insert pass at the end."""

    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def add(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        self.rows.setdefault(table, []).append(row)
        return row


def _org(w: World, kind: str, name: str) -> UUID:
    org_id = uuid7()
    w.add("orgs", {"id": org_id, "kind": kind, "name": name})
    return org_id


def _location(w: World, org_id: UUID, name: str, activated_on: date) -> UUID:
    loc_id = uuid7()
    w.add(
        "locations",
        {"id": loc_id, "org_id": org_id, "name": name, "activated_on": activated_on},
    )
    return loc_id


def _user(w: World, org_id: UUID, email: str, role: str, full_name: str) -> UUID:
    user_id = uuid7()
    w.add(
        "users",
        {
            "id": user_id,
            "org_id": org_id,
            "email": email,
            "password_hash": hash_password(DEMO_PASSWORDS[role]),
            "role": role,
            "full_name": full_name,
            "is_active": True,
        },
    )
    return user_id


def build_world() -> World:
    rng = random.Random(RNG_SEED)
    w = World()

    # --- Identity: HQ + operators (1 + 3 + 4 locations, rest single) = 20 locs ---
    hq_org = _org(w, "hq", "Clinic Network OS HQ")
    _user(w, hq_org, HQ_EMAIL, "hq_admin", "Harper Quinn")

    cities = iter(CITIES)
    operator_locs: list[tuple[UUID, UUID, str]] = []  # (org, location, name)
    multi = [
        ("Radiant Partners Group", 1),
        ("Luminous Clinics Collective", 3),
        ("Desert Bloom Aesthetics Group", 4),
    ]
    single_count = 20 - sum(n for _, n in multi)
    operators = multi + [(f"Solo Operator {i + 1} LLC", 1) for i in range(single_count)]

    for idx, (org_name, n_locs) in enumerate(operators):
        org_id = _org(w, "operator", org_name)
        _user(
            w,
            org_id,
            f"operator-{idx + 1}@clinic-network-os.demo",
            "operator",
            f"Operator {idx + 1}",
        )
        rate = Decimal("0.0500") if org_name == "Luminous Clinics Collective" else Decimal("0.0700")
        minimum = 200_000 if org_name == "Desert Bloom Aesthetics Group" else None
        w.add(
            "license_agreements",
            {
                "id": uuid7(),
                "org_id": org_id,
                "royalty_rate": rate,
                "base_definition": "net_treatment_revenue",
                "monthly_minimum_cents": minimum,
                "effective_from": date(2025, 6, 1),
                "effective_to": None,
            },
        )
        for loc_n in range(n_locs):
            city = next(cities)
            name = (
                UNDERREPORTER_LOCATION
                if city == "Chandler"
                else f"{'Vista Glow' if n_locs == 1 else org_name.split()[0]} Clinic — {city}"
            )
            # Staggered activation: older locations have longer histories/ramps.
            activated = date(2025, 6 + ((idx + loc_n) % 7), 1)
            loc_id = _location(w, org_id, name, activated)
            operator_locs.append((org_id, loc_id, name))
            if org_name == "Luminous Clinics Collective" and loc_n == 0:
                _user(
                    w,
                    org_id,
                    f"staff-{idx + 1}@clinic-network-os.demo",
                    "clinic_staff",
                    "Casey Staff",
                )

    # --- Catalog ---
    product_ids: list[tuple[UUID, int]] = []
    for p in PRODUCTS:
        pid: UUID = uuid7()
        w.add("products", {"id": pid, **p})
        product_ids.append((pid, int(p["price_cents"])))
    lots: list[UUID] = []
    for q, (product_id, _) in enumerate(product_ids * 3):  # 9 lots across products
        lot_id: UUID = uuid7()
        w.add(
            "lots",
            {
                "id": lot_id,
                "product_id": product_id,
                "lot_code": f"LOT-2026-{q + 1:03d}",
                "supplier": rng.choice(["MedSupply Co", "VialWorks Inc", "AesthetiSource"]),
                "expiry": date(2027, 1 + (q % 12), 1),
            },
        )
        lots.append(lot_id)

    # --- Funnel + supply + reports per location per period ---
    for org_id, loc_id, loc_name in operator_locs:
        loc_lot = rng.sample(lots, k=3)  # each location draws from 3 lots
        # Reports must be derived from CALENDAR-month administrations — the same
        # bucketing the variance engine uses (R5). Deriving them from the funnel
        # loop's counts instead lets treatment spillover systematically skew
        # reported-vs-floor and false-flag honest locations.
        admin_dates: list[datetime] = []
        for period in PERIODS:
            months_active = (period.year - 2025) * 12 + period.month - 6
            if months_active <= 0:
                continue
            # Ramp: newer locations produce less; plateau ~14 months.
            ramp = min(1.0, 0.3 + months_active * 0.06)
            n_leads = int(rng.gauss(60, 8) * ramp)
            month_admins = 0

            for _ in range(max(n_leads, 5)):
                lead_day = period + timedelta(days=rng.randrange(28))
                lead_at = datetime(lead_day.year, lead_day.month, lead_day.day, 9, tzinfo=UTC)
                lead_id = uuid7()
                w.add(
                    "leads",
                    {
                        "id": lead_id,
                        "org_id": org_id,
                        "location_id": loc_id,
                        "source": rng.choice(["meta_ads", "google_ads", "referral", "walk_in"]),
                        "external_id": f"ext-{lead_id.hex[:12]}",
                        "created_at": lead_at,
                    },
                )
                if rng.random() > 0.55:  # no consult booked
                    continue
                consult_at = lead_at + timedelta(days=rng.randrange(1, 10), hours=rng.randrange(8))
                outcome = rng.choices(["no_show", "no_sale", "sale"], weights=[20, 45, 35])[0]
                consult_id = uuid7()
                w.add(
                    "consults",
                    {
                        "id": consult_id,
                        "org_id": org_id,
                        "location_id": loc_id,
                        "lead_id": lead_id,
                        "scheduled_at": consult_at,
                        "occurred_at": None if outcome == "no_show" else consult_at,
                        "outcome": outcome,
                        "created_at": lead_at,
                    },
                )
                if outcome != "sale":
                    continue
                planned = rng.randint(3, 6)
                plan_value = planned * rng.randint(80_000, 120_000)
                sale_id = uuid7()
                w.add(
                    "sales",
                    {
                        "id": sale_id,
                        "org_id": org_id,
                        "location_id": loc_id,
                        "consult_id": consult_id,
                        "plan_value_cents": plan_value,
                        "planned_treatments": planned,
                        "financing_flag": rng.random() < 0.3,
                        "sold_at": consult_at + timedelta(hours=1),
                        "created_at": consult_at,
                    },
                )
                # Treatments this month (rest spill into future periods; keep in-month
                # so supply/consumption/report math stays self-consistent).
                for t_n in range(min(planned, rng.randint(2, 4))):
                    treated_at = consult_at + timedelta(days=3 + t_n * 9)
                    if treated_at.date() >= ANCHOR:
                        continue
                    treatment_id = uuid7()
                    w.add(
                        "treatments",
                        {
                            "id": treatment_id,
                            "org_id": org_id,
                            "location_id": loc_id,
                            "sale_id": sale_id,
                            "scheduled_at": treated_at,
                            "completed_at": treated_at,
                            "created_at": consult_at,
                        },
                    )
                    w.add(
                        "administrations",
                        {
                            "id": uuid7(),
                            "org_id": org_id,
                            "location_id": loc_id,
                            "lot_id": rng.choice(loc_lot),
                            "treatment_id": treatment_id,
                            "synthetic_patient_ref": f"synthpt-{uuid7().hex[:10]}",
                            "qty": 1,
                            "administered_at": treated_at,
                            "created_at": treated_at,
                        },
                    )
                    admin_dates.append(treated_at)
                    month_admins += 1

            # Ship enough stock ahead of the month for what gets consumed.
            per_lot = month_admins // len(loc_lot) + 8
            ship_at = datetime(period.year, period.month, 1, 6, tzinfo=UTC) - timedelta(days=3)
            for ship_lot in loc_lot:
                w.add(
                    "shipments",
                    {
                        "id": uuid7(),
                        "org_id": org_id,
                        "location_id": loc_id,
                        "lot_id": ship_lot,
                        "qty": per_lot,
                        "shipped_at": ship_at,
                        "created_at": ship_at,
                    },
                )

        # Locked, attested monthly reports — derived from calendar-month
        # administration counts, the exact quantity the variance floor uses.
        # Honest locations report above the floor; only the designated
        # underreporter lands ~40% under it.
        operator_user = next(
            r["id"] for r in w.rows["users"] if r["org_id"] == org_id and r["role"] == "operator"
        )
        for period in PERIODS:
            calendar_admins = sum(
                1 for t in admin_dates if t.year == period.year and t.month == period.month
            )
            implied = calendar_admins * AVG_NET_TICKET_CENTS
            if loc_name == UNDERREPORTER_LOCATION:
                gross = int(implied * UNDERREPORT_FACTOR)
            else:
                gross = int(implied * rng.uniform(1.10, 1.30))
            refunds = int(gross * rng.uniform(0.01, 0.04))
            report_at = datetime(period.year, period.month, 28, 17, tzinfo=UTC)
            w.add(
                "revenue_reports",
                {
                    "id": uuid7(),
                    "org_id": org_id,
                    "location_id": loc_id,
                    "period": period,
                    "gross_cents": gross,
                    "refunds_cents": refunds,
                    "status": "locked",
                    "attested_by": operator_user,
                    "attested_at": report_at,
                    "supersedes": None,
                    "created_at": report_at,
                },
            )

    return w


# Insert order respects FKs; administrations after shipments so the on-hand
# triggers never dip below zero mid-seed.
INSERT_ORDER = [
    ("orgs", m.Org),
    ("locations", m.Location),
    ("users", m.User),
    ("license_agreements", m.LicenseAgreement),
    ("products", m.Product),
    ("lots", m.Lot),
    ("leads", m.Lead),
    ("consults", m.Consult),
    ("sales", m.Sale),
    ("treatments", m.Treatment),
    ("shipments", m.Shipment),
    ("administrations", m.Administration),
    ("revenue_reports", m.RevenueReport),
]

TRUNCATE_ORDER = [
    "variance_flags",
    "invoices",
    "royalty_line_items",
    "royalty_runs",
    "revenue_reports",
    "administrations",
    "shipments",
    "location_lot_on_hand",
    "treatments",
    "sales",
    "consults",
    "leads",
    "lots",
    "products",
    "license_agreements",
    "users",
    "locations",
    "orgs",
]


HISTORY_PERIODS = PERIODS[:-1]  # Feb..Jun get runs+invoices; July stays unrun
# for the live "Run royalty period" demo beat.

# Fraction of each period's invoices already paid — the remainder produces a
# realistic aging spread (older unpaid invoices land in deeper buckets).
PAID_FRACTION = {2: 1.0, 3: 1.0, 4: 0.85, 5: 0.6, 6: 0.3}


async def _build_royalty_history(engine: AsyncEngine) -> dict[str, int]:
    """Run the real royalty services for past periods, then backdate.

    Uses the actual run/issue code paths (invariants included) under an
    hq_admin RLS context, so seeded history is exactly what the demo produces
    live. Invoices are then backdated to their period (issued the 5th of the
    following month, net-30) and a deterministic subset marked paid.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.security import TokenClaims
    from app.services import royalty as royalty_service

    factory = async_sessionmaker(engine, expire_on_commit=False)
    hq = TokenClaims(sub="seed-history", org_id="", role="hq_admin")
    set_ctx = text(
        "SELECT set_config('app.org_id', '', true), set_config('app.role', 'hq_admin', true)"
    )

    runs = 0
    invoices = 0
    for period in HISTORY_PERIODS:
        async with factory() as session, session.begin():
            await session.execute(set_ctx)
            run = await royalty_service.run_royalty_period(session, hq, period)
            issued = await royalty_service.issue_invoices(session, hq, UUID(str(run.id)))
            runs += 1
            invoices += len(issued.invoices)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE invoices i
                   SET issued_at = (r.period + interval '1 month' + interval '4 days'),
                       due_date = (r.period + interval '1 month' + interval '34 days')::date
                  FROM royalty_runs r
                 WHERE r.id = i.run_id
                """
            )
        )
        for period in HISTORY_PERIODS:
            fraction = PAID_FRACTION[period.month]
            await conn.execute(
                text(
                    """
                    WITH ranked AS (
                        SELECT i.id,
                               row_number() OVER (ORDER BY o.name) AS rn,
                               count(*) OVER () AS total
                          FROM invoices i
                          JOIN royalty_runs r ON r.id = i.run_id
                          JOIN orgs o ON o.id = i.org_id
                         WHERE r.period = :period
                    )
                    UPDATE invoices
                       SET status = 'paid'
                     WHERE id IN (
                        SELECT id FROM ranked
                         WHERE rn <= round(total * CAST(:fraction AS float8))
                     )
                    """
                ),
                {"period": period, "fraction": fraction},
            )
    return {"royalty_runs": runs, "invoices": invoices}


async def run_seed(engine: AsyncEngine) -> dict[str, int]:
    world = build_world()
    counts: dict[str, int] = {}
    async with engine.begin() as conn:
        # Ledger append-only triggers block TRUNCATE's intent? No — TRUNCATE skips
        # row triggers; balances are wiped with the tables in the same statement.
        await conn.execute(text(f"TRUNCATE TABLE {', '.join(TRUNCATE_ORDER)} CASCADE"))
        for table, model in INSERT_ORDER:
            rows = world.rows.get(table, [])
            if rows:
                await conn.execute(insert(model), rows)
            counts[table] = len(rows)
    counts.update(await _build_royalty_history(engine))
    await engine.dispose()
    return counts


def main() -> None:
    settings = get_settings()
    url = settings.migrations_database_url or settings.database_url
    engine = create_async_engine(url)
    counts = asyncio.run(run_seed(engine))
    for table, n in counts.items():
        sys.stdout.write(f"{table:20s} {n:6d}\n")
    sys.stdout.write("seed complete — demo logins in docs/runbooks/local-dev.md\n")


if __name__ == "__main__":
    main()
