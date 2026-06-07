"""Database schema and persistence for webhook incidents."""

from __future__ import annotations

import gzip
import logging
import time

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import OperationalError

from app.db import engine

logger = logging.getLogger("guardian")

metadata = MetaData()

# Every failure webhook the guardian receives is recorded here. The log* columns
# are populated asynchronously by the Celery log-retrieval task (Phase 4).
incidents = Table(
    "incidents",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("job_id", String(64)),
    Column("workflow", Text),
    Column("repo_owner", Text),
    Column("repo_name", Text),
    Column("commit_sha", String(64)),
    Column("branch", Text),
    Column("conclusion", Text),
    Column("html_url", Text),
    Column("event_timestamp", DateTime(timezone=True)),
    Column("received_at", DateTime(timezone=True), server_default=func.now()),
    Column("raw_payload", JSONB),
    # Phase 4 — log retrieval/parsing
    Column("raw_log", LargeBinary),          # gzip-compressed raw job log
    Column("parsed_summary", Text),          # clean, extracted failure lines
    Column("failed_step", Text),
    Column("exit_code", Integer),
    Column("log_status", Text),              # retrieved | no_logs | error | skipped
    Column("log_retrieved_at", DateTime(timezone=True)),
    # Phase 5 — AI root-cause analysis + remediation decision
    Column("root_cause", Text),              # plain-English diagnosis from Cerebras
    Column("remediation_action", Text),      # AUTO_ROLLBACK | SERVICE_RESTART | HUMAN_ESCALATION
    Column("ai_status", Text),               # analyzed | error | skipped
    Column("analyzed_at", DateTime(timezone=True)),
    # Phase 6 — autonomous remediation engine
    Column("remediation_status", Text),      # RECOVERED | FAILED_RECOVERY | ESCALATED
    Column("remediation_detail", Text),      # human-readable action + outcome log
    Column("escalation_reason", Text),       # why a human is needed (HUMAN_ESCALATION)
    Column("escalation_summary", Text),      # structured JSON summary for reporting
    Column("remediated_at", DateTime(timezone=True)),
    # Phase 7 — incident reporting / Gmail notification
    Column("report_sent", Boolean, server_default=text("false")),
    Column("report_sent_at", DateTime(timezone=True)),
)

# Idempotent migration so existing tables gain the Phase 4 columns. create_all
# never alters an existing table, so we add columns explicitly.
_PHASE4_COLUMNS = [
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS raw_log BYTEA",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS parsed_summary TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS failed_step TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS exit_code INTEGER",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS log_status TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS log_retrieved_at TIMESTAMPTZ",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS root_cause TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS remediation_action TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS ai_status TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMPTZ",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS remediation_status TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS remediation_detail TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS escalation_reason TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS escalation_summary TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS remediated_at TIMESTAMPTZ",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS report_sent BOOLEAN DEFAULT false",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS report_sent_at TIMESTAMPTZ",
]


def create_tables(retries: int = 10, delay: float = 3.0) -> None:
    """Ensure the incidents table and Phase 4 columns exist, retrying until the DB is up."""
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            metadata.create_all(engine)
            with engine.begin() as conn:
                for stmt in _PHASE4_COLUMNS:
                    conn.execute(text(stmt))
            logger.info("Database schema ready (incidents table + log columns ensured)")
            return
        except OperationalError as exc:  # DB not accepting connections yet
            last_err = exc
            logger.warning("DB not ready (attempt %s/%s), retrying...", attempt, retries)
            time.sleep(delay)
    raise RuntimeError(f"Could not initialise database schema: {last_err}")


def insert_incident(event: dict, raw_payload: dict) -> int:
    """Persist one incident row and return its id."""
    with engine.begin() as conn:
        result = conn.execute(
            incidents.insert()
            .values(
                job_id=event.get("job_id"),
                workflow=event.get("workflow"),
                repo_owner=event.get("repo_owner"),
                repo_name=event.get("repo_name"),
                commit_sha=event.get("commit_sha"),
                branch=event.get("branch"),
                conclusion=event.get("conclusion"),
                html_url=event.get("html_url"),
                event_timestamp=event.get("event_timestamp"),
                raw_payload=raw_payload,
            )
            .returning(incidents.c.id)
        )
        return int(result.scalar_one())


def get_incident_basic(incident_id: int) -> dict | None:
    """Fields the log-retrieval task needs to call the GitHub API."""
    with engine.connect() as conn:
        row = conn.execute(
            select(
                incidents.c.id,
                incidents.c.job_id,
                incidents.c.repo_owner,
                incidents.c.repo_name,
                incidents.c.conclusion,
            ).where(incidents.c.id == incident_id)
        ).mappings().first()
    return dict(row) if row else None


def get_incident_for_analysis(incident_id: int) -> dict | None:
    """Fields the AI analysis task needs."""
    with engine.connect() as conn:
        row = conn.execute(
            select(
                incidents.c.id,
                incidents.c.failed_step,
                incidents.c.parsed_summary,
                incidents.c.exit_code,
            ).where(incidents.c.id == incident_id)
        ).mappings().first()
    return dict(row) if row else None


def get_incident_for_remediation(incident_id: int) -> dict | None:
    """Fields the remediation engine needs."""
    with engine.connect() as conn:
        row = conn.execute(
            select(
                incidents.c.id,
                incidents.c.remediation_action,
                incidents.c.repo_owner,
                incidents.c.repo_name,
                incidents.c.job_id,
                incidents.c.commit_sha,
                incidents.c.branch,
                incidents.c.conclusion,
                incidents.c.failed_step,
                incidents.c.exit_code,
                incidents.c.root_cause,
                incidents.c.html_url,
            ).where(incidents.c.id == incident_id)
        ).mappings().first()
    return dict(row) if row else None


def get_incident_report(incident_id: int) -> dict | None:
    """All fields needed to build the incident report email."""
    cols = [
        incidents.c.id,
        incidents.c.repo_owner,
        incidents.c.repo_name,
        incidents.c.branch,
        incidents.c.commit_sha,
        incidents.c.failed_step,
        incidents.c.exit_code,
        incidents.c.root_cause,
        incidents.c.remediation_action,
        incidents.c.remediation_status,
        incidents.c.remediation_detail,
        incidents.c.escalation_reason,
        incidents.c.html_url,
        incidents.c.received_at,
        incidents.c.remediated_at,
    ]
    with engine.connect() as conn:
        row = conn.execute(
            select(*cols).where(incidents.c.id == incident_id)
        ).mappings().first()
    return dict(row) if row else None


def update_incident_logs(incident_id: int, **fields) -> None:
    """Update the log* columns of an incident. Keys must be valid column names."""
    if not fields:
        return
    with engine.begin() as conn:
        conn.execute(
            incidents.update().where(incidents.c.id == incident_id).values(**fields)
        )


def recent_incidents(limit: int = 20) -> list[dict]:
    """Return the most recent incidents (raw payload/log omitted) for inspection."""
    cols = [
        incidents.c.id,
        incidents.c.job_id,
        incidents.c.repo_owner,
        incidents.c.repo_name,
        incidents.c.branch,
        incidents.c.conclusion,
        incidents.c.failed_step,
        incidents.c.exit_code,
        incidents.c.log_status,
        incidents.c.remediation_action,
        incidents.c.ai_status,
        incidents.c.remediation_status,
        incidents.c.log_retrieved_at,
        incidents.c.received_at,
    ]
    with engine.connect() as conn:
        rows = conn.execute(
            select(*cols).order_by(incidents.c.id.desc()).limit(limit)
        ).mappings().all()

    result: list[dict] = []
    for row in rows:
        item = dict(row)
        for key in ("log_retrieved_at", "received_at"):
            if item.get(key) is not None:
                item[key] = item[key].isoformat()
        result.append(item)
    return result


def get_incident_detail(incident_id: int) -> dict | None:
    """Full incident incl. decompressed log excerpt and sizes (never any secret)."""
    with engine.connect() as conn:
        row = conn.execute(
            select(incidents).where(incidents.c.id == incident_id)
        ).mappings().first()
    if not row:
        return None

    item = dict(row)
    raw = item.pop("raw_log", None)
    item["raw_log_gz_bytes"] = len(raw) if raw else 0
    item["raw_log_chars"] = 0
    item["raw_log_excerpt"] = None
    if raw:
        try:
            decompressed = gzip.decompress(bytes(raw)).decode("utf-8", "replace")
            item["raw_log_chars"] = len(decompressed)
            item["raw_log_excerpt"] = decompressed[:2000]
        except Exception:  # noqa: BLE001
            item["raw_log_excerpt"] = "<unable to decompress>"

    for key in (
        "event_timestamp",
        "received_at",
        "log_retrieved_at",
        "analyzed_at",
        "remediated_at",
        "report_sent_at",
    ):
        if item.get(key) is not None:
            item[key] = item[key].isoformat()
    return item
