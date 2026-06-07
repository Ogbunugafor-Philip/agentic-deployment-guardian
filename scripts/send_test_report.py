"""Seed a realistic incident and email its report immediately — for verifying
Phase 7 delivery. Run inside the worker container:

  docker exec -i guardian-worker python3 - < scripts/send_test_report.py
  docker exec -e STATUS=ESCALATED -e REMEDIATION=HUMAN_ESCALATION -i guardian-worker python3 - < scripts/send_test_report.py

Prints the subject line and text body of the email that was sent.
"""

import os
from datetime import datetime, timezone

from app.email_sender import send_email
from app.models import get_incident_report, insert_incident, update_incident_logs
from app.report import build_html, build_subject, build_text

status = os.environ.get("STATUS", "RECOVERED")
action = os.environ.get("REMEDIATION", "SERVICE_RESTART")

event = {
    "job_id": "79966117358",
    "workflow": "Deploy Agentic Deployment Guardian",
    "repo_owner": "Ogbunugafor-Philip",
    "repo_name": "agentic-deployment-guardian",
    "commit_sha": "0ffa588abc1234",
    "branch": "main",
    "conclusion": "failure",
    "html_url": "https://github.com/Ogbunugafor-Philip/agentic-deployment-guardian",
    "event_timestamp": None,
}

incident_id = insert_incident(event, {"seed": "report-test"})
update_incident_logs(
    incident_id,
    failed_step="Run tests",
    exit_code=1,
    log_status="retrieved",
    ai_status="analyzed",
    root_cause=(
        "Failure point: Run tests\n"
        "Why it failed: A unit test failed because the code produced 5 where 4 was "
        "expected, so the deployment was stopped to protect the live service.\n"
        "Suggested fix: Correct the addition logic in the widget module and re-run the tests."
    ),
    remediation_action=action,
    remediation_status=status,
    remediation_detail="Restarted the app service.",
    escalation_reason=(
        "A unit test is failing, which needs a developer to correct the code."
        if status == "ESCALATED"
        else None
    ),
    remediated_at=datetime.now(timezone.utc),
)

incident = get_incident_report(incident_id)
subject = build_subject(incident)
send_email(subject, build_html(incident), build_text(incident))
update_incident_logs(incident_id, report_sent=True, report_sent_at=datetime.now(timezone.utc))

print(f"SENT incident #{incident_id}")
print(f"SUBJECT: {subject}")
print("----- TEXT BODY -----")
print(build_text(incident))
