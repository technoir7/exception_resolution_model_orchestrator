"""
Celery application configuration.
"""

from celery import Celery

from apps.api.config import settings

celery_app = Celery(
    "ap_reconciliation",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["apps.api.tasks.pipeline_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
