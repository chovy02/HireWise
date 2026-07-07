from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user, require_role
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
    interview = db.query(models.Interview).filter(models.Interview.cv_id == candidate_id).first()
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
    """Tạo buổi phỏng vấn mới và AI tự động sinh câu hỏi."""
    candidate = db.query(models.Candidate).filter(models.Candidate.id == candidate_id).first()
    if not candidate or not candidate.evaluation:
        raise HTTPException(status_code=400, detail="Ứng viên không tồn tại hoặc chưa được đánh giá AI.")

    jd = db.query(models.JobDescription).filter(models.JobDescription.id == candidate.jd_id).first()

    # Xóa lịch sử phỏng vấn cũ nếu HR muốn tạo lại
    existing_interview = db.query(models.Interview).filter(models.Interview.cv_id == candidate_id).first()
    if existing_interview:
        db.delete(existing_interview)
        db.commit()

    # Đóng gói ngữ cảnh gửi cho AI
    candidate_context = {
        "full_cv": candidate.raw_text,
        "ai_identified_weaknesses": candidate.evaluation.explanation
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
            order_index=idx * 10 # Bước nhảy 10 để dễ chèn câu hỏi phụ vào giữa sau này
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
    """HR nhập câu trả lời của ứng viên, AI đánh giá và sinh câu hỏi đào sâu nếu cần."""
    question = db.query(models.InterviewQuestion).filter(models.InterviewQuestion.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi.")
    
    interview = db.query(models.Interview).filter(models.Interview.id == question.interview_id).first()
    if interview and interview.status == "pending":
        interview.status = "in_progress"
        db.commit()

    # Gọi AI đánh giá
    ai_eval = evaluate_interview_answer_ai(
        question=question.question,
        expected=question.expected_answer,
        answer=payload.answer_text
    )

    # Cập nhật kết quả cho câu hỏi hiện tại
    question.answer_text = payload.answer_text
    question.ai_evaluation = ai_eval.get("evaluation", "")
    question.score = ai_eval.get("score", 0)
    db.commit()
    db.refresh(question)

    follow_up = None
    # Nếu AI đề xuất câu hỏi đào sâu
    if ai_eval.get("follow_up_question"):
        follow_up_text = ai_eval.get("follow_up_question")
        follow_up = models.InterviewQuestion(
            interview_id=question.interview_id,
            question=follow_up_text,
            expected_answer="Đào sâu năng lực xử lý vấn đề từ câu trả lời trước.",
            category="Đào sâu (Follow-up)",
            order_index=question.order_index + 1, # Chèn ngay bên dưới câu hiện tại
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
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi phỏng vấn.")
        
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