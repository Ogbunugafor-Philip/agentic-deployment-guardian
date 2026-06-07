"""Helpers for validating and parsing GitHub failure webhooks."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime


def verify_signature(
    payload_body: bytes, secret: str, signature_header: str | None
) -> bool:
    """Constant-time check of the GitHub-style X-Hub-Signature-256 header.

    The signature is HMAC-SHA256 of the raw request body keyed by the shared
    secret, formatted as ``sha256=<hexdigest>`` (identical to GitHub's scheme).
    """
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = (
        "sha256="
        + hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature_header)


def _parse_timestamp(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_event(payload: dict) -> dict:
    """Extract the incident fields from either our Actions sender payload or a
    native GitHub ``workflow_run`` webhook payload."""
    repo = payload.get("repository") or {}
    owner = repo.get("owner")
    if isinstance(owner, dict):
        owner = owner.get("login")

    workflow_run = payload.get("workflow_run")
    if isinstance(workflow_run, dict):
        # Native GitHub workflow_run webhook shape.
        return {
            "job_id": str(workflow_run.get("id") or ""),
            "workflow": workflow_run.get("name"),
            "repo_owner": owner,
            "repo_name": repo.get("name"),
            "commit_sha": workflow_run.get("head_sha"),
            "branch": workflow_run.get("head_branch"),
            "conclusion": workflow_run.get("conclusion"),
            "html_url": workflow_run.get("html_url"),
            "event_timestamp": _parse_timestamp(
                workflow_run.get("updated_at") or workflow_run.get("created_at")
            ),
        }

    # Flat shape produced by our notify-guardian GitHub Actions workflow.
    return {
        "job_id": str(payload.get("job_id") or ""),
        "workflow": payload.get("workflow"),
        "repo_owner": owner or payload.get("repo_owner"),
        "repo_name": repo.get("name") or payload.get("repo_name"),
        "commit_sha": payload.get("commit_sha"),
        "branch": payload.get("branch"),
        "conclusion": payload.get("conclusion"),
        "html_url": payload.get("html_url"),
        "event_timestamp": _parse_timestamp(payload.get("timestamp")),
    }
