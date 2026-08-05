"""Invoice payment lifecycle: manual pay (pre-Phase-6), overdue derivation."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import Settings
from app.core.security import TokenClaims, mint_token
from app.services import royalty
from tests.conftest import HQ_ORG_ID, tenant_session
from tests.integration.royalty_helpers import (
    HQ_ACTOR,
    create_operator,
    lock_report,
    unique_period,
)

pytestmark = pytest.mark.integration


async def _issued_invoice() -> tuple[UUID, UUID]:
    """One org, one locked report, one run, one invoice. Returns (invoice, org)."""
    org_id, loc_id, user_id = await create_operator()
    period = unique_period()
    await lock_report(org_id, loc_id, user_id, period, gross_cents=1_000_000)
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        run = await royalty.run_royalty_period(s, HQ_ACTOR, period)
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        issued = await royalty.issue_invoices(s, HQ_ACTOR, UUID(str(run.id)))
    return UUID(str(issued.invoices[0].id)), org_id


def _hq_headers(settings: Settings) -> dict[str, str]:
    token = mint_token(TokenClaims(sub="pay-test", org_id=HQ_ORG_ID, role="hq_admin"), settings)
    return {"Authorization": f"Bearer {token}"}


async def test_invoice_pay_is_hq_only_and_idempotent(
    client: AsyncClient, settings: Settings
) -> None:
    invoice_id, org_id = await _issued_invoice()

    op_token = mint_token(
        TokenClaims(sub="pay-test", org_id=str(org_id), role="operator"), settings
    )
    forbidden = await client.post(
        f"/api/v1/royalty/invoices/{invoice_id}/pay",
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert forbidden.status_code == 403

    first = await client.post(
        f"/api/v1/royalty/invoices/{invoice_id}/pay", headers=_hq_headers(settings)
    )
    assert first.status_code == 200
    assert first.json()["status"] == "paid"

    again = await client.post(
        f"/api/v1/royalty/invoices/{invoice_id}/pay", headers=_hq_headers(settings)
    )
    assert again.status_code == 200
    assert again.json()["status"] == "paid"


async def test_unpaid_invoice_past_due_reads_overdue(
    client: AsyncClient, settings: Settings
) -> None:
    invoice_id, _ = await _issued_invoice()

    # Invoices are mutable rows (unlike ledgers); backdate due_date directly.
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        await s.execute(
            text(
                "UPDATE invoices SET due_date = current_date - CAST(:days AS integer)"
                " WHERE id = :id"
            ),
            {"days": 10, "id": invoice_id},
        )

    listing = await client.get("/api/v1/royalty/invoices", headers=_hq_headers(settings))
    row = next(r for r in listing.json() if r["id"] == str(invoice_id))
    assert row["status"] == "overdue"  # derived at read time; storage stays 'issued'

    paid = await client.post(
        f"/api/v1/royalty/invoices/{invoice_id}/pay", headers=_hq_headers(settings)
    )
    assert paid.json()["status"] == "paid"  # payment beats overdue derivation
