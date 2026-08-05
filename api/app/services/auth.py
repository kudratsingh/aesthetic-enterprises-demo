from typing import cast

import bcrypt
from sqlalchemy import select, text

from app.core.config import Settings
from app.core.errors import InvalidCredentialsError
from app.core.security import Role, TokenClaims, mint_token
from app.db.engine import get_session_factory
from app.db.models import User

# Verified when no user matches, so a missing account costs the same time as a
# wrong password.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def authenticate(email: str, password: str, settings: Settings) -> str:
    """Verify credentials and mint a JWT whose claims feed the RLS context.

    Login precedes any tenant context, so the lookup runs under the dedicated
    'auth_service' RLS policy (SELECT on users only; see ADR-0006).
    """
    async with get_session_factory()() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'auth_service', true)"))
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    if user is None:
        bcrypt.checkpw(password.encode(), _DUMMY_HASH)
        raise InvalidCredentialsError("invalid email or password")
    if not user.is_active or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        raise InvalidCredentialsError("invalid email or password")

    claims = TokenClaims(sub=str(user.id), org_id=str(user.org_id), role=cast(Role, user.role))
    return mint_token(claims, settings)
