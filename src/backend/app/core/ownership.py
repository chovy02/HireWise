"""Giới hạn dữ liệu nghiệp vụ theo NGƯỜI TẠO.

Mỗi JD (project) đã có sẵn cột `job_descriptions.created_by` trỏ về users.id, nhưng
TRƯỚC ĐÂY không truy vấn nào dùng tới nó: `GET /jds` trả về mọi JD trong bảng, và mọi
endpoint nhận `jd_id`/`candidate_id`/`shortlist_id` đều nạp theo id trần. Hậu quả là
hai tài khoản HR khác nhau nhìn thấy y hệt danh sách project của nhau, và chỉ cần biết
id là đọc/sửa được dữ liệu của người khác (xem CV gốc, ghi đè điểm, xoá shortlist).

Mọi truy cập tài nguyên nghiệp vụ phải đi qua các hàm dưới đây.

TRẢ 404 CHỨ KHÔNG PHẢI 403 khi tài nguyên thuộc về người khác: 403 xác nhận "id này
có tồn tại", đủ để dò id hợp lệ. Người dùng hợp lệ không phân biệt được hai trường hợp,
còn kẻ dò thì không moi được thông tin gì.

Các router này đều đã chặn `require_role("hr_staff")` nên admin không vào được — không
cần nhánh miễn trừ cho admin ở đây.
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models

JD_NOT_FOUND = "Không tìm thấy vị trí tuyển dụng."
CANDIDATE_NOT_FOUND = "Không tìm thấy ứng viên."
EVALUATION_NOT_FOUND = "Không tìm thấy đánh giá."
SHORTLIST_NOT_FOUND = "Không tìm thấy shortlist."
INTERVIEW_NOT_FOUND = "Không tìm thấy buổi phỏng vấn."
QUESTION_NOT_FOUND = "Không tìm thấy câu hỏi."


def owned_jds(db: Session, user: models.User, include_deleted: bool = False):
    """Query JD đã lọc theo chủ sở hữu. Dùng làm gốc cho mọi truy vấn danh sách.

    MẶC ĐỊNH BỎ QUA JD trong thùng rác. Lọc ở đây thay vì ở từng endpoint là có chủ
    đích: mọi đường vào JD đều đi qua hàm này, nên một JD đã xoá không thể lọt ra ở
    một endpoint nào đó do lập trình viên quên lọc. Chỉ trang thùng rác mới truyền
    include_deleted=True.
    """
    q = db.query(models.JobDescription).filter(
        models.JobDescription.created_by == user.id
    )
    if not include_deleted:
        q = q.filter(models.JobDescription.deleted_at.is_(None))
    return q


def get_owned_jd(
    db: Session, jd_id: UUID, user: models.User, include_deleted: bool = False
) -> models.JobDescription:
    jd = (
        owned_jds(db, user, include_deleted=include_deleted)
        .filter(models.JobDescription.id == jd_id)
        .first()
    )
    if not jd:
        raise HTTPException(status_code=404, detail=JD_NOT_FOUND)
    return jd


def get_owned_candidate(
    db: Session, candidate_id: UUID, user: models.User
) -> models.Candidate:
    """Ứng viên không có chủ sở hữu riêng — thừa hưởng từ JD chứa nó.

    JD đã vào thùng rác thì ứng viên bên trong cũng coi như không tồn tại: dự án đã
    biến mất khỏi giao diện mà link cũ tới ứng viên vẫn mở được thì rất khó hiểu.
    """
    candidate = (
        db.query(models.Candidate)
        .join(models.JobDescription, models.Candidate.jd_id == models.JobDescription.id)
        .filter(
            models.Candidate.id == candidate_id,
            models.JobDescription.created_by == user.id,
            models.JobDescription.deleted_at.is_(None),
        )
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail=CANDIDATE_NOT_FOUND)
    return candidate


def get_owned_evaluation(
    db: Session, evaluation_id: UUID, user: models.User
) -> models.Evaluation:
    evaluation = (
        db.query(models.Evaluation)
        .join(models.JobDescription, models.Evaluation.jd_id == models.JobDescription.id)
        .filter(
            models.Evaluation.id == evaluation_id,
            models.JobDescription.created_by == user.id,
            models.JobDescription.deleted_at.is_(None),
        )
        .first()
    )
    if not evaluation:
        raise HTTPException(status_code=404, detail=EVALUATION_NOT_FOUND)
    return evaluation


def get_owned_interview(
    db: Session, interview_id: UUID, user: models.User
) -> models.Interview:
    interview = (
        db.query(models.Interview)
        .join(models.Candidate, models.Interview.cv_id == models.Candidate.id)
        .join(models.JobDescription, models.Candidate.jd_id == models.JobDescription.id)
        .filter(
            models.Interview.id == interview_id,
            models.JobDescription.created_by == user.id,
            models.JobDescription.deleted_at.is_(None),
        )
        .first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail=INTERVIEW_NOT_FOUND)
    return interview


def get_owned_question(
    db: Session, question_id: UUID, user: models.User
) -> models.InterviewQuestion:
    question = (
        db.query(models.InterviewQuestion)
        .join(
            models.Interview,
            models.InterviewQuestion.interview_id == models.Interview.id,
        )
        .join(models.Candidate, models.Interview.cv_id == models.Candidate.id)
        .join(models.JobDescription, models.Candidate.jd_id == models.JobDescription.id)
        .filter(
            models.InterviewQuestion.id == question_id,
            models.JobDescription.created_by == user.id,
            models.JobDescription.deleted_at.is_(None),
        )
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail=QUESTION_NOT_FOUND)
    return question


def get_owned_shortlist(
    db: Session, shortlist_id: UUID, user: models.User
) -> models.Shortlist:
    """Chốt theo chủ của JD (không theo Shortlist.created_by) để mọi thứ trong một
    project luôn cùng một ranh giới sở hữu."""
    shortlist = (
        db.query(models.Shortlist)
        .join(models.JobDescription, models.Shortlist.jd_id == models.JobDescription.id)
        .filter(
            models.Shortlist.id == shortlist_id,
            models.JobDescription.created_by == user.id,
            models.JobDescription.deleted_at.is_(None),
        )
        .first()
    )
    if not shortlist:
        raise HTTPException(status_code=404, detail=SHORTLIST_NOT_FOUND)
    return shortlist
