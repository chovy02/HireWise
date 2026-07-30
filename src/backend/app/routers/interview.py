from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.ownership import (
    get_owned_candidate,
    get_owned_interview,
    get_owned_jd,
    get_owned_question,
)
from app.services.ai_agent.evaluation_view import weakness_context
from app.services.ai_agent.interviewer import generate_interview_questions_ai, evaluate_interview_answer_ai, summarize_interview_ai

router = APIRouter(
    prefix="/interviews",
    tags=["Interviews"],
    dependencies=[Depends(require_role("hr_staff"))],
)

@router.get("/candidate/{candidate_id}", response_model=schemas.InterviewResponse)
def get_candidate_interview(
    candidate_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lấy buổi phỏng vấn hiện có của ứng viên (nếu đã tạo)."""
    candidate = get_owned_candidate(db, candidate_id, current_user)
    interview = db.query(models.Interview).filter(models.Interview.cv_id == candidate.id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Ứng viên chưa có buổi phỏng vấn.")
    return interview

@router.post("/candidate/{candidate_id}/generate", response_model=schemas.InterviewResponse)
def generate_interview(
    candidate_id: UUID,
    payload: schemas.GenerateInterviewRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Tạo buổi phỏng vấn mới và AI tự động sinh từ 5-10 câu hỏi tùy CV."""
    candidate = get_owned_candidate(db, candidate_id, current_user)
    if not candidate.evaluation:
        raise HTTPException(status_code=400, detail="Ứng viên không tồn tại hoặc chưa được đánh giá AI.")

    jd = get_owned_jd(db, candidate.jd_id, current_user)

    # Xóa lịch sử phỏng vấn cũ nếu HR muốn tạo lại
    existing_interview = db.query(models.Interview).filter(models.Interview.cv_id == candidate.id).first()
    if existing_interview:
        db.delete(existing_interview)
        db.commit()

    # Đóng gói ngữ cảnh gửi cho AI. Phần "điểm yếu" lấy từ chính lượt chấm điểm
    # (từng thiếu hụt + chỗ đánh dấu cần kiểm chứng) thay vì đoạn tóm tắt chung chung,
    # để câu hỏi sinh ra bám vào chỗ còn nghi vấn của ứng viên này.
    candidate_context = {
        "full_cv": candidate.raw_text,
        "ai_identified_weaknesses": weakness_context(candidate.evaluation)
    }

    ai_questions = generate_interview_questions_ai(jd.requirements, candidate_context, payload.aspect)
    
    if not ai_questions:
        raise HTTPException(status_code=502, detail="Lỗi khi AI sinh câu hỏi phỏng vấn.")

    # Lưu vào Database
    interview = models.Interview(cv_id=candidate.id, status="pending")
    db.add(interview)
    db.commit()
    db.refresh(interview)

    for idx, q in enumerate(ai_questions):
        if not isinstance(q, dict):
            continue
        db_question = models.InterviewQuestion(
            interview_id=interview.id,
            question=q.get("question", "Câu hỏi chưa xác định"),
            expected_answer=q.get("expected_answer", ""),
            category=q.get("category", "Chung"),
            order_index=idx * 10 # Bước nhảy 10 để chèn tối đa 9 câu hỏi phụ vào giữa
        )
        db.add(db_question)
    
    db.commit()
    db.refresh(interview)
    return interview

@router.post("/question/{question_id}/evaluate", response_model=schemas.EvaluationResultResponse)
def evaluate_answer(
    question_id: UUID,
    payload: schemas.EvaluateAnswerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """HR nhập câu trả lời, AI đánh giá. Chỉ sinh follow-up nếu câu trả lời chưa tốt và chưa quá 3 câu."""
    question = get_owned_question(db, question_id, current_user)

    interview = db.query(models.Interview).filter(models.Interview.id == question.interview_id).first()
    if interview and interview.status == "pending":
        interview.status = "in_progress"
        db.commit()

    # 1. Xác định mốc câu hỏi gốc (Ví dụ order_index là 20, 21, 22 -> root_index sẽ là 20)
    root_index = (question.order_index // 10) * 10

    # 2. Tìm các câu hỏi phụ đã tạo trong cùng nhóm câu gốc này (từ root_index + 1 đến root_index + 9)
    existing_follow_ups = db.query(models.InterviewQuestion).filter(
        models.InterviewQuestion.interview_id == question.interview_id,
        models.InterviewQuestion.order_index > root_index,
        models.InterviewQuestion.order_index < root_index + 10
    ).all()

    # 3. Kiểm tra giới hạn: Nếu đã có từ 3 câu hỏi phụ trở lên -> Khóa, không cho AI sinh thêm
    can_follow_up = len(existing_follow_ups) < 3

    # Gọi AI đánh giá (Truyền cờ can_follow_up để AI biết đường ép chuỗi rỗng nếu đã đầy)
    ai_eval = evaluate_interview_answer_ai(
        question=question.question,
        expected=question.expected_answer,
        answer=payload.answer_text,
        allow_follow_up=can_follow_up
    )

    # Cập nhật kết quả cho câu hỏi hiện tại
    question.answer_text = payload.answer_text
    question.ai_evaluation = ai_eval.get("evaluation", "")
    question.score = ai_eval.get("score", 0)
    db.commit()
    db.refresh(question)

    follow_up = None
    # Nếu AI đề xuất câu hỏi đào sâu (khi trả lời chưa tốt) VÀ chưa vượt giới hạn 3 câu
    if can_follow_up and ai_eval.get("follow_up_question"):
        follow_up_text = ai_eval.get("follow_up_question").strip()
        if follow_up_text:
            # Đảm bảo order_index tuần tự không bị trùng (root+1, root+2, root+3)
            next_order_idx = (max([q.order_index for q in existing_follow_ups]) + 1) if existing_follow_ups else (root_index + 1)
            
            follow_up = models.InterviewQuestion(
                interview_id=question.interview_id,
                question=follow_up_text,
                expected_answer="Đào sâu năng lực xử lý vấn đề từ câu trả lời trước.",
                category="Đào sâu (Follow-up)",
                order_index=next_order_idx,
                is_ai_generated=True
            )
            db.add(follow_up)
            db.commit()
            db.refresh(follow_up)

    return schemas.EvaluationResultResponse(
        evaluated_question=question,
        follow_up_question=follow_up
    )

@router.patch("/{interview_id}/complete")
def complete_interview(
    interview_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """HR bấm nút kết thúc. Hệ thống gom toàn bộ dữ liệu cho AI tổng kết."""
    interview = get_owned_interview(db, interview_id, current_user)

    if interview.status == "completed":
        raise HTTPException(status_code=400, detail="Buổi phỏng vấn này đã được đóng lại trước đó.")

    # Lấy tất cả các câu hỏi đã có câu trả lời
    answered_questions = [q for q in interview.questions if q.answer_text]
    
    if not answered_questions:
        interview.status = "completed"
        interview.feedback_summary = "Buổi phỏng vấn bị hủy hoặc ứng viên không trả lời câu hỏi nào."
        db.commit()
        return {"message": "Đã kết thúc buổi phỏng vấn (không có dữ liệu)."}

    # Gom dữ liệu thành biên bản văn bản để gửi cho AI
    transcript_lines = []
    for q in answered_questions:
        transcript_lines.append(f"Hỏi: {q.question}")
        transcript_lines.append(f"Đáp: {q.answer_text}")
        transcript_lines.append(f"AI nhận xét tạm: {q.ai_evaluation}\n")
    
    transcript = "\n".join(transcript_lines)
    
    # Gọi AI sinh tổng kết
    summary = summarize_interview_ai(transcript)
    
    # Cập nhật bảng interviews
    interview.status = "completed"
    interview.feedback_summary = summary
    db.commit()
    db.refresh(interview)
    
    return {
        "id": interview.id,
        "status": interview.status,
        "feedback_summary": interview.feedback_summary
    }