# ADR-0010: Mock collections provider behind a Protocol seam

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 6

## Context

Phase 6's exit criterion is "an invoice can be paid in test mode and aging
updates itself." No real Stripe account exists, and CLAUDE.md forbids
third-party branding and non-synthetic data; the demo also must run with zero
network dependencies. What matters architecturally is not the provider but the
seams: where checkout starts, how payment status flows back, and which single
code path is allowed to mark an invoice paid (invariant 6 already constrains
invoice mutation to supersession + the paid transition).

## Decision

- **Provider Protocol seam.** `app/services/collections.py` defines the whole
  provider contract as a Protocol: `create_checkout(invoice) →
  CheckoutSession(provider_ref, checkout_url)`. The service persists
  `provider_ref` and treats it and the URL as opaque. `payment_provider`
  (config, default `"mock"`) selects the implementation; an unknown name fails
  closed (503). A real Stripe implementation is one new class creating a real
  Checkout Session and returning its id/url — no caller changes. **ACH is the
  same seam**: an ACH provider returns a mandate/debit reference as
  `provider_ref` and its own hosted flow URL; only settlement latency differs,
  which the status model below already tolerates.
- **MockStripeProvider** is the only implementation: deterministic refs
  (`mock_cs_<invoice-id-12-hex>`), URLs under `https://checkout.mock.local/`
  (can never resolve), zero I/O — no stripe SDK dependency, no network calls.
  Determinism doubles as idempotency: re-checkout of an invoice reproduces the
  same session, backed by a UNIQUE `provider_ref` column.
- **payments table** (tenant-scoped, standard RLS policy, ADR-0002): one row
  per checkout session, `initiated → succeeded | failed`, plus
  `failed → succeeded` (payer retried the same session). `succeeded` is
  terminal — an out-of-order failure event can never un-pay an invoice.
  Checkout refuses paid and superseded invoices (the live successor carries
  the balance, invariant 6) and returns an existing open payment instead of
  duplicating it.
- **`POST /webhooks/payments`** copies the ingest webhook contract verbatim
  (ADR-0005): HMAC-SHA256 over the raw body, hex digest in
  `X-Webhook-Signature`, shared secret `PAYMENT_WEBHOOK_SECRET`, constant-time
  compare, 401 on mismatch, 503 fail-closed when unset. Events run in the
  machine `hq_admin` RLS context via the standard `set_config` pattern — a
  policy-level role, never a bypass. **Webhook idempotency** keys on
  `provider_ref`: replays of a delivered event no-op with 200 (providers
  retry aggressively; the alternative — dedup tables of event ids — buys
  nothing here because our state machine is already monotone).
- **Success is the only invoice-touching path**, and it goes through
  `royalty.mark_invoice_paid` with the machine HQ claims — one sanctioned
  payment transition, not a second implementation. Failure marks only the
  payment; the invoice stays collectible.
- **`POST /collections/payments/{payment_id}/simulate`** exists because the
  mock has no hosted checkout page: with a real provider, the payer completes
  checkout on the provider's site and the provider calls the webhook. Simulate
  is that completion for dev/demo — callable by any authenticated user who can
  see the payment (operator: own org via RLS; HQ: any), and it marks success
  through the same internal path the webhook uses. The UI never computes
  HMACs; signatures stay a server-to-server concern.
- **Aging needs no code**: it is read-derived from unpaid live invoices, so a
  paid invoice drops out on its own. The integration suite proves the full
  loop: checkout → signed webhook → invoice reads paid → aging bucket count
  decrements.

## Consequences

- The demo shows the full money-movement loop with zero external dependencies,
  and the cutover to real Stripe is confined to one class + two config values
  (provider name, webhook secret — the real endpoint would also verify
  Stripe's signature scheme inside the same seam).
- Payment history is queryable per tenant (`GET /collections/payments`) and
  invariant-5-tested: an operator cannot see another org's payments.
- The mock cannot exercise provider-side failure modes (network flakes,
  partial captures, disputes); those arrive with the real implementation and
  belong to Phase 9 hardening.
- A second checkout provider (e.g. ACH) will need a provider column-aware
  selection per invoice or org; the schema already records `provider` per
  payment, so that is config, not migration.

## Alternatives considered

- **Stripe test mode now:** rejected — requires an account, an SDK dependency,
  and network access in CI/demo for behavior we'd immediately hide behind an
  interface anyway; the interview-relevant artifact is the seam, not the
  vendor call.
- **Marking invoices paid directly in the webhook handler:** rejected — a
  second payment path would drift from `mark_invoice_paid`'s rules (superseded
  refusal, idempotency); calling the existing service keeps one truth.
- **UI-computed HMAC calling the webhook from the browser:** rejected — the
  shared secret would ship to every client, making the signature theater; the
  simulate endpoint keeps the webhook contract honest.
- **Append-only payments ledger:** rejected — payments are provider-mirrored
  state, not our financial record (the invoice is); reversing entries would
  add ceremony without an audit consumer. The audit log lands in Phase 9.
