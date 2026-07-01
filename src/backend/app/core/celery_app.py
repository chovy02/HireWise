import os

from celery import Celery

# Redis vừa làm broker vừa làm result backend.
# Mặc định trỏ tới service "redis" trong docker-compose; override bằng env khi cần.
BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

celery_app = Celery(
    "hirewise",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["app.services.ai_agent.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
    broker_connection_retry_on_startup = True,
    # Chỉ ack task SAU khi chạy xong -> worker crash giữa chừng thì task được giao lại,
    # không mất CV đang xử lý.
    task_acks_late=True,
    # Mỗi worker chỉ nhận 1 task một lúc, chia đều tải giữa nhiều worker.
    worker_prefetch_multiplier=1,
)

# Alias để lệnh `celery -A app.core.celery_app worker` tự tìm được instance.
celery = celery_app
