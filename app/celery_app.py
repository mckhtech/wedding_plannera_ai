from celery import Celery
from app.config import settings

celery_app = Celery(
    "image_generation_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=['app.celery_tasks']
)

# Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker
    
    # Retry settings
    task_default_retry_delay=30,
    task_max_retries=3,
)