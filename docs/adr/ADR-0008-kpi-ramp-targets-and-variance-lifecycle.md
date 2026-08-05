# ADR-0008: KPI ramp targets as formula; variance flag lifecycle

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 4

## Context

The HQ dashboard compares each location against "ramp targets" (CLAUDE.md Phase 4),
and the variance engine (rule R5) turns supply consumption into an expected revenue
floor. Both need a definition of "expected" that ships in the MVP without new
schema.

## Decision

**Ramp targets are a formula, not a table.** `target_treatments(months_active) =
round(28 × min(1, 0.3 + 0.06 × months_active))` — the same ramp shape the seed
world grows on, so attainment reads sensibly from seeded data. Constants live in
`app/services/funnel.py`.

**Variance flags are compute-on-demand, idempotent per (location, period).**
`POST /variance/compute` (HQ) evaluates every location: floor = administrations ×
trailing-90-day network avg ticket (`plan_value ÷ planned_treatments`, fallback to
the seed's stable $1,000 when no sales history); flag when reported net_base <
floor × threshold (config, default 0.75). Recompute refreshes the numbers on an
existing flag but never resets its review status — an analyst's `reviewed/resolved`
verdict survives new data. Operators see only their own **resolved** flags
(permissions matrix); RLS scopes rows, the service filters status.

## Consequences

- No migration; targets tune by editing two constants, threshold by env var.
- Formula targets are demo-shaped: a real network would negotiate per-location
  targets into license agreements — that's a schema change deferred until Phase 7+
  needs it (this ADR would then be superseded).
- Compute-on-demand (vs a scheduled job) keeps the MVP without background
  infrastructure (ADR-0001 consequence) and makes the demo moment explicit:
  HQ clicks, the underreporter lights up.

## Alternatives considered

- **Targets table now:** rejected — invents commercial terms no one has negotiated
  and adds schema for a formula the seed already encodes.
- **Flag auto-reopen on recompute:** rejected — silently discarding review verdicts
  is how a variance feature loses analyst trust (PROJECT_CONTEXT §4 R5 rationale).
