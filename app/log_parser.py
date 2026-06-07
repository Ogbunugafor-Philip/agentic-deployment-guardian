"""Parse raw GitHub Actions job logs into a clean, structured failure summary.

GitHub job logs prefix every line with an ISO-8601 timestamp and use ``##[...]``
workflow markers (``##[group]``, ``##[error]``, etc.). This module strips that
noise, finds the failed step and exit code, and extracts the most relevant
failure lines.
"""

from __future__ import annotations

import re

# ESC[...m and other CSI sequences.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# Leading "2026-06-07T14:29:03.1234567Z " timestamp GitHub adds to each line.
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\s")
_EXIT_RE = re.compile(r"(?:exit code|exit status)\s+(\d+)", re.IGNORECASE)

# Lines worth surfacing as part of the failure.
_ERROR_RE = re.compile(
    r"(?:##\[error\]|::error|\b(?:error|errors|exception|failed|failure|fatal)\b|"
    r"traceback|exit code\s+[1-9]|exit status\s+[1-9]|npm ERR!|"
    r"AssertionError|SyntaxError|ModuleNotFoundError|ImportError|"
    r"segmentation fault|panic:)",
    re.IGNORECASE,
)

_GROUP_PREFIX = "##[group]"
_ERROR_PREFIX = "##[error]"
_MAX_SUMMARY_LINES = 60


def _strip(line: str) -> str:
    line = _ANSI_RE.sub("", line)
    line = _TS_RE.sub("", line)
    return line.rstrip()


def clean_log(raw: str) -> list[str]:
    """Strip timestamps/ANSI and collapse repeated blank lines."""
    cleaned: list[str] = []
    for original in raw.splitlines():
        line = _strip(original)
        if line == "" and (not cleaned or cleaned[-1] == ""):
            continue
        cleaned.append(line)
    return cleaned


def parse_logs(raw: str) -> dict:
    """Return a structured summary of the failure.

    Keys: failed_step, exit_code, error_lines, summary, cleaned_lines.
    """
    cleaned = clean_log(raw)

    current_group: str | None = None
    failed_step: str | None = None
    exit_code: int | None = None
    error_lines: list[str] = []

    for line in cleaned:
        if line.startswith(_GROUP_PREFIX):
            current_group = line[len(_GROUP_PREFIX):].strip() or None

        exit_match = _EXIT_RE.search(line)
        if exit_match and int(exit_match.group(1)) != 0:
            if exit_code is None:
                exit_code = int(exit_match.group(1))
            # The step running when the non-zero exit was reported is the failure point.
            if failed_step is None and current_group:
                failed_step = current_group

        if _ERROR_RE.search(line):
            text = line[len(_ERROR_PREFIX):].strip() if line.startswith(_ERROR_PREFIX) else line
            if text and (not error_lines or error_lines[-1] != text):
                error_lines.append(text)

    # Prefer explicit ##[error] step name if we never tied one to an exit code.
    if failed_step is None and current_group:
        failed_step = current_group

    relevant = error_lines[-_MAX_SUMMARY_LINES:]

    summary_parts = [
        f"Failed step: {failed_step or 'unknown'}",
        f"Exit code: {exit_code if exit_code is not None else 'unknown'}",
        "",
        "Relevant failure lines:",
    ]
    summary_parts.extend(relevant if relevant else ["<no explicit error lines found>"])
    summary = "\n".join(summary_parts)

    return {
        "failed_step": failed_step,
        "exit_code": exit_code,
        "error_lines": relevant,
        "summary": summary,
        "cleaned_lines": len(cleaned),
    }
