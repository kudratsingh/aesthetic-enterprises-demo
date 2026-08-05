from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"
    # Matches infra/docker-compose.yml (host port 5433 to avoid local Postgres collisions).
    database_url: str = "postgresql+asyncpg://cnos:cnos@localhost:5433/cnos"
    jwt_secret: str = "dev-only-secret-change-me-not-for-production"
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 3600
    cors_origins: list[str] = ["http://localhost:5173"]
    # Period boundaries are computed in this zone (no DST); storage is UTC. See PROJECT_CONTEXT §3.
    network_timezone: str = "America/Phoenix"


@lru_cache
def get_settings() -> Settings:
    return Settings()
