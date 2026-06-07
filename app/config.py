"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Agentic Deployment Guardian"
    environment: str = "production"

    # Service URLs. Inside Docker Compose these resolve to the service names
    # (db, redis) over the internal network, not the host port mappings.
    database_url: str = "postgresql+psycopg2://guardian:guardian@db:5432/guardian"
    redis_url: str = "redis://redis:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
