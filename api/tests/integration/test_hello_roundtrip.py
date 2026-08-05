import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_hello_roundtrip_hits_real_postgres(client: AsyncClient, hq_token: str) -> None:
    resp = await client.get("/api/v1/hello", headers={"Authorization": f"Bearer {hq_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "round trip web → api → db complete" in body["message"]
    assert body["db_time"] is not None
