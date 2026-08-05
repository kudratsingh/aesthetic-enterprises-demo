"""rls policies and ledger triggers

RLS design (ADR-0002): every tenant-scoped table is keyed on org_id against the
transaction-local settings app.org_id / app.role, set by the tenancy dependency
from the verified JWT. HQ bypass is policy-level (app.role = 'hq_admin'), never a
code branch. ENABLE + FORCE so RLS also binds the table owner (Neon's single-role
setup). The app must connect as a non-superuser (cnos_app locally) — superusers
bypass RLS unconditionally.

Ledger rules (ADR-0003): shipments/administrations are append-only (trigger-
enforced); on-hand is trigger-maintained in location_lot_on_hand whose CHECK is
invariant 1.

Revision ID: f421a68d63a9
Revises: fff849ab3deb
Create Date: 2026-08-05 03:50:19.787545

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f421a68d63a9"
down_revision: str | None = "fff849ab3deb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables carrying org_id, isolated per-tenant with policy-level HQ bypass.
TENANT_TABLES = [
    "locations",
    "users",
    "license_agreements",
    "leads",
    "consults",
    "sales",
    "treatments",
    "shipments",
    "administrations",
    "location_lot_on_hand",
    "revenue_reports",
    "royalty_line_items",
    "invoices",
    "variance_flags",
]

# Network-shared catalog: any authenticated tenant reads, HQ writes.
SHARED_READ_TABLES = ["products", "lots", "royalty_runs"]

IS_HQ = "current_setting('app.role', true) = 'hq_admin'"
IS_AUTHENTICATED = "current_setting('app.role', true) IN ('hq_admin', 'operator', 'clinic_staff')"
ORG_MATCH = "org_id = NULLIF(current_setting('app.org_id', true), '')::uuid"


def upgrade() -> None:
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {t}
                USING ({IS_HQ} OR {ORG_MATCH})
                WITH CHECK ({IS_HQ} OR {ORG_MATCH})
            """
        )

    # orgs: tenant sees its own row; only HQ creates/modifies orgs.
    op.execute("ALTER TABLE orgs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE orgs FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON orgs
            USING ({IS_HQ} OR id = NULLIF(current_setting('app.org_id', true), '')::uuid)
            WITH CHECK ({IS_HQ})
        """
    )

    # Login runs before any tenant context exists: the auth service sets
    # app.role = 'auth_service' to look up a user by email (ADR-0006).
    op.execute(
        """
        CREATE POLICY auth_lookup ON users FOR SELECT
            USING (current_setting('app.role', true) = 'auth_service')
        """
    )

    for t in SHARED_READ_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY network_read ON {t} FOR SELECT USING ({IS_AUTHENTICATED})")
        op.execute(f"CREATE POLICY hq_insert ON {t} FOR INSERT WITH CHECK ({IS_HQ})")
        op.execute(
            f"CREATE POLICY hq_update ON {t} FOR UPDATE USING ({IS_HQ}) WITH CHECK ({IS_HQ})"
        )
        op.execute(f"CREATE POLICY hq_delete ON {t} FOR DELETE USING ({IS_HQ})")

    # --- Append-only ledgers (ADR-0003) ---
    op.execute(
        """
        CREATE FUNCTION forbid_ledger_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% rows are append-only; corrections are reversing entries',
                TG_TABLE_NAME;
        END
        $$
        """
    )
    for t in ("shipments", "administrations"):
        op.execute(
            f"""
            CREATE TRIGGER {t}_append_only
                BEFORE UPDATE OR DELETE ON {t}
                FOR EACH ROW EXECUTE FUNCTION forbid_ledger_mutation()
            """
        )

    # --- On-hand maintenance; the CHECK on location_lot_on_hand is invariant 1 ---
    # UPDATE-first, INSERT-fallback: with INSERT..ON CONFLICT DO UPDATE, Postgres
    # evaluates CHECK constraints on the candidate row BEFORE conflict resolution,
    # so a negative-delta candidate (any administration, any reversal) would fail
    # the CHECK even when the resulting balance is fine.
    op.execute(
        """
        CREATE FUNCTION apply_on_hand_delta(
            p_location_id uuid, p_lot_id uuid, p_org_id uuid, p_delta integer
        ) RETURNS void
        LANGUAGE plpgsql AS $$
        BEGIN
            UPDATE location_lot_on_hand
               SET on_hand = on_hand + p_delta
             WHERE location_id = p_location_id AND lot_id = p_lot_id;
            IF NOT FOUND THEN
                INSERT INTO location_lot_on_hand (location_id, lot_id, org_id, on_hand)
                VALUES (p_location_id, p_lot_id, p_org_id, p_delta)
                ON CONFLICT (location_id, lot_id)
                DO UPDATE SET on_hand = location_lot_on_hand.on_hand + EXCLUDED.on_hand;
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION apply_shipment_to_on_hand() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM apply_on_hand_delta(NEW.location_id, NEW.lot_id, NEW.org_id, NEW.qty);
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION apply_administration_to_on_hand() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM apply_on_hand_delta(NEW.location_id, NEW.lot_id, NEW.org_id, -NEW.qty);
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER shipments_apply_on_hand
            AFTER INSERT ON shipments
            FOR EACH ROW EXECUTE FUNCTION apply_shipment_to_on_hand()
        """
    )
    op.execute(
        """
        CREATE TRIGGER administrations_apply_on_hand
            AFTER INSERT ON administrations
            FOR EACH ROW EXECUTE FUNCTION apply_administration_to_on_hand()
        """
    )

    # App role grants — skipped where the role doesn't exist (Neon single-role).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'cnos_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cnos_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS administrations_apply_on_hand ON administrations")
    op.execute("DROP TRIGGER IF EXISTS shipments_apply_on_hand ON shipments")
    op.execute("DROP FUNCTION IF EXISTS apply_administration_to_on_hand()")
    op.execute("DROP FUNCTION IF EXISTS apply_shipment_to_on_hand()")
    op.execute("DROP FUNCTION IF EXISTS apply_on_hand_delta(uuid, uuid, uuid, integer)")
    for t in ("shipments", "administrations"):
        op.execute(f"DROP TRIGGER IF EXISTS {t}_append_only ON {t}")
    op.execute("DROP FUNCTION IF EXISTS forbid_ledger_mutation()")

    for t in SHARED_READ_TABLES:
        for p in ("network_read", "hq_insert", "hq_update", "hq_delete"):
            op.execute(f"DROP POLICY IF EXISTS {p} ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS auth_lookup ON users")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON orgs")
    op.execute("ALTER TABLE orgs DISABLE ROW LEVEL SECURITY")
    for t in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
