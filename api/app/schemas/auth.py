from typing import Literal

from pydantic import BaseModel

from app.core.security import Role


class DevTokenRequest(BaseModel):
    role: Role = "hq_admin"
    org_id: str = "org-hq"
    sub: str = "dev-user"


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
