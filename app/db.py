"""Database and cache client factories with lightweight connectivity checks."""

from __future__ import annotations

import redis
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import get_settings

_settings = get_settings()

# pool_pre_ping recycles dead connections transparently; the guardian app is
# long-lived so this avoids stale-connection errors after DB restarts.
engine: Engine = create_engine(_settings.database_url, pool_pre_ping=True)

redis_client: redis.Redis = redis.Redis.from_url(
    _settings.redis_url, socket_connect_timeout=2, socket_timeout=2
)


def check_database() -> bool:
    """Return True if a trivial query against PostgreSQL succeeds."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True


def check_redis() -> bool:
    """Return True if Redis responds to PING."""
    return bool(redis_client.ping())
