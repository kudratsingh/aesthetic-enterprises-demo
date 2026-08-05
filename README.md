# clinic-network-os

Multi-tenant network operating system for a clinic licensor: royalty billing on
licensee revenue, network KPI reporting, product lot traceability, and
licensee-facing statements. **All data is synthetic** — see `CLAUDE.md` and
`docs/PROJECT_CONTEXT.md` for the full operating rules and domain context.

## Live demo

- Web: https://aesthetic-enterprises-demo.singhkudrat59.workers.dev
- API: https://cnos-api.onrender.com/api/v1/health

Sign in as HQ (`hq_admin@clinic-network-os.demo` / `demo-hq-2026!`) or an
operator (`operator-1@clinic-network-os.demo` / `demo-operator-2026!`) —
synthetic demo credentials, documented on purpose. The two-minute walkthrough
is scripted in `docs/runbooks/demo-script.md`. Free-tier note: the API sleeps
when idle — the first request after a quiet spell takes ~30s to wake it.

## Quickstart

Prereqs: Docker, [uv](https://docs.astral.sh/uv/), Node 22+.

```sh
make dev        # Postgres (:5433) + API (:8100) + web (:5173)
make seed       # deterministic demo world (in a second terminal, first run only)
```

Open http://localhost:5173 and sign in with the demo credentials above.

## Common commands

| Command | What it does |
|---|---|
| `make dev` | Run the full local stack |
| `make demo-reset` | Rebuild the deterministic demo world (alias: `make seed`) |
| `make test` | API tests (unit + integration vs real Postgres) + web typecheck |
| `make lint` | ruff, mypy --strict, ESLint, Prettier |
| `make openapi` | Regenerate the typed web API client from the FastAPI spec |
| `make token ROLE=operator ORG=org-a` | Mint a dev JWT for curl-level API poking |
| `make db-nuke` | Destroy the local database volume |

## Layout

```
/api      FastAPI + SQLAlchemy async + Alembic (routers → services → db)
/web      Vite + React + TS strict; API client generated from OpenAPI
/infra    Dockerfile, docker-compose (local Postgres)
/docs     Context store: PROJECT_CONTEXT.md, ADRs, runbooks
```

## Docs

- `docs/PROJECT_CONTEXT.md` — domain semantics, business rules, rationale
- `docs/adr/` — architecture decision records (index below)
- `docs/runbooks/` — local dev, deploy, integrations, demo script
- `CLAUDE.md` — engineering standards, workflow, phase plan

## ADR index

| ADR | Decision |
|---|---|
| [ADR-0001](docs/adr/ADR-0001-stack.md) | Stack selection |
| [ADR-0002](docs/adr/ADR-0002-rls-session-variable-tenancy.md) | RLS session-variable tenancy |
| [ADR-0003](docs/adr/ADR-0003-append-only-supply-ledger.md) | Append-only supply ledger |
| [ADR-0004](docs/adr/ADR-0004-versioned-idempotent-royalty-runs.md) | Versioned, idempotent royalty runs |
| [ADR-0005](docs/adr/ADR-0005-ghl-sync-not-replace.md) | GHL sync-not-replace funnel ingestion |
| [ADR-0006](docs/adr/ADR-0006-auth-jwt.md) | Auth — bcrypt credentials, HS256 JWT, claims drive RLS |
| [ADR-0007](docs/adr/ADR-0007-hosting-providers.md) | Hosting providers — Render, Cloudflare Pages, Neon |
| [ADR-0008](docs/adr/ADR-0008-kpi-ramp-targets-and-variance-lifecycle.md) | KPI ramp targets as formula; variance flag lifecycle |
