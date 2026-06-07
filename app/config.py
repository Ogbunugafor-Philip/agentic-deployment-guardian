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

    # Shared secret used to validate GitHub webhook signatures (HMAC-SHA256).
    # Written into .env by the deploy pipeline; never logged.
    github_webhook_secret: str = ""

    # GitHub Personal Access Token used to pull Actions job logs via the REST
    # API. Written into .env by the pipeline; never logged or stored in the DB.
    gh_pat: str = ""

    # Cerebras API key + model for AI root-cause analysis. Key written into .env
    # by the pipeline; never logged or stored in the DB.
    cerebras_api_key: str = ""
    cerebras_model: str = "gpt-oss-120b"

    # --- Phase 6: autonomous remediation ---
    # Master switch: when false, SERVICE_RESTART is dry-run (no SSH/restart).
    remediation_enabled: bool = True
    # Gate the production push for AUTO_ROLLBACK separately; dry-run when false.
    remediation_rollback_enabled: bool = False
    # Health endpoint polled to confirm recovery (app service over compose net).
    health_check_url: str = "http://app:8100/health"
    recovery_timeout_seconds: int = 300
    recovery_poll_interval: int = 10
    # SSH target for SERVICE_RESTART. Key is base64-encoded in .env to stay
    # single-line. None of these are ever logged.
    vps_host: str = ""
    vps_user: str = "guardian"
    vps_ssh_key_b64: str = ""
    project_dir: str = "/home/guardian/agentic-deployment-guardian"


@lru_cache
def get_settings() -> Settings:
    return Settings()
