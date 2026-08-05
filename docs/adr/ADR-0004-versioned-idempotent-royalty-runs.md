# ADR-0004: Versioned, idempotent royalty runs

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 2

## Context

Royalty recalculation after corrected inputs is a certainty (operators fix
locked reports via corrections), and audit clauses in license agreements make
traceable recomputation a requirement. Invariant 3 demands
`run_royalty_period` be idempotent per (period, inputs) and versioned;
invariant 2 demands locked revenue reports be immutable; run policy A3 says a
location without a locked report is excluded and *recorded on the run*.

## Decision

- **Input fingerprint.** A run's inputs are hashed into
  `royalty_runs.input_fingerprint`: SHA-256 over canonical JSON
  (sorted keys, sorted by location id) of the period plus, per included
  location, `(location_id, report_id, net_base_cents, rate,
  monthly_minimum_cents, active_days, days_in_period)`, plus the excluded set
  `(location_id, reason)`. The `report_id` is deliberately part of it: a locked
  correction with identical figures still changes the fingerprint, because the
  run must be traceable to the exact attested documents it billed from.
  Exclusions are inputs too — a location moving between "excluded" and "billed"
  must read as changed inputs even when every line item stays the same.
- **Version semantics.** `run_royalty_period(period)` computes the fingerprint
  first. If it equals the fingerprint of the **latest** version for the
  period, that version is returned untouched (idempotency); otherwise version
  N+1 is appended. Comparing only against the latest version means an input
  state that changes and later reverts produces a fresh version rather than
  resurrecting an old one — the version sequence stays a faithful timeline of
  "what HQ could have billed at each point". `(period, version)` is unique;
  line items reference exactly one run; prior versions and their line items
  are never mutated (append-only, same reasoning as ADR-0003: for
  financial-adjacent records the history *is* the product).
- **Excluded locations** are rows in `royalty_run_exclusions`
  `(run_id, location_id, reason, org_id)` — a table, not an array column on
  `royalty_runs`, for two reasons: it carries a per-location `reason`
  (`no_locked_report`, `no_active_agreement`), and it is tenant-scoped under
  the standard RLS policy (ADR-0002) so an operator sees only its own
  exclusions while `royalty_runs` itself stays network-shared read. Written
  once with its run and never updated thereafter.
- **Invariant 2 at the database.** A `BEFORE UPDATE OR DELETE` trigger on
  `revenue_reports` rejects any mutation of a row whose `OLD.status` is
  `locked`. There is deliberately **no exception path**: the sanctioned
  correction flow (`create_correction`) INSERTs a new draft whose
  `supersedes` column points at the locked original, so linking never touches
  the locked row. "Current locked report" for a run is derived by anti-join —
  a locked report not superseded by another *locked* report; a pending draft
  correction does not un-lock its predecessor. Transitions into `locked`
  (submit runs draft→submitted→locked in one transaction) pass because the
  guard reads `OLD.status`.
- **Invoicing interlock** (invariant 6): one invoice per (run, org), enforced
  by a unique constraint. Re-issuing for a run with live invoices returns
  them unchanged; only the latest run version of a period may be invoiced, and
  its invoices supersede the period's prior ones per org via `superseded_by` —
  the only column ever written on an existing invoice.

## Consequences

- Reruns are safe to trigger blindly (button-mash proof): identical inputs
  can never fork a new version or drift an existing one.
- Every historical run remains reproducible and attributable to exact report
  rows; disputes replay from data, not memory.
- A rerun is required after any correction locks — the demo flow (Phase 4
  variance story) leans on this: correct → rerun → new version → new invoices.
- The fingerprint is an implementation detail of idempotency, not an API
  contract; changing its composition later simply produces one extra version.

## Alternatives considered

- **Compare against any prior version's fingerprint:** rejected — returning a
  stale mid-sequence version when inputs revert would make "latest version"
  disagree with current inputs, which invoicing depends on.
- **`excluded_location_ids` array on `royalty_runs`:** rejected — no room for
  a reason, and `royalty_runs` is network-shared read, so the array would leak
  other orgs' location ids to every operator.
- **Allowing a `superseded_by` back-pointer on locked reports:** rejected — it
  would require an exception in the lock trigger; the successor-side link
  gives the same query power with full immutability.
- **Mutating a single run per period in place:** rejected — destroys the audit
  trail and breaks invariant 6 (invoices must pin the exact computation they
  billed).
