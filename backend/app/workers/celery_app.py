from celery import Celery

from app.config import get_settings


settings = get_settings()

celery_app = Celery(
    "verda_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_default_queue="research",
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_default_retry_delay=10,
    broker_transport_options={"priority_steps": list(range(10)), "queue_order_strategy": "priority"},
)
