from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast, get_args

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings

Role = Literal["hq_admin", "operator", "clinic_staff"]


@dataclass(frozen=True)
class TokenClaims:
    """Verified identity attached to a request. Phase 1 feeds org_id/role into RLS session vars."""

    sub: str
    org_id: str
    role: Role


def mint_token(claims: TokenClaims, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": claims.sub,
        "org_id": claims.org_id,
        "role": claims.role,
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_ttl_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, settings: Settings) -> TokenClaims:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token") from exc
    role = payload.get("role")
    if role not in get_args(Role):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid role claim")
    return TokenClaims(
        sub=str(payload.get("sub")),
        org_id=str(payload.get("org_id")),
        role=cast(Role, role),
    )


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenClaims:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return decode_token(credentials.credentials, settings)


CurrentUser = Annotated[TokenClaims, Depends(get_current_user)]
