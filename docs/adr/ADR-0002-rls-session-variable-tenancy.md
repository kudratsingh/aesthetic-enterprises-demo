# ADR-0002: RLS session-variable tenancy

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 1

## Context

Tenancy bugs in application code are the most common multi-tenant failure mode: one
forgotten WHERE clause leaks another operator's revenue. CLAUDE.md §2.3 mandates
enforcement in Postgres itself.

## Decision

- Every tenant-scoped table carries `org_id` and gets `ENABLE` + `FORCE ROW LEVEL
  SECURITY` with one `tenant_isolation` policy:
  `USING/WITH CHECK (app.role = 'hq_admin' OR org_id = app.org_id)` — the HQ bypass
  is inside the policy, never a code branch.
- Context comes from transaction-local settings: the FastAPI dependency
  (`app/db/tenancy.py`) opens the transaction and runs
  `set_config('app.org_id'/'app.role', …, true)` from the verified JWT before any
  query. `true` = transaction-scoped, so context cannot leak across pooled
  connections. `set_config` is used instead of `SET LOCAL` because it accepts bind
  parameters.
- Unset context reads as NULL (`current_setting(…, true)` + `NULLIF`) → every
  policy is false → deny by default (tested).
- Network-shared tables (`products`, `lots`, `royalty_runs`): SELECT for any
  authenticated role, writes HQ-only. `users` has an extra `auth_service` SELECT
  policy so login can look up a user before any tenant context exists (ADR-0006).
- **The app must connect as a non-superuser** — superusers bypass RLS
  unconditionally. Locally/CI that's `cnos_app` (created by
  `infra/initdb/01-app-role.sql`; compose's `cnos` is a superuser and is used for
  DDL only via `MIGRATIONS_DATABASE_URL`). On Neon the single `neondb_owner` role
  is the table owner but not superuser — `FORCE` is what binds RLS to it.

## Consequences

- Invariant 5 is testable end-to-end (two operators, cross-org reads/writes all
  fail) and runs in CI against real Postgres.
- Every new tenant-scoped table must ship RLS policies + grants in the same
  migration; CI's RLS tests catch a table that forgets.
- Location-level scoping for `clinic_staff` (permissions matrix) stays at the
  service layer for the MVP; RLS enforces the org boundary.

## Alternatives considered

- **App-level filtering:** rejected — the failure mode this exists to eliminate.
- **Schema-per-tenant / DB-per-tenant:** rejected — operational overkill for ~20
  locations and it makes cross-network HQ queries (the product's core) painful.
- **Postgres role-per-tenant:** rejected — connection pooling becomes a mess;
  session variables compose with a single pooled app role.
