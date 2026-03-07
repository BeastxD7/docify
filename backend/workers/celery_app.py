from celery import Celery

from config import settings

celery_app = Celery(
    "docify",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,          # ack only after task completes (safe retries)
    worker_prefetch_multiplier=1, # one task per worker at a time (fair for long jobs)
)
