"""Build the incident report email (subject + HTML + plain-text).

Plain English only — no JSON, logs, stack traces, or technical dumps in the body.
Color coding: green = recovered, orange = escalated, red = failed/everything else.
"""

from __future__ import annotations

from datetime import datetime

_STATUS_COLOR = {
    "RECOVERED": "#1e7e34",       # green
    "ESCALATED": "#d97706",       # orange
    "FAILED_RECOVERY": "#c0392b",  # red
}
_STATUS_LABEL = {
    "RECOVERED": "Recovered",
    "ESCALATED": "Escalated to a human",
    "FAILED_RECOVERY": "Recovery failed",
}
_ACTION_TEXT = {
    "AUTO_ROLLBACK": "rolled the project back to the last working version",
    "SERVICE_RESTART": "restarted the affected service",
    "HUMAN_ESCALATION": "escalated the issue for a human engineer to review",
}


def _color(status: str | None) -> str:
    return _STATUS_COLOR.get(status or "", "#c0392b")


def _rc_part(root_cause: str | None, label: str) -> str:
    for line in (root_cause or "").splitlines():
        if line.lower().startswith(label.lower()):
            return line.split(":", 1)[1].strip()
    return ""


def _format_duration(start: datetime | None, end: datetime | None) -> str:
    if not start or not end:
        return "not available"
    seconds = int((end - start).total_seconds())
    if seconds < 0:
        return "not available"
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} {secs} second{'s' if secs != 1 else ''}"
    hours, mins = divmod(minutes, 60)
    return f"{hours} hour{'s' if hours != 1 else ''} {mins} minute{'s' if mins != 1 else ''}"


def build_subject(incident: dict) -> str:
    return (
        f"[Guardian] Incident #{incident.get('id')} — "
        f"{incident.get('failed_step') or 'unknown step'} — "
        f"{incident.get('remediation_status') or 'UNKNOWN'}"
    )


def _sections(incident: dict) -> dict:
    repo = f"{incident.get('repo_owner')}/{incident.get('repo_name')}"
    branch = incident.get("branch") or "unknown"
    sha = (incident.get("commit_sha") or "")[:8] or "unknown"
    step = incident.get("failed_step") or "an automated step"
    action = incident.get("remediation_action")
    status = incident.get("remediation_status")
    why = _rc_part(incident.get("root_cause"), "Why it failed:") or (
        "The automated check did not complete successfully."
    )
    fix = _rc_part(incident.get("root_cause"), "Suggested fix:")
    duration = _format_duration(incident.get("received_at"), incident.get("remediated_at"))

    detected = incident.get("received_at")
    when = detected.strftime("%B %d, %Y at %H:%M UTC") if detected else "recently"

    what_happened = (
        f"On {when}, an automated deployment check for the {repo} project failed "
        f"while running the step “{step}”. The Guardian detected the problem "
        f"automatically and started working on it right away."
    )

    where = {"repository": repo, "branch": branch, "commit": sha}

    did = _ACTION_TEXT.get(action, "reviewed the incident")
    what_done = f"The Guardian automatically {did}."
    if status == "RECOVERED":
        what_done += " The service has fully recovered and is healthy again."
    elif status == "ESCALATED":
        what_done += " No automated change was made, because this needs a person to decide the fix."
    elif status == "FAILED_RECOVERY":
        what_done += " Unfortunately the automated recovery did not restore the service."
    what_done += f" Time from detection to resolution: {duration}."

    if status == "RECOVERED":
        next_steps = "No action is required — everything is healthy again."
        if fix:
            next_steps += f" To prevent this in future, consider: {fix}"
    elif status == "ESCALATED":
        next_steps = "A human engineer needs to review and resolve this. "
        next_steps += incident.get("escalation_reason") or fix or "Please review the failure."
    elif status == "FAILED_RECOVERY":
        next_steps = (
            "Automated recovery did not work, so please investigate and fix this manually."
        )
        if fix:
            next_steps += f" A good starting point: {fix}"
    else:
        next_steps = "Please review this incident."

    return {
        "what_happened": what_happened,
        "where": where,
        "why": why,
        "what_done": what_done,
        "next_steps": next_steps,
    }


def build_text(incident: dict) -> str:
    s = _sections(incident)
    w = s["where"]
    return (
        f"Guardian Incident #{incident.get('id')} — {incident.get('remediation_status')}\n\n"
        f"WHAT HAPPENED\n{s['what_happened']}\n\n"
        f"WHERE IT HAPPENED\nRepository: {w['repository']}\nBranch: {w['branch']}\nCommit: {w['commit']}\n\n"
        f"WHY IT FAILED\n{s['why']}\n\n"
        f"WHAT WAS DONE\n{s['what_done']}\n\n"
        f"NEXT STEPS\n{s['next_steps']}\n"
    )


def build_html(incident: dict) -> str:
    s = _sections(incident)
    w = s["where"]
    status = incident.get("remediation_status") or "UNKNOWN"
    color = _color(status)
    status_label = _STATUS_LABEL.get(status, status)
    incident_id = incident.get("id")

    def section(title: str, body_html: str) -> str:
        return (
            f'<tr><td style="padding:18px 24px 0 24px;">'
            f'<p style="margin:0 0 6px 0;font-size:13px;font-weight:700;letter-spacing:.04em;'
            f'text-transform:uppercase;color:#6b7280;">{title}</p>'
            f'<div style="margin:0;font-size:15px;line-height:1.55;color:#1f2937;">{body_html}</div>'
            f"</td></tr>"
        )

    where_html = (
        f'<table cellpadding="0" cellspacing="0" style="font-size:15px;color:#1f2937;">'
        f'<tr><td style="padding:2px 16px 2px 0;color:#6b7280;">Repository</td><td style="padding:2px 0;font-weight:600;">{w["repository"]}</td></tr>'
        f'<tr><td style="padding:2px 16px 2px 0;color:#6b7280;">Branch</td><td style="padding:2px 0;font-weight:600;">{w["branch"]}</td></tr>'
        f'<tr><td style="padding:2px 16px 2px 0;color:#6b7280;">Commit</td><td style="padding:2px 0;font-weight:600;">{w["commit"]}</td></tr>'
        f"</table>"
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#f3f4f6;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f3f4f6;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#ffffff;border-radius:10px;overflow:hidden;border:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;">
        <tr><td style="background-color:{color};padding:20px 24px;">
          <p style="margin:0;color:#ffffff;font-size:18px;font-weight:700;">Agentic Deployment Guardian</p>
          <p style="margin:4px 0 0 0;color:#ffffff;font-size:14px;opacity:.92;">Incident #{incident_id} &middot; {status_label}</p>
        </td></tr>
        {section("What Happened", s["what_happened"])}
        {section("Where It Happened", where_html)}
        {section("Why It Failed", s["why"])}
        {section("What Was Done", s["what_done"])}
        {section("Next Steps", s["next_steps"])}
        <tr><td style="padding:22px 24px 24px 24px;">
          <p style="margin:0;font-size:12px;color:#9ca3af;border-top:1px solid #e5e7eb;padding-top:14px;">
            This report was generated automatically by the Agentic Deployment Guardian.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
