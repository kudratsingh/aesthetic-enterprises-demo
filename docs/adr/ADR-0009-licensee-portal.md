# ADR-0009: Licensee portal — checklist, vault, reorders into the ledger

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 7

## Context

Phase 7 (built on the owner's explicit request — the post-MVP gate in CLAUDE.md
§6): a 60-day onboarding checklist, a document vault, and a product reorder
flow "tied to the lots ledger". The MVP discipline still applies: smallest
production-shaped version of each.

## Decision

- **Checklist instances, no template table.** `onboarding_tasks` rows are
  stamped per org from a fixed template constant (`ONBOARDING_TEMPLATE` in
  `services/portal.py`); the seed materializes them with realistic progress
  (three newest orgs mid-checklist). A template table arrives only when
  per-network templates are a real requirement — same reasoning as the ramp
  formula (ADR-0008). Completion is idempotent; a cross-org completion attempt
  404s because RLS hides the row (no existence leak).
- **Vault is text-only.** `portal_documents` stores title/category/body; real
  file uploads mean object storage, signed URLs, and virus scanning — a
  deliberate non-goal until Phase 9 hardening. Never PHI, as everywhere.
- **Orders request; the ledger delivers.** `product_orders` +
  `product_order_lines` carry draft → submitted → fulfilled. HQ fulfillment
  assigns a lot per product line and writes **real shipment rows** — on-hand
  moves only via the append-only ledger and its triggers (ADR-0003). The order
  never mutates stock itself, so supply truth has exactly one source. Lot
  assignment validates lot↔product identity (422 on mismatch).
- All four tables carry `org_id` with the standard tenant-isolation policy
  (ADR-0002), FORCE RLS, conditional grants.

## Consequences

- Phase 7 exit is testable end-to-end: operator creates → submits; HQ fulfills;
  the operator's on-hand rises through the ledger — asserted in
  `test_reorder_flow_end_to_end_lands_in_supply_ledger`.
- Reorder thresholds/auto-suggestions (PROJECT_CONTEXT supply loop, post-MVP)
  can read on-hand vs order history without schema changes.
- The vault's text-only constraint is visible in the UI copy so nobody mistakes
  it for a compliant document store.
