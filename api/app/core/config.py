from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"
    # App connections use the non-superuser role so RLS applies (ADR-0002); the
    # admin/owner URL is only for DDL. Ports match infra/docker-compose.yml.
    database_url: str = "postgresql+asyncpg://cnos_app:cnos_app@localhost:5433/cnos"
    # None → migrations run over database_url (Neon: one owner role does both).
    # Locally the Makefile exports the cnos admin URL for migrate/test targets.
    migrations_database_url: str | None = None
    jwt_secret: str = "dev-only-secret-change-me-not-for-production"
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 3600
    # HMAC shared secret for /webhooks/ghl (ADR-0005). None → endpoint answers 503.
    ghl_webhook_secret: str | None = None
    cors_origins: list[str] = ["http://localhost:5173"]
    # Period boundaries are computed in this zone (no DST); storage is UTC. See PROJECT_CONTEXT §3.
    network_timezone: str = "America/Phoenix"
    # R5: flag when reported net_base < expected_floor * threshold (assumption A2).
    variance_threshold: float = 0.75


@lru_cache
def get_settings() -> Settings:
    return Settings()
