import bcrypt
from httpx import AsyncClient

from app.core.config import Settings
from app.core.security import TokenClaims, decode_token, mint_token
from app.services.auth import hash_password


async def test_hello_without_token_is_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/hello")
    assert resp.status_code == 401


async def test_hello_with_garbage_token_is_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/hello", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_token_mint_decode_roundtrip(settings: Settings) -> None:
    claims = TokenClaims(sub="u1", org_id="org-a", role="operator")
    assert decode_token(mint_token(claims, settings), settings) == claims


def test_password_hash_verifies_and_salts() -> None:
    h1, h2 = hash_password("s3cret"), hash_password("s3cret")
    assert h1 != h2  # salted
    assert bcrypt.checkpw(b"s3cret", h1.encode())
    assert not bcrypt.checkpw(b"wrong", h1.encode())
