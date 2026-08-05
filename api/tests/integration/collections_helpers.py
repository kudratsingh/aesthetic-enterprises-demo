"""Shared setup for collections integration tests (Phase 6, ADR-0010).

Every scenario starts from one issued invoice (operator org → locked report →
run → invoice) produced through the real service path. Periods are private per
test (stable inputs between reruns) and deliberately in the PAST (2010+, with
org activation/agreement dates to match): the network KPI query windows the
most recent months present in the shared database, and far-future periods
(royalty_helpers.unique_period's 2040+) would push real fixture months out of
that window for suites that run after this one.
"""

import hashlib
import hmac
import itertools
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.core.config import Settings
from app.core.security import TokenClaims, mint_token
from app.services import royalty
from tests.conftest import HQ_ORG_ID, tenant_session, unique
from tests.integration.royalty_helpers import HQ_ACTOR, lock_report

PAYMENT_WEBHOOK_SECRET = "integration-test-payment-secret"
PAYMENT_WEBHOOK_PATH = "/api/v1/webhooks/payments"

# gross 1,000,000 cents at the default 7% → a 70,000-cent invoice.
GROSS_CENTS = 1_000_000
INVOICE_CENTS = 70_000


_ACTIVATED_ON = date(2005, 1, 1)

_period_counter = itertools.count()


def past_period() -> date:
    """A month no other suite touches: 2010 onward, safely before any fixture
    month, so it can never displace one from the KPI window (see docstring)."""
    n = next(_period_counter)
    return date(2010 + n // 12, n % 12 + 1, 1)


@dataclass(frozen=True)
class IssuedInvoice:
    invoice_id: uuid.UUID
    org_id: uuid.UUID
    location_id: uuid.UUID
    user_id: uuid.UUID


async def _create_operator() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """One operator org with one location, one user, and a 7% agreement, all
    effective from 2005 so past_period() months are billable."""
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        org_id: uuid.UUID = (
            await s.execute(
                text(
                    "INSERT INTO orgs (id, kind, name)"
                    " VALUES (gen_random_uuid(), 'operator', :n) RETURNING id"
                ),
                {"n": unique("col-org")},
            )
        ).scalar_one()
        loc_id: uuid.UUID = (
            await s.execute(
                text(
                    "INSERT INTO locations (id, org_id, name, activated_on)"
                    " VALUES (gen_random_uuid(), :org, :n, :d) RETURNING id"
                ),
                {"org": org_id, "n": unique("col-loc"), "d": _ACTIVATED_ON},
            )
        ).scalar_one()
        user_id: uuid.UUID = (
            await s.execute(
                text(
                    "INSERT INTO users (id, org_id, email, password_hash, role, full_name,"
                    " is_active) VALUES (gen_random_uuid(), :org, :email, 'x', 'operator',"
                    " 'Collections Operator', true) RETURNING id"
                ),
                {"org": org_id, "email": f"{unique('col-user')}@clinic-network-os.test"},
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO license_agreements (id, org_id, royalty_rate, base_definition,"
                " monthly_minimum_cents, effective_from)"
                " VALUES (gen_random_uuid(), :org, :rate, 'net_treatment_revenue', NULL, :d)"
            ),
            {"org": org_id, "rate": Decimal("0.0700"), "d": _ACTIVATED_ON},
        )
    return org_id, loc_id, user_id


async def issued_invoice() -> IssuedInvoice:
    """One org, one locked report, one run, one live issued invoice."""
    org_id, loc_id, user_id = await _create_operator()
    period = past_period()
    await lock_report(org_id, loc_id, user_id, period, gross_cents=GROSS_CENTS)
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        run = await royalty.run_royalty_period(s, HQ_ACTOR, period)
    async with tenant_session(HQ_ORG_ID, "hq_admin") as s:
        issued = await royalty.issue_invoices(s, HQ_ACTOR, uuid.UUID(str(run.id)))
    invoices = {uuid.UUID(str(inv.org_id)): inv for inv in issued.invoices}
    return IssuedInvoice(
        invoice_id=uuid.UUID(str(invoices[org_id].id)),
        org_id=org_id,
        location_id=loc_id,
        user_id=user_id,
    )


def hq_headers(settings: Settings) -> dict[str, str]:
    token = mint_token(
        TokenClaims(sub="collections-test", org_id=HQ_ORG_ID, role="hq_admin"), settings
    )
    return {"Authorization": f"Bearer {token}"}


def operator_headers(settings: Settings, org_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, str]:
    token = mint_token(TokenClaims(sub=str(user_id), org_id=str(org_id), role="operator"), settings)
    return {"Authorization": f"Bearer {token}"}


def sign_payment_body(body: bytes) -> str:
    return hmac.new(PAYMENT_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def mock_provider_ref(invoice_id: uuid.UUID) -> str:
    """The MockStripeProvider's deterministic ref for an invoice."""
    return f"mock_cs_{invoice_id.hex[:12]}"
