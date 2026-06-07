"""Minimal GitHub REST API client for pulling Actions job logs.

The GH_PAT is read from settings and sent only as an Authorization header. It is
never logged. ``requests`` follows GitHub's 302 redirect to the (already-signed)
log blob URL and drops the Authorization header on that cross-host hop.
"""

from __future__ import annotations

import requests

from app.config import get_settings

GITHUB_API = "https://api.github.com"


class LogsNotFound(Exception):
    """The job exists but logs are unavailable (404 / expired)."""


def fetch_job_logs(owner: str, repo: str, job_id: str | int, timeout: int = 30) -> str:
    """Return the raw plain-text logs for a single Actions job.

    Endpoint: GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs
    Raises LogsNotFound on 404, RuntimeError if GH_PAT is missing, and the
    underlying HTTPError for other non-2xx responses.
    """
    token = get_settings().gh_pat
    if not token:
        raise RuntimeError("GH_PAT is not configured")

    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/jobs/{job_id}/logs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "agentic-deployment-guardian",
    }

    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code == 404:
        raise LogsNotFound(f"no logs for job {job_id} in {owner}/{repo}")
    resp.raise_for_status()
    return resp.text
