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
from app.email_sender import send_email
from app.models import (
    create_tables,
    get_incident_basic,
    get_incident_for_analysis,
    get_incident_for_remediation,
    get_incident_report,
    update_incident_logs,
)
from app.remediation import run_escalation
from app.report import build_html, build_subject, build_text
from app.restart import run_restart
from app.rollback import run_rollback

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

    # Phase 6: chain the autonomous remediation engine automatically.
    remediate_incident.delay(incident_id)
    logger.info("Enqueued remediation for incident #%s (action=%s)", incident_id, action)
    return "analyzed"


@celery.task(name="remediate_incident", bind=True, max_retries=0)
def remediate_incident(self, incident_id: int) -> str:
    """Dispatch the remediation action and record recovery status."""
    incident = get_incident_for_remediation(incident_id)
    if not incident:
        logger.warning("Incident #%s not found for remediation", incident_id)
        return "not_found"

    action = incident.get("remediation_action")
    fields: dict = {}

    try:
        if action == "AUTO_ROLLBACK":
            status, detail = run_rollback(incident)
        elif action == "SERVICE_RESTART":
            status, detail = run_restart(incident)
        else:  # HUMAN_ESCALATION or anything unexpected -> escalate to a human
            status, detail, reason, summary = run_escalation(incident)
            fields["escalation_reason"] = reason
            fields["escalation_summary"] = summary
    except Exception as exc:  # noqa: BLE001 - never let remediation crash silently
        logger.exception("Remediation crashed for incident #%s", incident_id)
        status, detail = "FAILED_RECOVERY", f"Remediation error: {exc.__class__.__name__}"

    update_incident_logs(
        incident_id,
        remediation_status=status,
        remediation_detail=detail,
        remediated_at=_now(),
        **fields,
    )
    logger.info(
        "Remediation for incident #%s: action=%s status=%s", incident_id, action, status
    )

    # Phase 7: email the incident report automatically once remediation is done.
    send_incident_report.delay(incident_id)
    logger.info("Enqueued incident report email for incident #%s", incident_id)
    return status


@celery.task(
    name="send_incident_report",
    bind=True,
    max_retries=3,
    default_retry_delay=20,
)
def send_incident_report(self, incident_id: int) -> str:
    """Compile the report and email it via Gmail. Failures are logged, not fatal."""
    incident = get_incident_report(incident_id)
    if not incident:
        logger.warning("Incident #%s not found for reporting", incident_id)
        return "not_found"

    subject = build_subject(incident)
    try:
        send_email(subject, build_html(incident), build_text(incident))
    except Exception as exc:  # noqa: BLE001 - never crash the pipeline on email failure
        # str(exc) is the SMTP server response, which does not contain the password.
        logger.warning(
            "Incident report email FAILED for #%s (%s: %s)",
            incident_id,
            exc.__class__.__name__,
            exc,
        )
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Giving up emailing incident report for #%s after retries", incident_id)
            return "email_error"

    update_incident_logs(incident_id, report_sent=True, report_sent_at=_now())
    logger.info("Incident report emailed for #%s: %s", incident_id, subject)
    return "sent"
