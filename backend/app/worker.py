"""
Celery Worker Configuration

Async task processing for agent execution, notifications, and background jobs.
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "company_ai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Jakarta",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "agents": {"exchange": "agents", "routing_key": "agents"},
        "notifications": {"exchange": "notifications", "routing_key": "notifications"},
    },
)


@celery_app.task(name="health_check")
def health_check():
    """Simple task to verify worker is running."""
    return {"status": "worker_healthy"}
