"""phase 6 payments table

Collections (ADR-0010): one row per provider checkout session against an
invoice. provider_ref is UNIQUE so webhook replays land on the same row —
idempotency lives at the database, like every other invariant. Tenant-scoped
with the standard tenant_isolation policy (ADR-0002): an operator sees only
its own payments; the provider webhook writes in the machine hq_admin context.

Revision ID: 41fdf96fff0d
Revises: 21eae3d52b30
Create Date: 2026-08-05 06:24:55.113725

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "41fdf96fff0d"
down_revision: str | None = "21eae3d52b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IS_HQ = "current_setting('app.role', true) = 'hq_admin'"
ORG_MATCH = "org_id = NULLIF(current_setting('app.org_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_ref", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("initiated", "succeeded", "failed", name="payment_status"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_ref", name="uq_payments_provider_ref"),
    )
    op.create_index(op.f("ix_payments_invoice_id"), "payments", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_payments_org_id"), "payments", ["org_id"], unique=False)

    # Same tenant isolation as every org_id-carrying table (ADR-0002).
    op.execute("ALTER TABLE payments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE payments FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON payments
            USING ({IS_HQ} OR {ORG_MATCH})
            WITH CHECK ({IS_HQ} OR {ORG_MATCH})
        """
    )

    # App role grants — skipped where the role doesn't exist (Neon single-role).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'cnos_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON payments TO cnos_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON payments")
    op.drop_index(op.f("ix_payments_org_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_invoice_id"), table_name="payments")
    op.drop_table("payments")
    op.execute("DROP TYPE IF EXISTS payment_status")
