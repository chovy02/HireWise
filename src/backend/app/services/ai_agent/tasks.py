from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services.ai_agent import pipeline


@celery_app.task(name="evaluate_candidate")
def evaluate_candidate_task(candidate_id: str) -> dict:
    """
    Task nền: chấm điểm 1 CV (parse -> score -> evidence -> lưu Evaluation).

    Tự mở session DB riêng vì session của HTTP request đã đóng khi response trả về.
    Nhận candidate_id dạng str (Celery serialize sang JSON), pipeline sẽ tự đổi về UUID.
    """
    db = SessionLocal()
    try:
        return pipeline.evaluate_candidate(db, candidate_id)
    finally:
        db.close()
