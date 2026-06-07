from datetime import datetime, timezone

from app.report import build_html, build_subject, build_text

INCIDENT = {
    "id": 42,
    "repo_owner": "Ogbunugafor-Philip",
    "repo_name": "agentic-deployment-guardian",
    "branch": "main",
    "commit_sha": "0ffa588abc",
    "failed_step": "Run tests",
    "exit_code": 1,
    "root_cause": (
        "Failure point: Run tests\n"
        "Why it failed: A unit test failed.\n"
        "Suggested fix: Fix the addition logic."
    ),
    "remediation_action": "SERVICE_RESTART",
    "remediation_status": "RECOVERED",
    "remediation_detail": "Restarted app.",
    "escalation_reason": None,
    "received_at": datetime(2026, 6, 7, 16, 0, 0, tzinfo=timezone.utc),
    "remediated_at": datetime(2026, 6, 7, 16, 0, 18, tzinfo=timezone.utc),
}


def test_subject_format():
    assert build_subject(INCIDENT) == "[Guardian] Incident #42 — Run tests — RECOVERED"


def test_html_has_all_five_sections():
    html = build_html(INCIDENT)
    for section in ["What Happened", "Where It Happened", "Why It Failed", "What Was Done", "Next Steps"]:
        assert section in html


def test_html_color_coding():
    assert "#1e7e34" in build_html(INCIDENT)  # green for RECOVERED
    escalated = {**INCIDENT, "remediation_status": "ESCALATED"}
    assert "#d97706" in build_html(escalated)  # orange
    failed = {**INCIDENT, "remediation_status": "FAILED_RECOVERY"}
    assert "#c0392b" in build_html(failed)  # red


def test_text_has_no_json_or_braces():
    text = build_text(INCIDENT)
    assert "{" not in text and "}" not in text
    assert "18 second" in text  # duration computed


def test_duration_unknown_when_missing():
    inc = {**INCIDENT, "remediated_at": None}
    assert "not available" in build_text(inc)
