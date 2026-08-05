"""The app's DB role must not be able to skip RLS — the guard behind ADR-0002's
amendment. Locally/CI this asserts cnos_app stays unprivileged; the deployed
app enforces the same check at startup (hard failure in prod)."""

import pytest

from app.db.engine import connected_role_bypasses_rls

pytestmark = pytest.mark.integration


async def test_app_role_cannot_bypass_rls() -> None:
    assert not await connected_role_bypasses_rls(), (
        "the application database role has SUPERUSER or BYPASSRLS — "
        "tenancy would be silently unenforced (see ADR-0002 amendment)"
    )
