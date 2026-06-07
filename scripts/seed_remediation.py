"""Seed one synthetic, already-analyzed incident with a chosen remediation_action
and enqueue the remediation engine — for testing each path independently.

Run inside the worker container (it has the app code + DB + Redis), e.g.:

  docker exec -e ACTION=SERVICE_RESTART -i guardian-worker python3 - < scripts/seed_remediation.py
  docker exec -e ACTION=AUTO_ROLLBACK   -i guardian-worker python3 - < scripts/seed_remediation.py
  docker exec -e ACTION=HUMAN_ESCALATION -i guardian-worker python3 - < scripts/seed_remediation.py

Then inspect: curl http://localhost:8101/incidents/<printed id>
"""

import os
from datetime import datetime, timezone

from app.models import insert_incident, update_incident_logs
from app.tasks import remediate_incident

ACTION = os.environ.get("ACTION", "HUMAN_ESCALATION")

event = {
    "job_id": "79966117358",  # a real failed job in this repo (for realism)
    "workflow": "Deploy Agentic Deployment Guardian",
    "repo_owner": "Ogbunugafor-Philip",
    "repo_name": "agentic-deployment-guardian",
    "commit_sha": "0ffa588",
    "branch": "main",
    "conclusion": "failure",
    "html_url": "https://github.com/Ogbunugafor-Philip/agentic-deployment-guardian",
    "event_timestamp": None,
}

incident_id = insert_incident(event, {"seed": "remediation-test", "forced_action": ACTION})
update_incident_logs(
    incident_id,
    log_status="retrieved",
    parsed_summary="Seeded test summary for remediation path verification.",
    failed_step="Run tests",
    exit_code=1,
    ai_status="analyzed",
    root_cause=(
        "Failure point: Run tests\n"
        "Why it failed: Seeded incident for testing the remediation engine.\n"
        "Suggested fix: n/a (test seed)."
    ),
    remediation_action=ACTION,
    analyzed_at=datetime.now(timezone.utc),
)

remediate_incident.delay(incident_id)
print(f"seeded incident {incident_id} with remediation_action={ACTION}; remediation enqueued")
