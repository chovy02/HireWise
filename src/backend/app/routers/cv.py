import os
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.dependencies import get_current_user, require_role
from app.core.ownership import (
    get_owned_candidate,
    get_owned_evaluation,
    get_owned_jd,
    owned_jds,
)
from app.core.ranking import score_sort_key
from app.database import get_db
from app.services import jd_deletion
from app.services.ai_agent import pipeline
from app.services.ai_agent.exceptions import AIServiceError
from app.services.ai_agent.tasks import evaluate_candidate_task
from app.services.logging import write_audit_log

# ────────────────────────────────────────────────────────────
# Router 1: Job Description
# Toàn bộ pipeline tuyển dụng (JD/CV/đánh giá) chỉ dành cho HR (RBAC theo SRS 2.4:
# Admin chỉ quản trị tài khoản/cấu hình/logs, KHÔNG thao tác nghiệp vụ tuyển dụng).
# ────────────────────────────────────────────────────────────
jd_router = APIRouter(
    prefix="/jds",
    tags=["Job Description"],
    dependencies=[Depends(require_role("hr_staff"))],
)


@jd_router.post("", status_code=status.HTTP_201_CREATED, response_model=schemas.JDResponse)
def create_jd(
    payload: schemas.JDCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
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

    write_audit_log(
        db, user_id=current_user.id, action="CREATE_JD", entity_type="job_description",
        entity_id=jd.id,
        old_data=None,
        new_data={"title": jd.title, "status": jd.status},
    )
    return jd


@jd_router.get("", response_model=list[schemas.JDListItem])
def list_jds(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # CHỈ JD do chính người dùng này tạo. Trước đây trả về cả bảng nên hai tài
    # khoản HR khác nhau thấy y hệt danh sách project của nhau.
    # owned_jds() tự loại JD đang nằm trong thùng rác.
    jds = (
        owned_jds(db, current_user)
        .order_by(models.JobDescription.created_at.desc())
        .all()
    )
    return _jd_list_items(db, jds)


def _jd_list_items(db: Session, jds: list[models.JobDescription]) -> list[schemas.JDListItem]:
    """Gắn số ứng viên cho từng JD bằng 1 query gộp (tránh N+1)."""
    jd_ids = [jd.id for jd in jds]
    counts = (
        dict(
            db.query(models.Candidate.jd_id, func.count(models.Candidate.id))
            .filter(models.Candidate.jd_id.in_(jd_ids))
            .group_by(models.Candidate.jd_id)
            .all()
        )
        if jd_ids
        else {}
    )
    return [
        schemas.JDListItem(
            id=jd.id,
            title=jd.title,
            raw_text=jd.raw_text,
            status=jd.status,
            created_at=jd.created_at,
            candidate_count=counts.get(jd.id, 0),
            deleted_at=jd.deleted_at,
        )
        for jd in jds
    ]


# PHẢI khai báo TRƯỚC "/{jd_id}": FastAPI khớp route theo thứ tự đăng ký, để sau thì
# "trash" bị nuốt vào {jd_id} và lỗi 422 vì không parse được thành UUID.
@jd_router.get("/trash", response_model=list[schemas.JDListItem])
def list_trashed_jds(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Danh sách dự án đang nằm trong thùng rác, mới xoá xếp trước."""
    jds = (
        owned_jds(db, current_user, include_deleted=True)
        .filter(models.JobDescription.deleted_at.isnot(None))
        .order_by(models.JobDescription.deleted_at.desc())
        .all()
    )
    return _jd_list_items(db, jds)


@jd_router.get("/{jd_id}", response_model=schemas.JDResponse)
def get_jd(
    jd_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return get_owned_jd(db, jd_id, current_user)


@jd_router.delete("/{jd_id}", status_code=status.HTTP_200_OK)
def delete_jd(
    jd_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Xoá dự án vào THÙNG RÁC (xoá mềm). Ứng viên và điểm đã chấm giữ nguyên,
    khôi phục lại là có đủ — không tốn thêm lượt gọi AI nào."""
    jd = get_owned_jd(db, jd_id, current_user)
    candidate_count = (
        db.query(func.count(models.Candidate.id))
        .filter(models.Candidate.jd_id == jd.id)
        .scalar()
    )

    jd_deletion.soft_delete_jd(db, jd)

    write_audit_log(
        db, user_id=current_user.id, action="DELETE_JD", entity_type="job_description",
        entity_id=jd.id,
        old_data={"title": jd.title, "deleted_at": None},
        new_data={"title": jd.title, "deleted_at": jd.deleted_at.isoformat()},
    )
    return {
        "jd_id": jd.id,
        "deleted_at": jd.deleted_at,
        "candidate_count": candidate_count,
        "detail": "Đã chuyển dự án vào thùng rác.",
    }


@jd_router.post("/{jd_id}/restore", status_code=status.HTTP_200_OK)
def restore_jd(
    jd_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Khôi phục dự án từ thùng rác về bảng điều khiển."""
    jd = get_owned_jd(db, jd_id, current_user, include_deleted=True)
    if jd.deleted_at is None:
        raise HTTPException(status_code=400, detail="Dự án này không nằm trong thùng rác.")

    old_deleted_at = jd.deleted_at.isoformat()
    jd_deletion.restore_jd(db, jd)

    write_audit_log(
        db, user_id=current_user.id, action="RESTORE_JD", entity_type="job_description",
        entity_id=jd.id,
        old_data={"title": jd.title, "deleted_at": old_deleted_at},
        new_data={"title": jd.title, "deleted_at": None},
    )
    return {"jd_id": jd.id, "detail": "Đã khôi phục dự án."}


@jd_router.delete("/{jd_id}/permanent", status_code=status.HTTP_200_OK)
def purge_jd(
    jd_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Xoá VĨNH VIỄN dự án cùng toàn bộ ứng viên, điểm đánh giá và file CV gốc.
    KHÔNG THỂ HOÀN TÁC.

    Chỉ chấp nhận dự án ĐANG Ở TRONG THÙNG RÁC — bắt buộc phải qua hai bước (xoá
    mềm rồi mới xoá hẳn) nên không thể mất dữ liệu chỉ vì một cú bấm nhầm.
    """
    jd = get_owned_jd(db, jd_id, current_user, include_deleted=True)
    if jd.deleted_at is None:
        raise HTTPException(
            status_code=400,
            detail="Chỉ xoá vĩnh viễn được dự án đang nằm trong thùng rác.",
        )

    title = jd.title
    # Ghi nhật ký TRƯỚC khi xoá: sau khi purge thì jd.id không còn tham chiếu được.
    write_audit_log(
        db, user_id=current_user.id, action="PURGE_JD", entity_type="job_description",
        entity_id=jd.id,
        old_data={"title": title, "deleted_at": jd.deleted_at.isoformat()},
        new_data=None,
    )
    stats = jd_deletion.purge_jd(db, jd)

    return {
        "detail": f"Đã xoá vĩnh viễn dự án “{title}”.",
        "deleted": stats,
    }


@jd_router.post(
    "/{jd_id}/cvs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=schemas.UploadBatchResponse,
)
async def upload_cvs(
    jd_id: UUID,
    file: UploadFile = File(..., description="File ZIP chứa nhiều CV dạng PDF"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    UC U002 + U003. Nhận ZIP CV -> giải nén + tạo Candidate PENDING (nhanh) rồi
    ĐẨY việc chấm điểm AI mỗi CV vào hàng đợi Celery và TRẢ VỀ NGAY (202 Accepted).

    Frontend poll GET /jds/{jd_id}/candidates để thấy status/điểm cập nhật dần,
    không phải chờ toàn bộ CV xử lý xong.
    """
    jd = get_owned_jd(db, jd_id, current_user)

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

    # Lưu lượt tải này lại. Không lưu thì sau khi F5, giao diện không còn cách nào
    # biết các ứng viên đã có đến từ file nào — ô "Lượt tải lên" luôn hiện 0.
    db.add(models.UploadBatch(
        jd_id=jd.id,
        filename=file.filename,
        total=len(staged),
        staged=processing,
        duplicated=duplicated,
        failed=failed,
        uploaded_by=current_user.id,
    ))
    db.commit()

    return schemas.UploadBatchResponse(
        jd_id=jd.id,
        total=len(staged),
        completed=0,
        processing=processing,
        failed=failed,
        duplicated=duplicated,
        results=staged,
    )


@jd_router.get("/{jd_id}/uploads", response_model=list[schemas.UploadHistoryItem])
def list_uploads(
    jd_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lịch sử các lượt tải ZIP CV của vị trí này, mới nhất xếp trước."""
    jd = get_owned_jd(db, jd_id, current_user)
    return (
        db.query(models.UploadBatch)
        .filter(models.UploadBatch.jd_id == jd.id)
        .order_by(models.UploadBatch.created_at.desc())
        .all()
    )


@jd_router.get("/{jd_id}/candidates", response_model=list[schemas.CandidateListItem])
def get_leaderboard(
    jd_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """UC U004 - View Candidate Leaderboard: bảng xếp hạng theo điểm phù hợp, giảm dần."""
    # Chốt quyền trên JD trước: nếu không phải JD của mình thì 404 luôn, không lộ
    # danh sách ứng viên của người khác.
    jd = get_owned_jd(db, jd_id, current_user)
    candidates = db.query(models.Candidate).filter(models.Candidate.jd_id == jd.id).all()

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
            error_message=c.error_message,
            created_at=c.created_at,
        )
        for c in candidates
    ]
    # Ứng viên có điểm xếp trước, điểm cao xếp trước; chưa có điểm (None) xếp cuối.
    # score_sort_key phá hoà bằng (created_at, id): thiếu chốt phá hoà thì hai ứng viên
    # TRÙNG ĐIỂM lấy đúng thứ tự heap của Postgres, và chỉ một lần UPDATE lên hàng nào đó
    # là chúng đổi chỗ nhau sau khi HR nạp lại trang.
    items.sort(key=score_sort_key)
    return items


# ────────────────────────────────────────────────────────────
# Router 2: Candidate detail
# ────────────────────────────────────────────────────────────
candidate_router = APIRouter(
    prefix="/candidates",
    tags=["Candidates"],
    dependencies=[Depends(require_role("hr_staff"))],
)


@candidate_router.get("/{candidate_id}", response_model=schemas.CandidateDetailResponse)
def get_candidate(
    candidate_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return get_owned_candidate(db, candidate_id, current_user)


@candidate_router.post("/{candidate_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_candidate(
    candidate_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Chấm lại 1 CV chưa xong: đưa về PENDING và đẩy lại vào hàng đợi Celery.

    Phần lớn lỗi trích xuất là TẠM THỜI (AI quá tải, rate limit, timeout mạng) nên
    thử lại là xong; trước đây HR phải upload lại cả file ZIP, mà CV cũ lại bị chặn
    vì trùng file_hash.

    NHẬN CẢ CV ĐANG PENDING — có chủ đích: Celery ack task ngay khi nhận, nên worker
    bị restart giữa chừng là task biến mất trong khi CV vẫn nằm ở PENDING. Nếu chặn
    PENDING thì những CV kẹt kiểu đó không còn đường cứu từ giao diện. Đổi lại, HR
    bấm đúng lúc worker đang chạy thật thì CV bị chấm hai lần (tốn lượt gọi AI,
    không hỏng dữ liệu vì evaluate_candidate tự dọn trước mỗi lần chạy).

    COMPLETED thì từ chối: chấm lại sẽ xóa mất đánh giá đang dùng.
    """
    candidate = db.query(models.Candidate).filter(models.Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Không tìm thấy ứng viên.")

    if candidate.status == "COMPLETED":
        raise HTTPException(
            status_code=400,
            detail="CV này đã chấm xong, không cần chấm lại.",
        )

    candidate.status = "PENDING"
    candidate.error_message = None
    db.commit()

    # Dữ liệu cũ (skills/projects) do evaluate_candidate tự dọn ở đầu mỗi lần chạy.
    evaluate_candidate_task.delay(str(candidate.id))

    return {"candidate_id": candidate.id, "status": "PENDING"}


@candidate_router.get("/{candidate_id}/cv")
def get_candidate_cv(
    candidate_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Trả file PDF gốc của ứng viên để hiển thị lại cho HR (nhúng trong CandidateModal)."""
    candidate = get_owned_candidate(db, candidate_id, current_user)
    if not candidate.file_path or not os.path.exists(candidate.file_path):
        raise HTTPException(status_code=404, detail="Chưa lưu file CV gốc cho ứng viên này.")

    return FileResponse(
        candidate.file_path,
        media_type="application/pdf",
        filename=f"{candidate.name or 'cv'}.pdf",
        # inline để trình duyệt hiển thị trong <iframe> thay vì tải xuống.
        content_disposition_type="inline",
    )


# ────────────────────────────────────────────────────────────
# Router 3: Evaluation override
# ────────────────────────────────────────────────────────────
evaluation_router = APIRouter(
    prefix="/evaluations",
    tags=["Evaluations"],
    dependencies=[Depends(require_role("hr_staff"))],
)


@evaluation_router.patch("/{evaluation_id}/override", response_model=schemas.EvaluationResponse)
def override_evaluation(
    evaluation_id: UUID,
    payload: schemas.EvaluationOverrideRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """HR điều chỉnh điểm AI chấm sai, lưu lịch sử thay đổi vào evaluation_overrides."""
    evaluation = get_owned_evaluation(db, evaluation_id, current_user)

    db.add(models.EvaluationOverride(
        evaluation_id=evaluation.id,
        user_id=current_user.id,
        old_score=evaluation.score,
        new_score=payload.new_score,
        reason=payload.reason,
    ))

    old_score = evaluation.score
    was_overridden = evaluation.is_overridden

    evaluation.score = payload.new_score
    evaluation.is_overridden = True
    db.commit()
    db.refresh(evaluation)

    # Con người ghi đè điểm máy chấm là hành động cần truy vết được: nó thay đổi
    # thứ hạng ứng viên và phải giải trình được khi bị chất vấn về tính công bằng.
    write_audit_log(
        db, user_id=current_user.id, action="OVERRIDE_EVALUATION", entity_type="evaluation",
        entity_id=evaluation.id,
        old_data={"score": old_score, "is_overridden": was_overridden},
        new_data={
            "score": payload.new_score,
            "is_overridden": True,
            "reason": payload.reason,
        },
    )
    return evaluation