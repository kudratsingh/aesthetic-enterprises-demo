"""phase 2 royalty exclusions and report lock trigger

Two additions for the royalty domain core (ADR-0004):

1. royalty_run_exclusions — run policy A3 records every location a run skipped
   (unlocked/missing report, no active agreement) with a reason. Tenant-scoped
   with the standard RLS policy so an operator sees only its own exclusions,
   while the royalty_runs row itself stays network-shared.

2. Invariant 2 at the database: a BEFORE UPDATE OR DELETE trigger on
   revenue_reports rejects any mutation of a row whose status is 'locked'.
   There is deliberately NO exception path: the sanctioned supersedes link
   lives entirely on the successor row (a new draft INSERTed with
   supersedes = old.id), so correcting a locked report never touches the
   locked row. Transitions INTO locked pass because the guard checks
   OLD.status only.

Revision ID: 96e322848d4f
Revises: f421a68d63a9
Create Date: 2026-08-05 04:15:29.493428

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "96e322848d4f"
down_revision: str | None = "f421a68d63a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IS_HQ = "current_setting('app.role', true) = 'hq_admin'"
ORG_MATCH = "org_id = NULLIF(current_setting('app.org_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "royalty_run_exclusions",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["royalty_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "location_id", name="uq_royalty_run_exclusions_run_location"),
    )
    op.create_index(
        op.f("ix_royalty_run_exclusions_location_id"),
        "royalty_run_exclusions",
        ["location_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_royalty_run_exclusions_org_id"), "royalty_run_exclusions", ["org_id"], unique=False
    )
    op.create_index(
        op.f("ix_royalty_run_exclusions_run_id"), "royalty_run_exclusions", ["run_id"], unique=False
    )

    # Same tenant isolation as every org_id-carrying table (ADR-0002).
    op.execute("ALTER TABLE royalty_run_exclusions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE royalty_run_exclusions FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON royalty_run_exclusions
            USING ({IS_HQ} OR {ORG_MATCH})
            WITH CHECK ({IS_HQ} OR {ORG_MATCH})
        """
    )

    # --- Invariant 2: locked revenue_reports are immutable at the DB ---
    op.execute(
        """
        CREATE FUNCTION forbid_locked_report_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.status = 'locked' THEN
                RAISE EXCEPTION 'locked revenue_reports are immutable; corrections create a new'
                    ' report linked via supersedes';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER revenue_reports_lock_immutable
            BEFORE UPDATE OR DELETE ON revenue_reports
            FOR EACH ROW EXECUTE FUNCTION forbid_locked_report_mutation()
        """
    )

    # App role grants — skipped where the role doesn't exist (Neon single-role).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'cnos_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON royalty_run_exclusions TO cnos_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS revenue_reports_lock_immutable ON revenue_reports")
    op.execute("DROP FUNCTION IF EXISTS forbid_locked_report_mutation()")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON royalty_run_exclusions")
    op.drop_index(op.f("ix_royalty_run_exclusions_run_id"), table_name="royalty_run_exclusions")
    op.drop_index(op.f("ix_royalty_run_exclusions_org_id"), table_name="royalty_run_exclusions")
    op.drop_index(
        op.f("ix_royalty_run_exclusions_location_id"), table_name="royalty_run_exclusions"
    )
    op.drop_table("royalty_run_exclusions")
