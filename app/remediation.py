"""Shared remediation helpers: recovery health-poll and escalation."""

from __future__ import annotations

import json
import logging
import time

import requests

from app.config import get_settings

logger = logging.getLogger("guardian.remediation")


def poll_health(timeout: int | None = None, interval: int | None = None) -> bool:
    """Poll the health endpoint until it reports healthy or the timeout elapses.

    Used as the confirmation check after AUTO_ROLLBACK and SERVICE_RESTART.
    """
    settings = get_settings()
    timeout = timeout if timeout is not None else settings.recovery_timeout_seconds
    interval = interval if interval is not None else settings.recovery_poll_interval
    url = settings.health_check_url

    deadline = time.monotonic() + timeout
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and (resp.json() or {}).get("status") == "healthy":
                logger.info("Recovery confirmed: %s healthy after %d attempt(s)", url, attempt)
                return True
        except Exception:  # noqa: BLE001 - keep polling regardless of transient errors
            pass
        if time.monotonic() >= deadline:
            logger.warning("Recovery NOT confirmed within %ss (%s)", timeout, url)
            return False
        time.sleep(interval)


def _root_cause_explanation(root_cause: str | None) -> str:
    if not root_cause:
        return "No AI root-cause diagnosis was available."
    for line in root_cause.splitlines():
        if line.lower().startswith("why it failed:"):
            return line.split(":", 1)[1].strip()
    return root_cause.strip()


def run_escalation(incident: dict) -> tuple[str, str, str, str]:
    """Flag for human review. Returns (status, detail, reason, summary_json)."""
    reason = (
        f"Human review required. Failed step: {incident.get('failed_step') or 'unknown'}. "
        f"{_root_cause_explanation(incident.get('root_cause'))}"
    )

    summary = {
        "incident_id": incident.get("id"),
        "repository": f"{incident.get('repo_owner')}/{incident.get('repo_name')}",
        "branch": incident.get("branch"),
        "commit_sha": incident.get("commit_sha"),
        "job_id": incident.get("job_id"),
        "failed_step": incident.get("failed_step"),
        "exit_code": incident.get("exit_code"),
        "remediation_action": incident.get("remediation_action"),
        "root_cause": incident.get("root_cause"),
        "recommended_next_step": "Human engineer to review the root cause and apply a fix.",
        "html_url": incident.get("html_url"),
    }
    detail = "Incident flagged for human review (no automated action taken)."
    return "ESCALATED", detail, reason, json.dumps(summary, ensure_ascii=False)
