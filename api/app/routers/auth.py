from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.auth import authenticate

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
async def login(
    body: LoginRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> TokenResponse:
    """Credential login against seeded users (ADR-0006). Replaces the Phase 0
    dev-token stub. Claims (sub, org_id, role) drive the RLS tenant context."""
    return TokenResponse(access_token=await authenticate(body.email, body.password, settings))
