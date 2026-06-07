"""Decision matrix: classify an incident's remediation action.

Deterministic, keyword-driven rules over the failed step + root cause + parsed
summary, with the model's severity suggestion as a tiebreaker and a safe
default of HUMAN_ESCALATION when signals are insufficient.
"""

from __future__ import annotations

VALID_ACTIONS = {"AUTO_ROLLBACK", "SERVICE_RESTART", "HUMAN_ESCALATION"}

# Transient / infrastructure problems a restart would likely clear.
_RESTART_KEYS = (
    "timeout", "timed out", "connection refused", "econnrefused", "connection reset",
    "temporarily unavailable", "temporary failure", "could not connect",
    "network is unreachable", "i/o timeout", "502 bad gateway", "503 service",
    "out of memory", "oomkilled", "broken pipe", "deadline exceeded",
    "rate limit", "too many requests", "connection timed out",
)

# A newly deployed change broke a working system -> revert it.
_ROLLBACK_KEYS = (
    "health check", "healthcheck", "/health", "unhealthy", "failed to start",
    "crashloop", "container exited", "container failed", "migration failed",
    "rollback", "port is already allocated", "did not become healthy",
    "readiness probe", "liveness probe",
)

# Code / test / build / configuration errors that need a human.
_ESCALATE_KEYS = (
    "assertionerror", "syntaxerror", "importerror", "modulenotfound", "typeerror",
    "nameerror", "test failed", "tests failed", "failing test", "compilation",
    "cannot compile", "undefined reference", "lint", "mypy", "permission denied",
    "unauthorized", "forbidden", "secret is not set", "merge conflict",
    "no such file", "command not found",
)


def classify_remediation(
    failed_step: str | None,
    root_cause: str | None,
    parsed_summary: str | None,
    exit_code: int | None = None,
    llm_severity: str | None = None,
) -> tuple[str, str]:
    """Return (action, reason). action is one of VALID_ACTIONS."""
    haystack = " ".join(
        part for part in (failed_step, root_cause, parsed_summary) if part
    ).lower()

    def has(keys: tuple[str, ...]) -> bool:
        return any(k in haystack for k in keys)

    if has(_RESTART_KEYS):
        return "SERVICE_RESTART", "transient/infrastructure signal"
    if has(_ROLLBACK_KEYS):
        return "AUTO_ROLLBACK", "deployment/health regression signal"
    if has(_ESCALATE_KEYS):
        return "HUMAN_ESCALATION", "code/test/config error signal"
    if llm_severity in VALID_ACTIONS:
        return llm_severity, "model recommendation"
    return "HUMAN_ESCALATION", "default (insufficient signal)"
