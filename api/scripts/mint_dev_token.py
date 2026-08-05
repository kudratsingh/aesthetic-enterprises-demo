"""Mint a dev JWT for local API testing.

Usage: uv run python scripts/mint_dev_token.py [role] [org_id] [sub]
Defaults: hq_admin org-hq dev-user
"""

import sys
from typing import cast, get_args

from app.core.config import get_settings
from app.core.security import Role, TokenClaims, mint_token


def main() -> None:
    role = sys.argv[1] if len(sys.argv) > 1 else "hq_admin"
    org_id = sys.argv[2] if len(sys.argv) > 2 else "org-hq"
    sub = sys.argv[3] if len(sys.argv) > 3 else "dev-user"
    if role not in get_args(Role):
        sys.stderr.write(f"invalid role {role!r}; expected one of {get_args(Role)}\n")
        raise SystemExit(2)
    settings = get_settings()
    if settings.environment == "prod":
        sys.stderr.write("refusing to mint dev tokens in prod environment\n")
        raise SystemExit(2)
    token = mint_token(TokenClaims(sub=sub, org_id=org_id, role=cast(Role, role)), settings)
    sys.stdout.write(token + "\n")


if __name__ == "__main__":
    main()
