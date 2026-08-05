import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import Settings
from app.core.security import decode_token
from app.services.auth import hash_password
from tests.conftest import HQ_ORG_ID, tenant_session, unique

pytestmark = pytest.mark.integration


async def _create_user(
    role: str = "operator", is_active: bool = True
) -> tuple[str, str, uuid.UUID]:
    email = f"{unique('user')}@clinic-network-os.test"
    password = "demo-password-1234"
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        org_id = (
            await s.execute(
                text(
                    "INSERT INTO orgs (id, kind, name)"
                    " VALUES (gen_random_uuid(), 'operator', :n) RETURNING id"
                ),
                {"n": unique("org")},
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO users (id, org_id, email, password_hash, role, full_name, is_active)"
                " VALUES (gen_random_uuid(), :org, :email, :hash, :role, 'Test User', :active)"
            ),
            {
                "org": org_id,
                "email": email,
                "hash": hash_password(password),
                "role": role,
                "active": is_active,
            },
        )
    return email, password, org_id


async def test_login_returns_token_with_tenant_claims(
    client: AsyncClient, settings: Settings
) -> None:
    email, password, org_id = await _create_user()
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    claims = decode_token(resp.json()["access_token"], settings)
    assert claims.org_id == str(org_id)
    assert claims.role == "operator"


async def test_login_wrong_password_is_401(client: AsyncClient) -> None:
    email, _, _ = await _create_user()
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_credentials"


async def test_login_unknown_email_is_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@clinic-network-os.test", "password": "whatever"},
    )
    assert resp.status_code == 401


async def test_login_inactive_user_is_401(client: AsyncClient) -> None:
    email, password, _ = await _create_user(is_active=False)
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 401


async def test_login_token_drives_hello_round_trip(client: AsyncClient) -> None:
    email, password, _ = await _create_user()
    token = (
        await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    ).json()["access_token"]
    resp = await client.get("/api/v1/hello", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "round trip web → api → db complete" in resp.json()["message"]
