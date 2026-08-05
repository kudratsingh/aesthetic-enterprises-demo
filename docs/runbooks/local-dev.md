# Runbook: local development

## Start everything

```sh
make dev
```

Brings up Postgres via docker-compose (host port **5433**, chosen to avoid colliding
with other local Postgres instances), the API with reload on :8100 (8000 is a popular
port for other local stacks), and Vite on :5173. The web dev server proxies `/api/*`
to 127.0.0.1:8100 (see `web/vite.config.ts`), so there is no CORS in local dev.

## Configuration

Settings load from environment / `api/.env` (`app/core/config.py`); defaults work
out of the box. Template: `.env.example` at the repo root. Never commit `.env`.

## Auth in Phase 0

Real auth lands in Phase 1 (ADR-0006). Until then, `POST /api/v1/auth/dev-token`
mints a signed JWT for any role — it is disabled when `ENVIRONMENT=prod`. From the
CLI: `make token ROLE=hq_admin ORG=org-hq`, then
`curl -H "Authorization: Bearer <token>" 127.0.0.1:8100/api/v1/hello`.

## Tests, lint, client generation

```sh
make test       # api unit + integration (needs Docker for Postgres) + web typecheck
make lint       # ruff format --check, ruff check, mypy --strict, eslint, prettier
make openapi    # after changing any endpoint/schema: regenerate web/src/api/schema.ts
```

`make openapi` output must be committed — CI fails if the generated client is stale
(openapi-client-freshness job).

## Database

- Reset: `make db-nuke && make db-up` (all local data is disposable synthetic seed).
- Migrations: `cd api && uv run alembic upgrade head`. CI replays all migrations from
  an empty database on every PR; merged migrations are immutable.

## Gotchas

- Host port is **5433**, not 5432 — `psql postgresql://cnos:cnos@localhost:5433/cnos`.
- If `make dev` fails at `db-up` with a port error, another service grabbed 5433;
  change the host port in `infra/docker-compose.yml` and `DATABASE_URL` together.
