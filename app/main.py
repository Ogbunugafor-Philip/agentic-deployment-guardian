"""FastAPI entrypoint for the Agentic Deployment Guardian."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.db import check_database, check_redis

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Autonomously detects, diagnoses, and resolves GitHub Actions "
        "pipeline failures."
    ),
)


@app.get("/")
def root() -> dict:
    return {
        "service": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
        "status": "running",
    }


@app.get("/health")
def health() -> JSONResponse:
    """Liveness + dependency readiness probe used by Docker and the pipeline."""
    checks: dict[str, str] = {}

    try:
        check_database()
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report any failure verbatim
        checks["postgres"] = f"error: {exc.__class__.__name__}"

    try:
        check_redis()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc.__class__.__name__}"

    healthy = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "healthy" if healthy else "degraded", "checks": checks},
    )
