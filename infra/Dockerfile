# clinic-network-os API container (build context: repo root)
#   docker build -f infra/Dockerfile -t cnos-api .
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /srv/api
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev

COPY api/app ./app
COPY api/migrations ./migrations
COPY api/alembic.ini ./

ENV PATH="/srv/api/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8080
# Shell form: Render injects PORT; migrations replay is idempotent (alembic upgrade head).
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
