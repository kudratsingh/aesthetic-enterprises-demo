# ADR-0003: Append-only supply ledger

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 1

## Context

Shipments and administrations are financial-adjacent records feeding royalty
verification (the supply-implied revenue floor) and recall queries. "Who changed
what, when" is the product; UPDATE/DELETE destroys it.

## Decision

- `shipments` and `administrations` are insert-only: `BEFORE UPDATE OR DELETE`
  triggers raise. Corrections are **reversing entries** — a new row with negated
  qty and `reversal_of` pointing at the original.
- On-hand per (location, lot) is materialized in `location_lot_on_hand`,
  maintained by `AFTER INSERT` triggers on both ledgers. Its
  `CHECK (on_hand >= 0)` **is** invariant 1: the database, not the service,
  guarantees stock can't go negative.
- The maintenance function is UPDATE-first with INSERT fallback. This is
  deliberate: with `INSERT … ON CONFLICT DO UPDATE`, Postgres evaluates CHECK
  constraints on the *candidate* row before conflict resolution, so any
  negative-delta candidate (every administration) would fail the CHECK even with
  ample stock. Discovered the hard way; the invariant test now covers the
  drain-to-zero path.
- Row locks on the balance row serialize concurrent consumption of the same
  (location, lot) — last one past zero fails, which is the correct outcome.

## Consequences

- Idempotent, auditable history for free; the variance engine (R5) can trust
  consumption totals.
- Reads of on-hand are O(1) — no ledger scans in request paths.
- Expired-lot rejection (R6) stays service-level (Phase 4) — it's a business
  rule, not a ledger-integrity rule.
