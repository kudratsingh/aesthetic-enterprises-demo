COMPOSE = docker compose -f infra/docker-compose.yml
# Admin/owner URL for DDL (migrations); the app itself connects as cnos_app so
# RLS applies (ADR-0002).
ADMIN_DB_URL = postgresql+asyncpg://cnos:cnos@localhost:5433/cnos

.PHONY: dev dev-api dev-web db-up db-down db-nuke migrate test test-api test-web lint openapi token

## dev: start Postgres (migrated), API (:8100), and web (:5173) together
dev: db-up migrate
	$(MAKE) -j2 dev-api dev-web

dev-api:
	cd api && uv run uvicorn app.main:app --reload --port 8100

dev-web:
	cd web && npm run dev

db-up:
	$(COMPOSE) up -d --wait db

db-down:
	$(COMPOSE) down

## db-nuke: destroy the local database volume (asks nothing — data is disposable seed)
db-nuke:
	$(COMPOSE) down -v

migrate: db-up
	cd api && MIGRATIONS_DATABASE_URL=$(ADMIN_DB_URL) uv run alembic upgrade head

test: test-api test-web

test-api: db-up migrate
	cd api && uv run pytest

test-web:
	cd web && npm run typecheck

lint:
	cd api && uv run ruff format --check . && uv run ruff check . && uv run mypy
	cd web && npm run lint && npm run format:check

## openapi: re-export the spec and regenerate the typed web client (commit the result)
openapi:
	cd api && uv run python -m scripts.export_openapi
	cd web && npm run generate:api

## token: mint a dev JWT — make token ROLE=operator ORG=org-a
token:
	cd api && uv run python -m scripts.mint_dev_token $(ROLE) $(ORG)
