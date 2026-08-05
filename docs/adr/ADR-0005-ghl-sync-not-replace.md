# ADR-0005: GHL sync-not-replace funnel ingestion

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 5

## Context

The consult-to-treatment funnel already lives in a third-party marketing CRM
(GHL-style) that the licensor manages for its operators. This system's wedge is
owning the canonical data and the money logic (royalties, verification) — not
re-implementing a CRM. Replacing the CRM is a later, political decision;
the architecture must stay agnostic to it (PROJECT_CONTEXT §6). R7 requires
webhook and CSV ingestion into `leads`/`consults` that is idempotent and never
mutates royalty or supply aggregates.

## Decision

- **Sync, don't replace.** `POST /api/v1/webhooks/ghl` and
  `POST /api/v1/imports/leads` mirror CRM state into the funnel tables; the CRM
  remains the operational tool. Ingestion feeds only the funnel/KPI layer —
  royalty and supply aggregates are written exclusively by their own services,
  so a compromised or misbehaving feed can skew dashboards but never money.
- **Idempotency = external identity.** Lead identity is `(source, external_id)`
  under the existing partial unique index `uq_leads_source_external_id`;
  replays hit `ON CONFLICT DO NOTHING` — **first write wins**, because a lead
  is a point-in-time acquisition fact (a replay carries no newer truth about
  when/where the contact entered the funnel). Consult identity is
  `(lead, scheduled_at)`; replays apply **update-freshness on non-null fields
  only** (`occurred_at`, `outcome`) — fields gain information and never lose
  it, so out-of-order deliveries (a late "booked" replay after "completed")
  cannot erase an outcome. Consults deliberately have no `external_id` column
  in the MVP (R7 fits the existing schema); a real two-way integration would
  add one, at the cost of a migration — a reschedule therefore reads as a new
  consult, which is acceptable for KPI counting.
- **Demo payload contract.** This repo defines the payload shape (documented in
  `docs/runbooks/integrations.md`): two event types (`contact`, `appointment`),
  each embedding the full contact so the lead upsert is always possible. CRM
  event subtypes (created/updated/rescheduled) are collapsed by the sender —
  ingestion is an idempotent upsert of current state either way; we sync state,
  we don't replay CRM history.
- **Location mapping.** Payloads carry OUR location UUID in `location_id`, via
  a licensor-configured custom field on the CRM side. The licensor controls the
  CRM, so the mapping is configured once at onboarding, and ingestion needs no
  name-matching heuristics. Unknown UUIDs are rejected (400) — never guessed.
- **HMAC-SHA256 over the raw body**, hex digest in `X-Webhook-Signature`,
  shared secret from `GHL_WEBHOOK_SECRET`, constant-time compare. Raw bytes
  (not re-serialized JSON) so signer and verifier hash identical input. Missing
  or wrong signature → 401; unset secret → **503, fail closed** — a deploy that
  forgot the secret must reject events loudly, not accept them silently.
- **Tenancy.** Ingestion runs in an `hq_admin` RLS context via the standard
  `set_config` pattern (ADR-0002): licensor-managed systems feed the funnel on
  behalf of the whole network, and the HQ role is already a policy-level
  concept. Rows are written with the destination location's `org_id`, so
  operators see their own leads/consults under the ordinary tenant policy. RLS
  stays enabled and enforced — this is a role the policies know, not a bypass.
  The CSV import additionally requires an authenticated `hq_admin` JWT and runs
  on the ordinary request tenant session.

## Consequences

- Replays are safe to fire blindly (webhook retries, re-imports) — the demo
  can prove it with two identical curl calls and one row.
- The funnel can be fed from two directions (live webhook, historical CSV)
  through one upsert path, so their semantics can never drift apart.
- Reported-revenue verification (R5) gains an independent top-of-funnel signal
  without this system taking over the CRM's job.
- The payload contract is ours, not GHL's real schema — a production
  integration would add a translation layer at the edge (and likely a consult
  `external_id` column), leaving the upsert semantics unchanged.
- A shared static secret is the simplest credible webhook auth; rotation or
  per-source secrets are deferred until a real integration exists (Phase 8).

## Alternatives considered

- **Replace the CRM outright:** rejected — enormous scope, political rather
  than technical, and unnecessary for the licensor's actual lever (money logic
  and verification).
- **Update-in-place on lead replay (last write wins):** rejected — a webhook
  retry storm could silently rewrite acquisition attribution; leads are facts,
  not state.
- **Consult matching by appointment external_id (new column + index):**
  rejected for the MVP — requires a migration for a demo integration; the
  (lead, scheduled_at) key gives correct replay semantics for the seeded world.
- **Signature over parsed-then-canonicalized JSON:** rejected — any
  serialization difference between sender and verifier breaks verification;
  raw bytes are the only stable contract.
- **Accepting unsigned events when no secret is set:** rejected — fail-open
  ingestion is how synthetic demo systems grow real vulnerabilities.
