"""Xoá dự án tuyển dụng (JD): xoá mềm vào thùng rác, khôi phục, và xoá vĩnh viễn.

VÌ SAO CÓ THÙNG RÁC: một JD kéo theo hàng chục CV đã tốn quota AI để chấm điểm.
Xoá thẳng khỏi DB thì bấm nhầm một cái là mất trắng, và chấm lại không chỉ mất thời
gian mà còn đụng trần token/ngày của Groq. Xoá mềm cho phép khôi phục nguyên vẹn;
muốn xoá hẳn thì phải vào thùng rác xác nhận thêm lần nữa.
"""

import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models


def soft_delete_jd(db: Session, jd: models.JobDescription) -> None:
    """Đưa JD vào thùng rác. Dữ liệu con giữ nguyên, chỉ bị ẩn khỏi mọi truy vấn."""
    jd.deleted_at = datetime.now(timezone.utc)
    db.commit()


def restore_jd(db: Session, jd: models.JobDescription) -> None:
    """Lấy JD ra khỏi thùng rác, trả lại đúng trạng thái trước khi xoá."""
    jd.deleted_at = None
    db.commit()


def _delete_cv_files(candidates: list[models.Candidate]) -> int:
    """Xoá file PDF gốc trên đĩa. Lỗi I/O KHÔNG được chặn việc xoá bản ghi DB —
    file mồ côi chỉ tốn chỗ, còn bản ghi mồ côi thì làm hỏng cả giao diện."""
    removed = 0
    for c in candidates:
        if not c.file_path:
            continue
        try:
            if os.path.exists(c.file_path):
                os.remove(c.file_path)
                removed += 1
        except OSError:
            pass
    return removed


def purge_jd(db: Session, jd: models.JobDescription) -> dict:
    """
    Xoá VĨNH VIỄN một JD cùng toàn bộ dữ liệu con. Không thể hoàn tác.

    Các bảng con đều dùng khoá ngoại KHÔNG có ON DELETE CASCADE, nên phải tự xoá
    theo đúng thứ tự từ lá lên gốc; sai thứ tự là dính lỗi vi phạm khoá ngoại.

    Trả về số bản ghi đã xoá từng loại, để ghi vào nhật ký kiểm toán.
    """
    candidates = (
        db.query(models.Candidate).filter(models.Candidate.jd_id == jd.id).all()
    )
    cand_ids = [c.id for c in candidates]

    # Evaluation gắn với JD qua CẢ hai đường (cv_id và jd_id). Gom cả hai để không
    # sót bản ghi lạc khi dữ liệu cũ không nhất quán.
    eval_filter = models.Evaluation.jd_id == jd.id
    if cand_ids:
        eval_filter = eval_filter | models.Evaluation.cv_id.in_(cand_ids)
    eval_ids = [e.id for e in db.query(models.Evaluation.id).filter(eval_filter).all()]

    interview_ids = [
        i.id
        for i in db.query(models.Interview.id)
        .filter(models.Interview.cv_id.in_(cand_ids))
        .all()
    ] if cand_ids else []

    shortlist_ids = [
        s.id
        for s in db.query(models.Shortlist.id)
        .filter(models.Shortlist.jd_id == jd.id)
        .all()
    ]

    def _wipe(model, condition):
        return db.query(model).filter(condition).delete(synchronize_session=False)

    stats = {"candidates": len(cand_ids), "evaluations": len(eval_ids)}

    # --- Lá: phụ thuộc vào interview / evaluation / shortlist ---
    if interview_ids:
        _wipe(models.InterviewQuestion,
              models.InterviewQuestion.interview_id.in_(interview_ids))
        _wipe(models.Interview, models.Interview.id.in_(interview_ids))
    if eval_ids:
        _wipe(models.EvaluationOverride,
              models.EvaluationOverride.evaluation_id.in_(eval_ids))
        # AgentToolLog là nhật ký tool của AI cho chính đánh giá này — xoá đánh giá
        # thì log cũng hết ý nghĩa.
        _wipe(models.AgentToolLog, models.AgentToolLog.evaluation_id.in_(eval_ids))
    if shortlist_ids:
        _wipe(models.ShortlistItem,
              models.ShortlistItem.shortlist_id.in_(shortlist_ids))
        _wipe(models.Shortlist, models.Shortlist.id.in_(shortlist_ids))

    # --- Thân: phụ thuộc vào candidate ---
    if eval_ids:
        _wipe(models.Evaluation, models.Evaluation.id.in_(eval_ids))
    if cand_ids:
        # ShortlistItem có thể trỏ tới ứng viên qua shortlist của JD KHÁC, nên quét
        # thêm một lượt theo cv_id — bỏ sót là dính lỗi khoá ngoại lúc xoá candidate.
        _wipe(models.ShortlistItem, models.ShortlistItem.cv_id.in_(cand_ids))
        _wipe(models.CandidateSkill, models.CandidateSkill.cv_id.in_(cand_ids))
        _wipe(models.CandidateProject,
              models.CandidateProject.candidate_id.in_(cand_ids))

    # --- Gốc ---
    # Lịch sử tải lên trỏ thẳng vào JD, phải xoá trước khi xoá JD.
    stats["uploads"] = _wipe(
        models.UploadBatch, models.UploadBatch.jd_id == jd.id
    )
    stats["files"] = _delete_cv_files(candidates)
    if cand_ids:
        _wipe(models.Candidate, models.Candidate.id.in_(cand_ids))
    db.delete(jd)
    db.commit()
    return stats
