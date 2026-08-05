import uuid
from datetime import UTC, datetime
from typing import Annotated, ClassVar

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from uuid6 import uuid7


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[type, object]] = {
        uuid.UUID: PG_UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
    }


def utcnow() -> datetime:
    return datetime.now(UTC)


# UUIDv7 (time-ordered) per PROJECT_CONTEXT §4; generated app-side for pg16 compat.
uuid_pk = Annotated[uuid.UUID, mapped_column(primary_key=True, default=uuid7)]
created_at_col = Annotated[
    datetime, mapped_column(nullable=False, default=utcnow, server_default=func.now())
]
# Money is integer cents everywhere; BigInteger so aggregates can't overflow.
cents = Annotated[int, mapped_column(BigInteger, nullable=False)]
org_fk = Annotated[
    uuid.UUID, mapped_column(ForeignKey("orgs.id", ondelete="RESTRICT"), nullable=False, index=True)
]
location_fk = Annotated[
    uuid.UUID,
    mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False, index=True),
]


class TimestampedTenantMixin:
    """Columns shared by every tenant-scoped row: RLS keys on org_id."""

    id: Mapped[uuid_pk]
    org_id: Mapped[org_fk]
    created_at: Mapped[created_at_col]
