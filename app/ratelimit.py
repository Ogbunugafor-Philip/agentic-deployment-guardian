"""Lightweight fixed-window rate limiter backed by the project's Redis.

Used to protect the webhook endpoint from abuse. Fails open if Redis is briefly
unavailable (availability over strictness for an internal guardian).
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.db import redis_client

logger = logging.getLogger("guardian.ratelimit")


def check_rate_limit(identifier: str) -> bool:
    """Return True if the caller is within the limit, False if it should be blocked."""
    settings = get_settings()
    limit = settings.webhook_rate_limit
    window = settings.webhook_rate_window
    key = f"ratelimit:webhook:{identifier}"
    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, window)
        return count <= limit
    except Exception:  # noqa: BLE001 - never let the limiter take down the endpoint
        logger.warning("Rate limiter unavailable; allowing request")
        return True


def client_identifier(request) -> str:
    """Best-effort client IP, honouring the X-Forwarded-For set by nginx."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
