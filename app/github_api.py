"""Minimal GitHub REST API client for pulling Actions job logs.

The GH_PAT is read from settings and sent only as an Authorization header. It is
never logged. ``requests`` follows GitHub's 302 redirect to the (already-signed)
log blob URL and drops the Authorization header on that cross-host hop.
"""

from __future__ import annotations

import requests

from app.config import get_settings

GITHUB_API = "https://api.github.com"

_BOM = "﻿"


class LogsNotFound(Exception):
    """The job exists but logs are unavailable (404 / expired)."""


def _headers() -> dict:
    token = get_settings().gh_pat
    if not token:
        raise RuntimeError("GH_PAT is not configured")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "agentic-deployment-guardian",
    }


def get_last_successful_deploy_sha(
    owner: str,
    repo: str,
    workflow_name: str = "Deploy Agentic Deployment Guardian",
    exclude_sha: str | None = None,
    timeout: int = 30,
) -> str | None:
    """Return the head SHA of the most recent *successful* deploy run."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs?status=success&per_page=50"
    resp = requests.get(url, headers=_headers(), timeout=timeout)
    resp.raise_for_status()
    for run in resp.json().get("workflow_runs", []):
        if run.get("name") == workflow_name and run.get("conclusion") == "success":
            sha = run.get("head_sha")
            if sha and (exclude_sha is None or not sha.startswith(exclude_sha)):
                return sha
    return None


def get_ref_sha(owner: str, repo: str, ref: str = "heads/main", timeout: int = 30) -> str:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/{ref}", headers=_headers(), timeout=timeout
    )
    resp.raise_for_status()
    return resp.json()["object"]["sha"]


def get_commit(owner: str, repo: str, sha: str, timeout: int = 30) -> dict:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/commits/{sha}", headers=_headers(), timeout=timeout
    )
    resp.raise_for_status()
    return resp.json()


def create_commit(
    owner: str, repo: str, message: str, tree_sha: str, parent_sha: str, timeout: int = 30
) -> str:
    """Create a commit object (write scope required) and return its SHA."""
    resp = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/commits",
        headers=_headers(),
        json={"message": message, "tree": tree_sha, "parents": [parent_sha]},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["sha"]


def update_ref(owner: str, repo: str, ref: str, sha: str, timeout: int = 30) -> dict:
    """Move a ref (e.g. heads/main) to a new commit (write scope required)."""
    resp = requests.patch(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/refs/{ref}",
        headers=_headers(),
        json={"sha": sha, "force": False},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


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
    # GitHub's log blob is UTF-8 but served without a charset, so requests would
    # otherwise guess Latin-1 and mangle non-ASCII. Force UTF-8 and drop any BOM.
    resp.encoding = "utf-8"
    text = resp.text
    return text[1:] if text.startswith(_BOM) else text
