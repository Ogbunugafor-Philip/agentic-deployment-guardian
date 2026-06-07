"""Pattern recognition over deployment_history.

Groups completed incidents by (failed_step, exit_code), and when the same
failure has occurred 2+ times records it in failure_patterns with a human label.
Also exposes a lookup used to feed matching patterns back into the AI prompt.
"""

from __future__ import annotations

import logging

from app.models import (
    fetch_recurring_groups,
    find_matching_pattern,
    upsert_failure_pattern,
)

logger = logging.getLogger("guardian.patterns")


def pattern_key(failed_step: str | None, exit_code: int | None) -> str:
    return f"{(failed_step or '').strip().lower()}|{exit_code if exit_code is not None else 'na'}"


def _suggested_fix(root_cause: str | None) -> str:
    for line in (root_cause or "").splitlines():
        if line.lower().startswith("suggested fix:"):
            return line.split(":", 1)[1].strip()
    return ""


def classify_label(failed_step: str | None, root_cause: str | None) -> str:
    """Human-friendly label for a recurring failure."""
    hay = f"{failed_step or ''} {root_cause or ''}".lower()
    if any(k in hay for k in ("test", "assert", "pytest", "spec")):
        return "Recurring test failure"
    if any(k in hay for k in (".env", "environment", "secret", "config", "credential", "variable")):
        return "Repeated env/config failure"
    if any(k in hay for k in ("restart", "crash", "health", "container", "service", "oom", "memory")):
        return "Repeated service crash"
    if any(k in hay for k in ("build", "compile", "lint", "bundle")):
        return "Recurring build failure"
    if any(k in hay for k in ("deploy", "rollback", "release")):
        return "Recurring deployment failure"
    if any(k in hay for k in ("timeout", "connection", "network", "dns")):
        return "Recurring connectivity failure"
    return f"Recurring failure at step '{(failed_step or 'unknown').strip()}'"


def recompute_patterns() -> int:
    """Recompute failure_patterns from history. Returns the number of patterns."""
    groups = fetch_recurring_groups(min_count=2)
    for g in groups:
        key = pattern_key(g["failed_step"], g["exit_code"])
        label = classify_label(g["failed_step"], g.get("latest_root_cause"))
        fix = _suggested_fix(g.get("latest_root_cause"))
        upsert_failure_pattern(
            pattern_key=key,
            pattern_label=label,
            failed_step=g["failed_step"],
            exit_code=g["exit_code"],
            occurrence_count=g["occurrence_count"],
            first_seen=g["first_seen"],
            last_seen=g["last_seen"],
            suggested_fix=fix,
        )
    logger.info("Pattern recompute: %d recurring pattern(s) currently known", len(groups))
    return len(groups)


def match_for(failed_step: str | None, exit_code: int | None) -> dict | None:
    """Return a known pattern matching this failure signature, if any."""
    return find_matching_pattern(pattern_key(failed_step, exit_code))
