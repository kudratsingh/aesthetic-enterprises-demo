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

## Auth (Phase 1, ADR-0006)

`POST /api/v1/auth/login` with email + password returns a JWT whose claims
(org, role) drive the RLS tenant context. For curl-level poking without a user
row: `make token ROLE=hq_admin ORG=<org-uuid>`, then
`curl -H "Authorization: Bearer <token>" 127.0.0.1:8100/api/v1/hello`.

## Seed world & demo logins

`make seed` (alias `make demo-reset`) rebuilds the deterministic synthetic world:
1 HQ + 15 operator orgs, 20 locations, 6 months of funnel/supply history, 120
locked revenue reports, and one designated underreporter
("Vista Glow Clinic — Chandler", ~40% below its supply-implied floor).
**Destructive**: truncates every table first. All data is fabricated.

| Login | Password | Role |
|---|---|---|
| `hq_admin@clinic-network-os.demo` | `demo-hq-2026!` | hq_admin |
| `operator-1@clinic-network-os.demo` … `operator-15@…` | `demo-operator-2026!` | operator |
| `staff-2@clinic-network-os.demo` | `demo-staff-2026!` | clinic_staff |

These are synthetic demo credentials, documented here on purpose.

## Database roles (ADR-0002)

Two local roles, created automatically on a fresh docker volume:

- `cnos` — superuser, **DDL only** (`make migrate` uses it via
  `MIGRATIONS_DATABASE_URL`). Superusers bypass RLS, so the app never connects as it.
- `cnos_app` — non-superuser the app and tests connect as; RLS applies.

**One-time note:** if your db volume predates Phase 1, run `make db-nuke` once —
the role-creation script only runs on a fresh volume.

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
- Migrations: `make migrate` (runs alembic as the admin role). CI replays all
  migrations from an empty database on every PR; merged migrations are immutable.

## Gotchas

- Host port is **5433**, not 5432 — `psql postgresql://cnos:cnos@localhost:5433/cnos`.
- If `make dev` fails at `db-up` with a port error, another service grabbed 5433;
  change the host port in `infra/docker-compose.yml` and `DATABASE_URL` together.
