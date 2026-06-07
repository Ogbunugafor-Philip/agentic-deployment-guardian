"""AUTO_ROLLBACK: revert main to the last successful deploy commit.

By default this runs in dry-run mode (identifies the target and records the plan
but does not push). Set REMEDIATION_ROLLBACK_ENABLED=true to perform the real
revert, which requires a GH_PAT with write (contents) + workflow scope.
"""

from __future__ import annotations

import logging

from app import github_api
from app.config import get_settings

logger = logging.getLogger("guardian.rollback")

_GUARDIAN_PREFIX = "[guardian] auto-rollback"


def run_rollback(incident: dict) -> tuple[str, str]:
    """Return (remediation_status, remediation_detail)."""
    from app.remediation import poll_health  # local import avoids cycle

    settings = get_settings()
    owner = incident.get("repo_owner")
    repo = incident.get("repo_name")
    failed_sha = incident.get("commit_sha")

    if not (owner and repo):
        return "FAILED_RECOVERY", "Rollback aborted: incident is missing repository owner/name."

    try:
        good_sha = github_api.get_last_successful_deploy_sha(owner, repo, exclude_sha=failed_sha)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rollback: could not query deploy history: %s", exc.__class__.__name__)
        return "FAILED_RECOVERY", f"Rollback aborted: could not query deploy history ({exc.__class__.__name__})."

    if not good_sha:
        return "FAILED_RECOVERY", "Rollback aborted: no prior successful deploy commit found."

    if not settings.remediation_rollback_enabled:
        detail = (
            f"[dry-run] Rollback prepared: would revert {owner}/{repo} main to last "
            f"successful deploy commit {good_sha[:8]}. Execution is disabled "
            f"(set REMEDIATION_ROLLBACK_ENABLED=true to perform the revert)."
        )
        logger.info("Rollback (dry-run) for incident #%s -> %s", incident.get("id"), good_sha[:8])
        healthy = poll_health()
        return ("RECOVERED" if healthy else "FAILED_RECOVERY"), detail

    # --- live rollback ---
    try:
        head_sha = github_api.get_ref_sha(owner, repo, "heads/main")
        head_commit = github_api.get_commit(owner, repo, head_sha)
        if (head_commit.get("message") or "").startswith(_GUARDIAN_PREFIX):
            return (
                "FAILED_RECOVERY",
                "Rollback aborted: main HEAD is already a guardian rollback "
                "(avoiding a rollback loop). Escalate to a human.",
            )
        good_commit = github_api.get_commit(owner, repo, good_sha)
        new_sha = github_api.create_commit(
            owner,
            repo,
            f"{_GUARDIAN_PREFIX} to {good_sha[:8]} (incident #{incident.get('id')})",
            good_commit["tree"]["sha"],
            head_sha,
        )
        github_api.update_ref(owner, repo, "heads/main", new_sha)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live rollback failed for incident #%s: %s", incident.get("id"), exc.__class__.__name__)
        return "FAILED_RECOVERY", f"Rollback push failed ({exc.__class__.__name__})."

    detail = (
        f"Reverted {owner}/{repo} main to last successful commit {good_sha[:8]} "
        f"via revert commit {new_sha[:8]}; deploy pipeline triggered."
    )
    logger.info("Live rollback for incident #%s: %s -> %s", incident.get("id"), good_sha[:8], new_sha[:8])
    healthy = poll_health()
    return ("RECOVERED" if healthy else "FAILED_RECOVERY"), detail
