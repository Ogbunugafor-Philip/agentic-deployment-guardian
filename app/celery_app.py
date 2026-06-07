"""Celery application for background log retrieval/parsing.

Uses the project's Redis instance as both broker and result backend. The web
process imports this module only to enqueue tasks by name (``send_task``); the
worker process (``celery -A app.celery_app worker``) imports ``app.tasks`` via
the ``include`` list below and runs them.
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery = Celery(
    "guardian",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)
