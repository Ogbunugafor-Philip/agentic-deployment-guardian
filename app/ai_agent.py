"""LangChain agent that asks Cerebras (gpt-oss-120b) for a root-cause analysis.

The CEREBRAS_API_KEY is read from the environment by ChatCerebras and from
settings here only to gate execution. It is never logged or returned.
"""

from __future__ import annotations

import json
import logging
import re

from langchain_cerebras import ChatCerebras
from langchain_core.prompts import ChatPromptTemplate

from app.config import get_settings

logger = logging.getLogger("guardian.ai")

_SYSTEM = (
    "You are an expert CI/CD site-reliability engineer working for the Agentic "
    "Deployment Guardian. You are given the parsed log summary and the failed "
    "step of a failed GitHub Actions job. Produce a root-cause analysis that a "
    "non-expert can understand.\n\n"
    "Respond with ONLY a single minified JSON object (no markdown, no prose "
    "outside the JSON) with exactly these keys:\n"
    '  "failure_point": the exact step/command/line where it failed,\n'
    '  "explanation": 2-4 plain-English sentences, no jargon, on WHY it failed,\n'
    '  "suggested_fix": the single most likely fix, concrete and actionable,\n'
    '  "severity": one of "AUTO_ROLLBACK", "SERVICE_RESTART", "HUMAN_ESCALATION".\n\n'
    "Severity guidance: AUTO_ROLLBACK = a newly deployed change broke a "
    "previously working deployment/health check and reverting is the safest "
    "immediate action; SERVICE_RESTART = a transient infrastructure/network/"
    "timeout/resource problem a restart would likely clear; HUMAN_ESCALATION = a "
    "code/test/build/configuration error that needs a human to change code or "
    "settings."
)

_HUMAN = (
    "Failed step: {failed_step}\n"
    "Exit code: {exit_code}\n"
    "Parsed log summary:\n{parsed_summary}\n"
    "{pattern_note}\n"
    "Return the JSON now."
)

_VALID_SEVERITY = {"AUTO_ROLLBACK", "SERVICE_RESTART", "HUMAN_ESCALATION"}


def _extract_json(content: str) -> dict:
    """Pull a JSON object out of the model response, tolerating fences/prose."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = content.find("{"), content.rfind("}")
        candidate = content[start : end + 1] if start != -1 and end > start else ""
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return {}


def _build_chain():
    settings = get_settings()
    # api key is read from the CEREBRAS_API_KEY env var by ChatCerebras.
    llm = ChatCerebras(
        model=settings.cerebras_model,
        temperature=0,
        max_tokens=1024,
        timeout=60,
        max_retries=2,
    )
    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])
    return prompt | llm


def _pattern_note(pattern: dict | None) -> str:
    """Phase 8: extra prompt context when this failure matches a known pattern."""
    if not pattern:
        return ""
    return (
        "\nThis failure matches a known pattern: "
        f"\"{pattern.get('pattern_label')}\". "
        f"It has occurred {pattern.get('occurrence_count')} times before. "
        f"Previous suggested fix: {pattern.get('suggested_fix') or 'n/a'}. "
        "Use this history to diagnose faster and more confidently.\n"
    )


def analyze_failure(
    failed_step: str | None,
    parsed_summary: str | None,
    exit_code: int | None,
    pattern: dict | None = None,
) -> dict:
    """Return {root_cause, failure_point, explanation, suggested_fix, severity_hint, model}.

    Raises RuntimeError if no API key is configured; lets transport errors
    propagate so the caller can retry.
    """
    settings = get_settings()
    if not settings.cerebras_api_key:
        raise RuntimeError("CEREBRAS_API_KEY is not configured")

    chain = _build_chain()
    response = chain.invoke(
        {
            "failed_step": failed_step or "unknown",
            "exit_code": exit_code if exit_code is not None else "unknown",
            "parsed_summary": (parsed_summary or "<no parsed summary available>")[:6000],
            "pattern_note": _pattern_note(pattern),
        }
    )
    content = getattr(response, "content", None) or str(response)
    data = _extract_json(content)

    failure_point = (data.get("failure_point") or failed_step or "unknown").strip()
    explanation = (data.get("explanation") or content.strip())[:4000]
    suggested_fix = (data.get("suggested_fix") or "No specific fix suggested.").strip()
    severity = data.get("severity")
    severity_hint = severity if severity in _VALID_SEVERITY else None

    root_cause = (
        f"Failure point: {failure_point}\n"
        f"Why it failed: {explanation}\n"
        f"Suggested fix: {suggested_fix}"
    )

    return {
        "root_cause": root_cause,
        "failure_point": failure_point,
        "explanation": explanation,
        "suggested_fix": suggested_fix,
        "severity_hint": severity_hint,
        "model": settings.cerebras_model,
    }
