# ADR-0001: Stack selection

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 0

## Context

`clinic-network-os` is a multi-tenant network OS for a clinic licensor (royalty
billing, KPI reporting, lot traceability), built as an interview demonstration on
production-shaped patterns. The stack must (a) let one developer move fast, (b) put
correctness guarantees in the database rather than application code, (c) deploy
cheaply with scale-to-zero, and (d) demonstrate patterns a reviewer recognizes as
production-grade.

## Decision

| Layer | Choice | Why |
|---|---|---|
| Database | Postgres (Neon serverless; postgres:16 via docker-compose locally) | RLS for tenancy, CHECK constraints for ledger invariants — correctness lives here. Neon gives branching + scale-to-zero. |
| API | FastAPI on Python 3.12, single container | Async, typed, OpenAPI for free (drives the generated web client). One container keeps deploys trivial (Cloud Run/Render). |
| DB access | SQLAlchemy 2.0 async + asyncpg; Alembic migrations | Typed core/ORM with async pooling; migrations replayable from zero in CI. |
| Python tooling | uv, ruff (lint+format), mypy --strict, pytest | Fast, modern, minimal config surface. |
| Web | Vite + React + TypeScript strict, TanStack Query | SPA is sufficient; no SSR need. Server state via Query, no global client state beyond auth. |
| API client | Generated from OpenAPI spec in CI (openapi-typescript) | Hand-written fetch types drift; the spec is the contract. CI freshness check enforces regeneration. |
| Auth | JWT with role claims (detailed in ADR-0006, Phase 1) | Role claims feed the RLS session variables. |
| Hosting | API: Cloud Run/Render. Web: Cloudflare Pages/Vercel. | Scale-to-zero, free tiers, push-to-deploy. |

## Consequences

- Monorepo (`/api`, `/web`, `/infra`, `/docs`) with one CI pipeline covering both sides.
- The OpenAPI spec becomes a hard contract: breaking it breaks the web build in CI, which is intended.
- Single-container API means no background-worker infrastructure; anything long-running
  (royalty runs) must be fast enough to run in-request for the demo scale (~20 locations).
- Postgres-first correctness means integration tests must run against real Postgres
  (docker-compose in CI), not SQLite.

## Alternatives considered

- **Next.js full-stack:** rejected — hides the API contract, and Python is the stronger
  signal for the domain-logic-heavy backend this demo showcases.
- **Django:** rejected — ORM-centric patterns fight RLS-session-variable tenancy;
  FastAPI's dependency injection maps cleanly onto per-request `SET LOCAL`.
- **SQLite for tests:** rejected — RLS and CHECK-based invariants are the product;
  they only exist on real Postgres.
