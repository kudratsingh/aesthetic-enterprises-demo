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

## Amendment (2026-08-05): BYPASSRLS is not defeated by FORCE

The original decision assumed Neon's single `neondb_owner` role was safe because
`FORCE ROW LEVEL SECURITY` binds the table owner. **That was wrong in a way
tests couldn't see:** Neon grants the database owner the `BYPASSRLS` *attribute*
(`rolbypassrls = true`), and FORCE defeats ownership bypass only — a role with
BYPASSRLS skips every policy regardless. The deployed app connecting as
`neondb_owner` therefore ran with tenancy unenforced, while local/CI (connecting
as unprivileged `cnos_app`) passed every RLS test honestly. Caught by the first
operator-scoped read ever run against production.

Consequences now in force:

- **Production uses the same two-role split as local/CI**: a `cnos_app` login
  role (NOSUPERUSER, NOBYPASSRLS, table grants only) for the app; the owner
  role only for DDL via `MIGRATIONS_DATABASE_URL`.
- **Startup guard**: the app checks `rolsuper OR rolbypassrls` on its own role —
  hard refusal to start in prod, loud warning elsewhere. An integration test
  pins the property for the test role.
- Lesson recorded: an RLS test suite proves the *policies*, not the *deployment*
  — the connecting role's attributes are part of the security boundary and must
  be verified per environment.

## Alternatives considered

- **App-level filtering:** rejected — the failure mode this exists to eliminate.
- **Schema-per-tenant / DB-per-tenant:** rejected — operational overkill for ~20
  locations and it makes cross-network HQ queries (the product's core) painful.
- **Postgres role-per-tenant:** rejected — connection pooling becomes a mess;
  session variables compose with a single pooled app role.
