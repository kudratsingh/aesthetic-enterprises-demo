"""Identity/tenancy reads. RLS scopes every row — an operator's session simply
cannot see other orgs' locations."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.locations import LocationOut


async def list_locations(session: AsyncSession) -> list[LocationOut]:
    rows = (
        await session.execute(
            text(
                "SELECT l.id, l.org_id, o.name, l.name, l.activated_on"
                "  FROM locations l JOIN orgs o ON o.id = l.org_id"
                " ORDER BY o.name, l.name"
            )
        )
    ).all()
    return [
        LocationOut(
            id=str(lid), org_id=str(oid), org_name=org_name, name=name, activated_on=activated
        )
        for lid, oid, org_name, name, activated in rows
    ]
