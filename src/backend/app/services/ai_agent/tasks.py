import os
import random
import uuid

from celery.exceptions import Retry

from app import models
from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services.ai_agent import pipeline
from app.services.ai_agent.exceptions import LLMBudgetExhausted

# Số lần hẹn lại tối đa cho 1 CV khi vướng hạn mức Groq. Với ZIP nhiều CV, những CV
# xếp cuối hàng có thể phải chờ qua vài cửa sổ rate limit mới tới lượt, nên con số
# này cần rộng tay — mỗi lần hẹn lại gần như không tốn gì (task chỉ nằm trong Redis).
MAX_BUDGET_RETRIES = int(os.getenv("CV_TASK_MAX_RETRIES", "12"))


def _mark_budget_failure(db, candidate_id: str, message: str) -> None:
    """Hết sạch lượt hẹn lại thì phải để lại dấu vết, không được bỏ CV kẹt PENDING
    im lặng — HR nhìn màn hình sẽ tưởng hệ thống vẫn đang chạy."""
    try:
        cid = uuid.UUID(candidate_id) if isinstance(candidate_id, str) else candidate_id
        candidate = (
            db.query(models.Candidate).filter(models.Candidate.id == cid).first()
        )
        if candidate:
            candidate.status = "FAILED"
            candidate.error_message = message
            db.commit()
    except Exception:  # noqa: BLE001 - đang ở nhánh xử lý lỗi, không được ném thêm
        db.rollback()


@celery_app.task(
    name="evaluate_candidate",
    bind=True,
    max_retries=MAX_BUDGET_RETRIES,
    # Hạn mức Groq tính theo phút, nên rải task ra thay vì để cả batch cùng lao vào.
    # Đây là chốt chặn cuối; điều tiết chính đã do rate_limiter (Redis) đảm nhiệm.
    rate_limit=os.getenv("CV_TASK_RATE_LIMIT", "20/m"),
)
def evaluate_candidate_task(self, candidate_id: str) -> dict:
    """
    Task nền: chấm điểm 1 CV (parse -> score+evidence -> lưu Evaluation).

    Tự mở session DB riêng vì session của HTTP request đã đóng khi response trả về.
    Nhận candidate_id dạng str (Celery serialize sang JSON), pipeline sẽ tự đổi về UUID.

    Vướng hạn mức Groq thì HẸN LẠI chứ không báo lỗi: CV vẫn ở PENDING và sẽ được
    chấm khi cửa sổ rate limit mở ra, HR không phải bấm "Thử lại" thủ công.
    """
    db = SessionLocal()
    try:
        return pipeline.evaluate_candidate(db, candidate_id)

    except LLMBudgetExhausted as e:
        # Cộng thêm jitter: cả batch cùng hẹn lại đúng một mốc thời gian thì lát nữa
        # chúng lại cùng lúc lao vào và cùng bị chặn tiếp.
        delay = float(getattr(e, "retry_after", 60) or 60)
        countdown = min(delay, 300) + random.uniform(0, 15)
        try:
            raise self.retry(exc=e, countdown=countdown)
        except Retry:
            raise  # hẹn lại thành công — đây là luồng bình thường, không phải lỗi
        except Exception:
            _mark_budget_failure(
                db,
                candidate_id,
                f"Hết hạn mức AI sau {MAX_BUDGET_RETRIES} lần chờ. "
                "Hãy thử lại sau khi quota Groq được cấp lại.",
            )
            raise
    finally:
        db.close()
