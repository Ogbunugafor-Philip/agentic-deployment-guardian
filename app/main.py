"""FastAPI entrypoint for the Agentic Deployment Guardian."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.celery_app import celery
from app.config import get_settings
from app.db import check_database, check_redis
from app.github_webhook import parse_event, verify_signature
from app.models import (
    create_tables,
    get_incident_detail,
    insert_incident,
    recent_incidents,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("guardian")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    if not settings.github_webhook_secret:
        logger.warning(
            "GITHUB_WEBHOOK_SECRET is empty — webhook requests will be rejected"
        )
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Autonomously detects, diagnoses, and resolves GitHub Actions "
        "pipeline failures."
    ),
    lifespan=lifespan,
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


def _persist_incident(event: dict, payload: dict) -> None:
    """Background task: write the incident to PostgreSQL and the app log, then
    enqueue automatic log retrieval for failure events."""
    try:
        incident_id = insert_incident(event, payload)
        logger.info(
            "Incident #%s recorded: repo=%s/%s branch=%s sha=%s conclusion=%s job_id=%s",
            incident_id,
            event.get("repo_owner"),
            event.get("repo_name"),
            event.get("branch"),
            (event.get("commit_sha") or "")[:8],
            event.get("conclusion"),
            event.get("job_id"),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to persist incident to PostgreSQL")
        return

    if (event.get("conclusion") or "").lower() == "failure":
        try:
            celery.send_task("process_incident_logs", args=[incident_id])
            logger.info("Enqueued log retrieval for incident #%s", incident_id)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to enqueue log retrieval for incident #%s", incident_id)


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> JSONResponse:
    """Receive a GitHub failure webhook, validate it, and record it.

    Returns 200 as soon as the signature is verified; the database write and
    detailed logging happen in a background task so GitHub never times out.
    """
    raw_body = await request.body()

    if not verify_signature(
        raw_body, settings.github_webhook_secret, x_hub_signature_256
    ):
        logger.warning(
            "Rejected webhook (event=%s): missing or invalid signature", x_github_event
        )
        return JSONResponse(status_code=401, content={"detail": "invalid signature"})

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("Rejected webhook (event=%s): body is not valid JSON", x_github_event)
        return JSONResponse(status_code=400, content={"detail": "invalid JSON body"})

    event = parse_event(payload)
    logger.info(
        "Webhook accepted: event=%s repo=%s/%s branch=%s sha=%s conclusion=%s job_id=%s",
        x_github_event,
        event.get("repo_owner"),
        event.get("repo_name"),
        event.get("branch"),
        (event.get("commit_sha") or "")[:8],
        event.get("conclusion"),
        event.get("job_id"),
    )

    background_tasks.add_task(_persist_incident, event, payload)
    return JSONResponse(status_code=200, content={"status": "accepted"})


@app.get("/incidents")
def list_incidents(limit: int = 20) -> JSONResponse:
    """Return the most recently recorded incidents (for verification)."""
    limit = max(1, min(limit, 100))
    rows = recent_incidents(limit)
    return JSONResponse(content={"count": len(rows), "incidents": rows})


@app.get("/incidents/{incident_id}")
def incident_detail(incident_id: int) -> JSONResponse:
    """Return one incident incl. parsed summary, failed step, and a log excerpt."""
    detail = get_incident_detail(incident_id)
    if detail is None:
        return JSONResponse(status_code=404, content={"detail": "incident not found"})
    return JSONResponse(content=detail)
