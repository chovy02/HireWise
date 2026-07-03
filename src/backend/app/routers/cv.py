from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.dependencies import get_current_user, require_role
from app.database import get_db
from app.services.ai_agent import pipeline
from app.services.ai_agent.exceptions import AIServiceError
from app.services.ai_agent.tasks import evaluate_candidate_task

# ────────────────────────────────────────────────────────────
# Router 1: Job Description
# ────────────────────────────────────────────────────────────
jd_router = APIRouter(prefix="/jds", tags=["Job Description"])


@jd_router.post("", status_code=status.HTTP_201_CREATED, response_model=schemas.JDResponse)
def create_jd(
    payload: schemas.JDCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr_staff", "admin")),
):
    """HR nhập yêu cầu tuyển dụng bằng ngôn ngữ tự nhiên, AI chuẩn hóa thành JD có cấu trúc."""
    try:
        jd = pipeline.create_jd_from_text(db, payload.raw_text, created_by=current_user.id)
    except ValueError as e:
        # JD thiếu thông tin tối thiểu -> lỗi nhập liệu của HR.
        raise HTTPException(status_code=422, detail=str(e))
    except AIServiceError as e:
        # Gemini lỗi/không cấu hình -> lỗi hạ tầng, HR nhập đúng vẫn gặp.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    return jd


@jd_router.get("", response_model=list[schemas.JDListItem])
def list_jds(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return db.query(models.JobDescription).order_by(models.JobDescription.created_at.desc()).all()


@jd_router.get("/{jd_id}", response_model=schemas.JDResponse)
def get_jd(
    jd_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    jd = db.query(models.JobDescription).filter(models.JobDescription.id == jd_id).first()
    if not jd:
        raise HTTPException(status_code=404, detail="Không tìm thấy vị trí tuyển dụng.")
    return jd


@jd_router.post(
    "/{jd_id}/cvs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=schemas.UploadBatchResponse,
)
async def upload_cvs(
    jd_id: UUID,
    file: UploadFile = File(..., description="File ZIP chứa nhiều CV dạng PDF"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr_staff", "admin")),
):
    """
    UC U002 + U003. Nhận ZIP CV -> giải nén + tạo Candidate PENDING (nhanh) rồi
    ĐẨY việc chấm điểm AI mỗi CV vào hàng đợi Celery và TRẢ VỀ NGAY (202 Accepted).

    Frontend poll GET /jds/{jd_id}/candidates để thấy status/điểm cập nhật dần,
    không phải chờ toàn bộ CV xử lý xong.
    """
    jd = db.query(models.JobDescription).filter(models.JobDescription.id == jd_id).first()
    if not jd:
        raise HTTPException(status_code=404, detail="Không tìm thấy vị trí tuyển dụng.")

    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file .zip chứa nhiều CV PDF.")

    zip_bytes = await file.read()

    # PHA 1 (đồng bộ, nhanh): tạo Candidate PENDING, không gọi AI.
    staged = pipeline.stage_cvs(db, jd, zip_bytes)

    # PHA 2 (nền): mỗi CV PENDING thành 1 task Celery chạy trên worker riêng.
    for item in staged:
        if item["status"] == "pending":
            evaluate_candidate_task.delay(str(item["candidate_id"]))

    processing = sum(1 for r in staged if r["status"] == "pending")
    failed = sum(1 for r in staged if r["status"] == "failed")
    duplicated = sum(1 for r in staged if r["status"] == "duplicated")

    return schemas.UploadBatchResponse(
        jd_id=jd.id,
        total=len(staged),
        completed=0,
        processing=processing,
        failed=failed,
        duplicated=duplicated,
        results=staged,
    )


@jd_router.get("/{jd_id}/candidates", response_model=list[schemas.CandidateListItem])
def get_leaderboard(
    jd_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """UC U004 - View Candidate Leaderboard: bảng xếp hạng theo điểm phù hợp, giảm dần."""
    candidates = db.query(models.Candidate).filter(models.Candidate.jd_id == jd_id).all()

    items = [
        schemas.CandidateListItem(
            id=c.id,
            name=c.name,
            email=c.email,
            status=c.status,
            score=c.evaluation.score if c.evaluation else None,
            # Kỹ năng đã trích (khử trùng, giữ thứ tự) để FE hiển thị chip trên bảng.
            skills=list(dict.fromkeys(s.skill_name for s in c.skills))[:15],
            is_overridden=c.evaluation.is_overridden if c.evaluation else False,
        )
        for c in candidates
    ]
    # Ứng viên có điểm xếp trước, điểm cao xếp trước; chưa có điểm (None) xếp cuối.
    items.sort(key=lambda x: (x.score is None, -(x.score or 0)))
    return items


# ────────────────────────────────────────────────────────────
# Router 2: Candidate detail
# ────────────────────────────────────────────────────────────
candidate_router = APIRouter(prefix="/candidates", tags=["Candidates"])


@candidate_router.get("/{candidate_id}", response_model=schemas.CandidateDetailResponse)
def get_candidate(
    candidate_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    candidate = db.query(models.Candidate).filter(models.Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Không tìm thấy ứng viên.")
    return candidate


# ────────────────────────────────────────────────────────────
# Router 3: Evaluation override
# ────────────────────────────────────────────────────────────
evaluation_router = APIRouter(prefix="/evaluations", tags=["Evaluations"])


@evaluation_router.patch("/{evaluation_id}/override", response_model=schemas.EvaluationResponse)
def override_evaluation(
    evaluation_id: UUID,
    payload: schemas.EvaluationOverrideRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr_staff", "admin")),
):
    """HR điều chỉnh điểm AI chấm sai, lưu lịch sử thay đổi vào evaluation_overrides."""
    evaluation = db.query(models.Evaluation).filter(models.Evaluation.id == evaluation_id).first()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Không tìm thấy đánh giá.")

    db.add(models.EvaluationOverride(
        evaluation_id=evaluation.id,
        user_id=current_user.id,
        old_score=evaluation.score,
        new_score=payload.new_score,
        reason=payload.reason,
    ))

    evaluation.score = payload.new_score
    evaluation.is_overridden = True
    db.commit()
    db.refresh(evaluation)
    return evaluation