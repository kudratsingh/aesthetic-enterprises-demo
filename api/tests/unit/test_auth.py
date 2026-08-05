from httpx import AsyncClient

from app.core.config import Settings
from app.core.security import TokenClaims, decode_token, mint_token


async def test_hello_without_token_is_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/hello")
    assert resp.status_code == 401


async def test_hello_with_garbage_token_is_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/hello", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_token_mint_decode_roundtrip(settings: Settings) -> None:
    claims = TokenClaims(sub="u1", org_id="org-a", role="operator")
    assert decode_token(mint_token(claims, settings), settings) == claims


async def test_dev_token_endpoint_mints_valid_token(
    client: AsyncClient, settings: Settings
) -> None:
    resp = await client.post("/api/v1/auth/dev-token", json={"role": "operator", "org_id": "org-a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    claims = decode_token(body["access_token"], settings)
    assert claims.role == "operator"
    assert claims.org_id == "org-a"
