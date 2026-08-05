"""Integration tests for POST /api/v1/imports/leads (HQ-only CSV lead import).

Covers the happy path, idempotent re-import (skipped counts), row-level error
tolerance with line numbers, role enforcement, and header validation.
"""

import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text

from app.core.config import Settings
from app.core.security import TokenClaims, mint_token
from tests.conftest import tenant_session, unique
from tests.integration.royalty_helpers import create_operator

pytestmark = pytest.mark.integration

IMPORT_PATH = "/api/v1/imports/leads"
HEADER = "source,external_id,location_id,created_at"


async def _post_csv(client: AsyncClient, token: str, body: str) -> Response:
    return await client.post(
        IMPORT_PATH,
        content=body.encode(),
        headers={"Content-Type": "text/csv", "Authorization": f"Bearer {token}"},
    )


async def _lead_count(org_id: uuid.UUID, source: str) -> int:
    async with tenant_session(str(org_id), "operator") as s:
        count = (
            await s.execute(text("SELECT count(*) FROM leads WHERE source = :src"), {"src": source})
        ).scalar_one()
        return int(count)


async def test_happy_path_imports_all_rows(client: AsyncClient, hq_token: str) -> None:
    org_id, loc_id, _ = await create_operator()
    source = unique("csv")
    body = "\n".join(
        [
            HEADER,
            f"{source},{unique('lead')},{loc_id},2026-07-01T09:00:00Z",
            f"{source},{unique('lead')},{loc_id},2026-07-02T10:30:00Z",
            f"{source},{unique('lead')},{loc_id},",  # created_at optional
        ]
    )
    resp = await _post_csv(client, hq_token, body)
    assert resp.status_code == 200
    assert resp.json() == {"imported": 3, "skipped": 0, "errors": []}
    assert await _lead_count(org_id, source) == 3


async def test_reimport_is_idempotent(client: AsyncClient, hq_token: str) -> None:
    org_id, loc_id, _ = await create_operator()
    source = unique("csv")
    body = "\n".join([HEADER, f"{source},{unique('lead')},{loc_id},2026-07-01T09:00:00Z"])

    first = await _post_csv(client, hq_token, body)
    replay = await _post_csv(client, hq_token, body)
    assert first.json() == {"imported": 1, "skipped": 0, "errors": []}
    assert replay.json() == {"imported": 0, "skipped": 1, "errors": []}
    assert await _lead_count(org_id, source) == 1


async def test_duplicate_within_one_file_is_skipped(client: AsyncClient, hq_token: str) -> None:
    org_id, loc_id, _ = await create_operator()
    source, external_id = unique("csv"), unique("lead")
    body = "\n".join(
        [HEADER, f"{source},{external_id},{loc_id},", f"{source},{external_id},{loc_id},"]
    )
    resp = await _post_csv(client, hq_token, body)
    assert resp.json() == {"imported": 1, "skipped": 1, "errors": []}
    assert await _lead_count(org_id, source) == 1


async def test_malformed_rows_reported_and_good_rows_land(
    client: AsyncClient, hq_token: str
) -> None:
    org_id, loc_id, _ = await create_operator()
    source = unique("csv")
    body = "\n".join(
        [
            HEADER,
            f"{source},{unique('lead')},{loc_id},",  # line 2: good
            f"{source},,{loc_id},",  # line 3: missing external_id
            f"{source},{unique('lead')},not-a-uuid,",  # line 4: bad UUID
            f"{source},{unique('lead')},{uuid.uuid4()},",  # line 5: unknown location
            f"{source},{unique('lead')},{loc_id},not-a-date",  # line 6: bad created_at
        ]
    )
    resp = await _post_csv(client, hq_token, body)
    assert resp.status_code == 200
    result = resp.json()
    assert result["imported"] == 1
    assert result["skipped"] == 0
    assert [e["line"] for e in result["errors"]] == [3, 4, 5, 6]
    assert await _lead_count(org_id, source) == 1


async def test_missing_required_column_is_400(client: AsyncClient, hq_token: str) -> None:
    resp = await _post_csv(client, hq_token, "source,external_id\nfoo,bar")
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "import_format"
    assert "location_id" in body["detail"]


async def test_empty_body_is_400(client: AsyncClient, hq_token: str) -> None:
    resp = await _post_csv(client, hq_token, "")
    assert resp.status_code == 400
    assert resp.json()["code"] == "import_format"


async def test_operator_role_is_403(client: AsyncClient, settings: Settings) -> None:
    org_id, loc_id, user_id = await create_operator()
    token = mint_token(TokenClaims(sub=str(user_id), org_id=str(org_id), role="operator"), settings)
    resp = await _post_csv(client, token, f"{HEADER}\n{unique('csv')},{unique('lead')},{loc_id},")
    assert resp.status_code == 403
    assert resp.json()["code"] == "role_forbidden"


async def test_unauthenticated_is_401(client: AsyncClient) -> None:
    resp = await client.post(IMPORT_PATH, content=b"x", headers={"Content-Type": "text/csv"})
    assert resp.status_code == 401
