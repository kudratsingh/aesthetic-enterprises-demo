# ADR-0006: Auth — bcrypt credentials, HS256 JWT, claims drive RLS

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 1

## Context

Phase 0 shipped a dev-token stub (mint any role, no credentials). Phase 1 needs
real users whose identity flows into the RLS tenant context (ADR-0002), without
introducing an external IdP for a demo.

## Decision

- **Users table** with bcrypt password hashes (`bcrypt` library directly, default
  cost; a dummy-hash comparison on unknown emails keeps timing uniform).
- **`POST /api/v1/auth/login`** verifies credentials and mints an HS256 JWT
  (PyJWT, `JWT_SECRET` env, 1h TTL) with claims `sub` (user id), `org_id`, `role`.
  The tenancy dependency copies exactly these claims into `app.org_id`/`app.role` —
  the token *is* the tenant context.
- **Pre-auth lookup policy:** login runs before any tenant context, so the auth
  service sets `app.role = 'auth_service'`, matching a users-SELECT-only RLS
  policy. No RLS bypass, no admin connection in the request path.
- The dev-token endpoint is deleted (not gated) — one auth path.
- `scripts/mint_dev_token.py` remains as a local curl convenience; it signs with
  the same secret and grants nothing a login couldn't.

## Consequences

- Stateless auth: no session store, revocation = TTL expiry. Acceptable for the
  demo; Phase 9 hardening revisits (refresh tokens/rotation if ever needed).
- Compromised `JWT_SECRET` = full tenant impersonation. It lives only in Render's
  env (generated) and local dev defaults; never logged, never committed.
- Seeded demo users (Phase 1 seed) are the demo's login surface; passwords are
  synthetic and documented in the runbook on purpose.

## Alternatives considered

- **External IdP (Auth0/Clerk/Supabase):** rejected — third-party dependency and
  branding in a neutral demo, and it hides the claims→RLS mechanism this project
  exists to demonstrate.
- **Passlib:** rejected — maintenance concerns; direct `bcrypt` is one call each way.
