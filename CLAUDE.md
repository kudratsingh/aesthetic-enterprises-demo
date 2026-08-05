# CLAUDE.md — clinic-network-os

Operating instructions for Claude Code on this repository. Read fully before any work. When a decision here conflicts with convenience, this file wins.

## 1. What this project is

A multi-tenant network operating system for a clinic licensor: royalty billing on licensee revenue (7% default), network KPI reporting, product lot traceability, and licensee-facing statements. Built as an interview demonstration on production-shaped patterns. Two hard rules that override everything else:

- **All data is synthetic.** Never ingest, generate, or commit real patient data, real revenue figures, or any PHI. Location names may mirror real public clinic names as seed labels; every number attached to them is fabricated and the seed script says so.
- **Neutral branding.** No third-party company names, logos, or trademarks in code, UI, or docs. The product name is `clinic-network-os`.

## 2. Architecture

### 2.1 System shape
```
React SPA (Vite, TS, Cloudflare Pages/Vercel)
        │  HTTPS + JWT (role claims)
        ▼
FastAPI app (single container, Cloud Run/Render, scale-to-zero)
  routers → services (domain logic, transactional) → db layer
        │  asyncpg via pooled connection string
        ▼
Postgres (Neon) — RLS tenancy, invariants live here
        ▲
Inbound: /webhooks/ghl (HMAC-verified), CSV import endpoint
```

### 2.2 Repo layout (monorepo)
```
/api
  /app
    /routers        # thin HTTP layer, no business logic
    /services       # domain logic, one module per aggregate (royalty, supply, funnel, auth)
    /db             # engine, session, RLS context manager, repositories
    /schemas        # Pydantic models (request/response), never ORM objects over the wire
    /core           # config, security, logging, errors
  /migrations       # Alembic
  /tests            # mirrors /app; integration tests hit real Postgres
/web
  /src
    /api            # generated typed client from OpenAPI
    /features       # royalty, dashboard, traceability, auth (feature folders)
    /components     # shared UI only
/infra              # Dockerfile, docker-compose (local pg), deploy configs
/docs               # living context docs — read before working on an area; see §5
  /adr              # ADR-NNNN-title.md, numbered, never deleted
```

### 2.3 Multi-tenancy (non-negotiable design)
Postgres RLS on every tenant-scoped table, keyed on `current_setting('app.org_id')`. A FastAPI dependency opens the transaction and executes `SET LOCAL app.org_id = :org` from the verified JWT before any query. HQ role uses a policy-level bypass (`app.role = 'hq_admin'`), never a code-level branch that skips RLS. No query runs outside the tenancy context manager. Weakening or bypassing RLS "temporarily" is forbidden.

### 2.4 Data model (aggregates)
- **Identity/tenancy:** orgs (hq | operator), locations, users (hq_admin, operator, clinic_staff), license_agreements (royalty_rate default 0.07, base_definition, monthly_minimum, effective_from/to).
- **Funnel:** leads → consults → sales (plan_value, financing_flag) → treatments. Source-attributed, timestamped stage transitions.
- **Supply (append-only):** products → lots (supplier, expiry) → shipments (lot→location, qty) → administrations (lot→treatment→synthetic_patient_ref). On-hand derived, protected by CHECK; rows are never updated or deleted — corrections are reversing entries.
- **Royalty:** revenue_reports (location, period, gross, refunds, net_base, status draft→submitted→locked, attested_by/at) → royalty_runs (period, version, generated_at) → royalty_line_items (base, rate, minimum_applied, adjustments, amount_due) → invoices (issued/paid/overdue, due_date). variance_flags join reported revenue against the expected floor derived from administrations × avg ticket.

### 2.5 Invariants (each one has a test with the same name)
1. Administrations ledger cannot drive location on-hand negative (DB-enforced).
2. A locked revenue_report is immutable; corrections create a new report version.
3. `run_royalty_period` is idempotent per (period, inputs) and versioned — reruns create a new royalty_run version; prior versions are never mutated.
4. Minimum royalty applies when 7% of base < monthly_minimum.
5. An operator can never read or write another org's rows (RLS test using two seeded operators).
6. Invoices reference exactly one royalty_run version; regenerating invoices supersedes, never edits.

### 2.6 Frontend
Vite + React + TS strict. TanStack Query for server state; no global client state beyond auth. Routes split by role at the router level (HQ shell vs operator shell). Typed API client generated from the FastAPI OpenAPI spec in CI — hand-written fetch types are forbidden. Keep the component surface small; this is a demo of a system, not a design system.

## 3. Engineering standards

- **Python:** 3.12, uv for dependency management. PEP8 enforced by ruff (lint + format); mypy --strict passes with zero ignores outside a documented allowlist. Full type annotations. No bare `except`. Services raise typed domain errors; routers translate to HTTP.
- **SQL/migrations:** Alembic only. CI replays all migrations from an empty database on every PR. A merged migration is immutable — fixes are new migrations.
- **TypeScript:** strict tsconfig, ESLint + Prettier, `tsc --noEmit` in CI.
- **Testing:** pytest. Unit tests for services (royalty math, locking, versioning), integration tests against real Postgres (docker-compose in CI) for RLS and ledger invariants. Every invariant in §2.5 has a named test. Frontend: vitest for non-trivial logic + typecheck; don't gold-plate UI tests for the MVP.
- **Logging/errors:** structlog JSON, request_id middleware, no print(). Secrets never logged.
- **Config:** pydantic-settings from environment. `.env.example` committed; `.env` never.

## 4. Git & GitHub workflow

- **Trunk-based.** `main` is always deployable and protected: no direct pushes, PRs only, required CI checks, squash-merge only (linear history).
- **Branches:** short-lived, `feat/…`, `fix/…`, `chore/…`, deleted on merge. Rebase on main before merge; no long-lived branches, no merge commits.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`, `docs:`). Squash title becomes the changelog line — write it well.
- **PR policy:** PRs are substantial, coherent vertical slices — schema + service + tests + UI for one feature area belongs in one PR, and closely related features may ship together when they form one reviewable story. Guidance ceiling ~1,500 changed lines; above that, split by seam, not by file type. Every PR description: what/why, how it was tested, invariants touched, ADR links. A PR that changes behavior without tests does not merge.
- **CI on every PR (required checks):** ruff, mypy --strict, pytest (unit + integration with migrations-from-zero), tsc, web build, openapi-client freshness check. **CD:** merge to main deploys api (Cloud Run/Render) and web (Pages) automatically.
- **ADRs:** any decision that would take a paragraph to justify gets an ADR. Seed set: 0001 stack, 0002 RLS session-variable tenancy, 0003 append-only supply ledger, 0004 versioned idempotent royalty runs, 0005 GHL sync-not-replace, 0006 auth/JWT approach.

## 5. Documentation & context

`/docs` is the repository's context store. Before working on any area, check `/docs` for background relevant to what you're touching — phase notes, domain explanations, integration details, decisions already made. Keep it current as you work:

- **ADRs are mandatory for major decisions.** Anything that would take a paragraph to justify — a technology choice, a schema shape, a workflow, a rejected alternative — gets `/docs/adr/ADR-NNNN-title.md` (numbered, append-only; supersede, never delete). Seed set listed in §4.
- **Pertinent standing docs are mandatory too.** When work produces knowledge a future contributor (or a future Claude session) would need — runbooks, environment/deploy notes, data dictionaries, demo scripts, compliance notes — write it under `/docs` in the appropriate subfolder. If it only lives in a chat transcript, it doesn't exist.
- Docs are updated in the same PR as the change they describe; stale docs are treated as bugs.

## 6. Phases

Status labels: `planned | in-progress | merged`. Each phase ends with green CI, deployed main, and its exit criteria demonstrably true.

### Phase 0 — Scaffold & walking skeleton `merged`
Monorepo, tooling (uv, ruff, mypy, pytest, Vite, ESLint), docker-compose Postgres, CI pipeline, deployed hello-world round trip (web → api → db) behind the auth gate. **Exit:** a stranger can clone, `make dev`, and hit a live URL.

### Phase 1 — Schema, tenancy, auth, seed `merged`
Alembic migrations for §2.4, RLS policies + tenancy dependency, JWT auth with seeded users (hq_admin, operator_a, operator_b, clinic_staff), deterministic seed (~20 locations, synthetic funnel + treatments, one deliberate underreporter). **Exit:** invariant tests 1, 5 pass; seed reset is one command.

### Phase 2 — Royalty domain core `merged`
Services + endpoints: submit/attest revenue report (locks), run_royalty_period (idempotent, versioned), minimums, issue_invoices, aging query. **Exit:** invariants 2, 3, 4, 6 pass; full royalty cycle executable via API alone.

### Phase 3 — Web shell & royalty UI `merged`
Auth flow, role-based shells, generated client. Operator: submit/attest month, view statements/invoices. HQ: run period, line items, invoices, aging. **Exit:** the two-minute demo's first half runs entirely in the browser.

### Phase 4 — Dashboard, variance, traceability `merged`
HQ KPI dashboard vs ramp targets; variance reconciliation view flagging the seeded underreporter with the math shown; lot receive/ship/administer UI + one-click recall query. **Exit:** the showpiece moments render from seed with zero manual setup.

### Phase 5 — Integration proof & demo hardening `merged`
`/webhooks/ghl` (HMAC-verified) mapping contact/appointment payloads into funnel tables; CSV importer; README with ADR index; `make demo-reset`; rehearsed script. **Exit: MVP complete — demo-ready.**

---

### Post-MVP (build only on a real signal — an offer, or their explicit interest)

### Phase 6 — Collections `in-progress`
Stripe invoicing + payment-status webhooks so invoices become money movement; ACH as end state. **Exit:** an invoice can be paid in test mode and aging updates itself.

### Phase 7 — Licensee portal `in-progress`
60-day onboarding checklist, document vault, product reorder flow tied to the lots ledger. **Exit:** an operator can complete onboarding tasks and place a product order end-to-end.

### Phase 8 — Attribution `planned`
Ad-spend import (Google/Meta), CAC and ROAS per location joined into the KPI layer; two-way GHL sync where it earns its keep. **Exit:** cost-per-close per location on the HQ dashboard.

### Phase 9 — Real-data hardening `planned`
Audit log table on all mutations, Sentry, OpenTelemetry traces, rate limiting, backup/PITR verification, consent registry (TCPA/photo/HIPAA-authorization records). **Exit:** the checklist a real deployment would demand, written down and green. Nothing before this phase touches non-synthetic data.

## 7. Definition of done (every PR)
Green CI; invariants touched have tests; migrations replay from zero; no mypy/ruff suppressions added without an inline justification; docs/ADR updated if a §2 decision changed; deployed main still boots and serves the demo seed.

## 8. Never do
Edit a merged migration. Commit secrets or `.env`. Bypass or weaken RLS. Log tokens or connection strings. Introduce real patient/company data or third-party branding. Merge red CI. Create a second long-lived branch.
