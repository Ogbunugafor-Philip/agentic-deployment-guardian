"""Background tasks: pull, parse, and store failure logs for an incident."""

from __future__ import annotations

import gzip
import logging
from datetime import datetime, timezone

from celery.signals import worker_ready

from app.ai_agent import analyze_failure
from app.celery_app import celery
from app.decision import classify_remediation
from app.github_api import LogsNotFound, fetch_job_logs
from app.log_parser import parse_logs
from app.models import (
    create_tables,
    get_incident_basic,
    get_incident_for_analysis,
    update_incident_logs,
)

logger = logging.getLogger("guardian.tasks")


@worker_ready.connect
def _ensure_schema_on_start(**_kwargs) -> None:
    try:
        create_tables()
    except Exception:  # noqa: BLE001
        logger.exception("Schema ensure failed on worker startup")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@celery.task(
    name="process_incident_logs",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def process_incident_logs(self, incident_id: int) -> str:
    """Fetch the failed job's logs from GitHub, parse them, and store the result."""
    incident = get_incident_basic(incident_id)
    if not incident:
        logger.warning("Incident #%s not found; nothing to process", incident_id)
        return "not_found"

    job_id = (incident.get("job_id") or "").strip()
    owner = incident.get("repo_owner")
    repo = incident.get("repo_name")

    if not (job_id and owner and repo):
        update_incident_logs(
            incident_id,
            log_status="skipped: missing job_id/repo",
            log_retrieved_at=_now(),
        )
        logger.warning("Incident #%s missing job_id/owner/repo; skipping log pull", incident_id)
        return "skipped"

    try:
        raw = fetch_job_logs(owner, repo, job_id)
    except LogsNotFound:
        update_incident_logs(incident_id, log_status="no_logs", log_retrieved_at=_now())
        logger.warning("No logs available for incident #%s (job_id=%s)", incident_id, job_id)
        return "no_logs"
    except Exception as exc:  # network/5xx/etc. — retry, then record the failure
        logger.warning("Log fetch failed for incident #%s: %s", incident_id, exc.__class__.__name__)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            update_incident_logs(
                incident_id,
                log_status=f"error: {exc.__class__.__name__}",
                log_retrieved_at=_now(),
            )
            return "error"

    parsed = parse_logs(raw)
    raw_gz = gzip.compress(raw.encode("utf-8", "replace"))

    update_incident_logs(
        incident_id,
        raw_log=raw_gz,
        parsed_summary=parsed["summary"],
        failed_step=parsed["failed_step"],
        exit_code=parsed["exit_code"],
        log_status="retrieved",
        log_retrieved_at=_now(),
    )
    logger.info(
        "Stored logs for incident #%s: step=%r exit=%s raw=%dB gz=%dB",
        incident_id,
        parsed["failed_step"],
        parsed["exit_code"],
        len(raw),
        len(raw_gz),
    )

    # Phase 5: chain AI root-cause analysis automatically once parsing is done.
    analyze_incident.delay(incident_id)
    logger.info("Enqueued AI analysis for incident #%s", incident_id)
    return "retrieved"


@celery.task(
    name="analyze_incident",
    bind=True,
    max_retries=2,
    default_retry_delay=20,
)
def analyze_incident(self, incident_id: int) -> str:
    """Ask Cerebras for a plain-English root cause, then classify remediation."""
    incident = get_incident_for_analysis(incident_id)
    if not incident:
        logger.warning("Incident #%s not found for analysis", incident_id)
        return "not_found"

    failed_step = incident.get("failed_step")
    parsed_summary = incident.get("parsed_summary")
    exit_code = incident.get("exit_code")

    try:
        result = analyze_failure(failed_step, parsed_summary, exit_code)
    except Exception as exc:  # transport/API errors — retry, then record failure
        logger.warning("AI analysis failed for incident #%s: %s", incident_id, exc.__class__.__name__)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            update_incident_logs(
                incident_id,
                ai_status=f"error: {exc.__class__.__name__}",
                analyzed_at=_now(),
            )
            return "error"

    action, reason = classify_remediation(
        failed_step,
        result["root_cause"],
        parsed_summary,
        exit_code,
        result.get("severity_hint"),
    )

    update_incident_logs(
        incident_id,
        root_cause=result["root_cause"],
        remediation_action=action,
        ai_status="analyzed",
        analyzed_at=_now(),
    )
    logger.info(
        "AI analysis for incident #%s: remediation=%s (%s)",
        incident_id,
        action,
        reason,
    )
    return "analyzed"
