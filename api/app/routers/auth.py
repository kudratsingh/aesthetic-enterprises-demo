from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.security import TokenClaims, mint_token
from app.schemas.auth import DevTokenRequest, TokenResponse

router = APIRouter(tags=["auth"])


@router.post("/auth/dev-token")
async def dev_token(
    body: DevTokenRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> TokenResponse:
    """Phase 0 stub: mints a signed JWT for any requested role, dev/test environments only.

    Replaced in Phase 1 by real credential auth against seeded users (ADR-0006).
    """
    if settings.environment == "prod":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not available")
    claims = TokenClaims(sub=body.sub, org_id=body.org_id, role=body.role)
    return TokenResponse(access_token=mint_token(claims, settings))
