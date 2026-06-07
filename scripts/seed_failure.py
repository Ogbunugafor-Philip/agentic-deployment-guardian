"""Seed a parsed incident and run it through the REAL chain from AI analysis
onward (Cerebras -> decision -> remediation -> email -> history/patterns).

Used to exercise different failure *types* end-to-end. Env: STEP, SUMMARY, EXIT.
"""

import os
from app.models import insert_incident, update_incident_logs
from app.tasks import analyze_incident

step = os.environ.get("STEP", "Run tests")
summary = os.environ.get("SUMMARY", "tests failed")
exit_code = int(os.environ.get("EXIT", "1"))

event = {
    "job_id": "seed-" + step.lower().replace(" ", "-"),
    "workflow": "Deploy Agentic Deployment Guardian",
    "repo_owner": "Ogbunugafor-Philip",
    "repo_name": "agentic-deployment-guardian",
    "commit_sha": "seedsha123",
    "branch": "main",
    "conclusion": "failure",
    "html_url": "https://github.com/Ogbunugafor-Philip/agentic-deployment-guardian",
    "event_timestamp": None,
}
iid = insert_incident(event, {"seed": "failure-type"})
update_incident_logs(iid, log_status="retrieved", parsed_summary=summary, failed_step=step, exit_code=exit_code)
analyze_incident.delay(iid)
print(iid)
