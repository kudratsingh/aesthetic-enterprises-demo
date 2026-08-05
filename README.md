# clinic-network-os

Multi-tenant network operating system for a clinic licensor: royalty billing on
licensee revenue, network KPI reporting, product lot traceability, and
licensee-facing statements. **All data is synthetic** — see `CLAUDE.md` and
`docs/PROJECT_CONTEXT.md` for the full operating rules and domain context.

## Live demo

- Web: https://aesthetic-enterprises-demo.singhkudrat59.workers.dev
- API: https://cnos-api.onrender.com/api/v1/health

Free-tier note: the API sleeps when idle — the first request after a quiet spell
takes ~30s to wake it.

## Quickstart

Prereqs: Docker, [uv](https://docs.astral.sh/uv/), Node 22+.

```sh
make dev        # Postgres (:5433) + API (:8100) + web (:5173)
```

Open http://localhost:5173 — sign in with the dev token button and you should see
the web → api → db round trip complete.

## Common commands

| Command | What it does |
|---|---|
| `make dev` | Run the full local stack |
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
- `docs/adr/` — architecture decision records
- `CLAUDE.md` — engineering standards, workflow, phase plan
