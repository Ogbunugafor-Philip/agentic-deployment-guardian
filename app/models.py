"""Database schema and persistence for webhook incidents."""

from __future__ import annotations

import logging
import time

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import OperationalError

from app.db import engine

logger = logging.getLogger("guardian")

metadata = MetaData()

# Every failure webhook the guardian receives is recorded here.
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
)


def create_tables(retries: int = 10, delay: float = 3.0) -> None:
    """Create the incidents table if it does not exist, retrying until the DB is up."""
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            metadata.create_all(engine)
            logger.info("Database schema ready (incidents table ensured)")
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


def recent_incidents(limit: int = 20) -> list[dict]:
    """Return the most recent incidents (raw_payload omitted) for inspection."""
    cols = [
        incidents.c.id,
        incidents.c.job_id,
        incidents.c.workflow,
        incidents.c.repo_owner,
        incidents.c.repo_name,
        incidents.c.commit_sha,
        incidents.c.branch,
        incidents.c.conclusion,
        incidents.c.html_url,
        incidents.c.event_timestamp,
        incidents.c.received_at,
    ]
    with engine.connect() as conn:
        rows = conn.execute(
            select(*cols).order_by(incidents.c.id.desc()).limit(limit)
        ).mappings().all()

    result: list[dict] = []
    for row in rows:
        item = dict(row)
        for key in ("event_timestamp", "received_at"):
            if item.get(key) is not None:
                item[key] = item[key].isoformat()
        result.append(item)
    return result
