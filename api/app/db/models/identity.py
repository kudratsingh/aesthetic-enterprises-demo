from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, Enum, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampedTenantMixin, created_at_col, uuid_pk

org_kind = Enum("hq", "operator", name="org_kind")
user_role = Enum("hq_admin", "operator", "clinic_staff", name="user_role")


class Org(Base):
    """A tenant: the HQ licensor or one operator company. RLS keys on id here."""

    __tablename__ = "orgs"

    id: Mapped[uuid_pk]
    kind: Mapped[str] = mapped_column(org_kind, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[created_at_col]


class Location(Base, TimestampedTenantMixin):
    __tablename__ = "locations"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    activated_on: Mapped[date] = mapped_column(Date, nullable=False)


class User(Base, TimestampedTenantMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(user_role, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class LicenseAgreement(Base, TimestampedTenantMixin):
    """Per-org commercial terms; rates are per-agreement so grandfathered terms
    need no code changes (PROJECT_CONTEXT §3)."""

    __tablename__ = "license_agreements"

    royalty_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.0700")
    )
    base_definition: Mapped[str] = mapped_column(
        Text, nullable=False, default="net_treatment_revenue"
    )
    monthly_minimum_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
