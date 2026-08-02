from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
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
from app.services.ai_agent.interviewer import (
    eval_failed,
    evaluate_interview_answer_ai,
    generate_interview_questions_ai,
    summarize_interview_ai,
)

router = APIRouter(
    prefix="/interviews",
    tags=["Interviews"],
    dependencies=[Depends(require_role("hr_staff"))],
)

# Nhãn phân loại mặc định cho câu hỏi HR tự gõ. Không được chứa chữ "follow" vì
# frontend nhận diện câu đào sâu bằng cách soi category (utils/interviewQuestions.js).
MANUAL_CATEGORY = "HR tự soạn"

# Câu hỏi chính cách nhau 10 đơn vị; 9 khe ở giữa dành cho câu đào sâu.
ORDER_STEP = 10


def _next_root_index(db: Session, interview_id: UUID) -> int:
    """Khe order_index cho câu hỏi chính tiếp theo (cuối danh sách)."""
    last = (
        db.query(func.max(models.InterviewQuestion.order_index))
        .filter(models.InterviewQuestion.interview_id == interview_id)
        .scalar()
    )
    if last is None:
        return 0
    return (last // ORDER_STEP + 1) * ORDER_STEP

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

    # Tạo lại bộ câu hỏi: chỉ thay phần AI, GIỮ NGUYÊN câu HR tự soạn (kèm câu trả lời
    # đã chấm của chúng). Trước đây cả buổi phỏng vấn bị xoá trắng, nghĩa là mỗi lần HR
    # bấm "Tạo lại" là mất sạch những câu mình gõ tay — không có cách nào lấy lại.
    interview = db.query(models.Interview).filter(models.Interview.cv_id == candidate.id).first()
    kept_questions: list[models.InterviewQuestion] = []
    if interview:
        for q in list(interview.questions):
            if q.is_ai_generated:
                db.delete(q)  # gồm cả câu đào sâu AI từng sinh ra
            else:
                kept_questions.append(q)
        # Tổng kết cũ nói về bộ câu hỏi vừa bị thay -> không còn đúng nữa.
        interview.feedback_summary = None
        interview.status = "in_progress" if any(q.answer_text for q in kept_questions) else "pending"
    else:
        interview = models.Interview(cv_id=candidate.id, status="pending")
        db.add(interview)
    db.commit()
    db.refresh(interview)

    next_index = 0
    for q in ai_questions:
        if not isinstance(q, dict):
            continue
        db_question = models.InterviewQuestion(
            interview_id=interview.id,
            question=q.get("question", "Câu hỏi chưa xác định"),
            expected_answer=q.get("expected_answer", ""),
            category=q.get("category", "Chung"),
            order_index=next_index # Bước nhảy 10 để chèn tối đa 9 câu hỏi phụ vào giữa
        )
        db.add(db_question)
        next_index += ORDER_STEP

    # Câu HR tự soạn xuống cuối bộ mới, giữ đúng thứ tự tương đối cũ giữa chúng.
    for q in sorted(kept_questions, key=lambda x: x.order_index):
        q.order_index = next_index
        next_index += ORDER_STEP

    db.commit()
    db.refresh(interview)
    return interview


@router.post(
    "/candidate/{candidate_id}/questions",
    response_model=schemas.InterviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_manual_question(
    candidate_id: UUID,
    payload: schemas.ManualQuestionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """HR tự thêm một câu hỏi vào cuối bộ câu hỏi.

    Câu này đi cùng đường ống với câu AI sinh: vẫn nhận câu trả lời, vẫn được
    `/question/{id}/evaluate` chấm điểm và sinh câu đào sâu, vẫn vào biên bản lúc tổng kết.

    Tự tạo buổi phỏng vấn nếu ứng viên chưa có — nhờ vậy HR muốn phỏng vấn thuần thủ công
    (không cần AI sinh câu, không cần CV đã chấm) thì vẫn bắt đầu được từ đây.
    """
    candidate = get_owned_candidate(db, candidate_id, current_user)

    interview = db.query(models.Interview).filter(models.Interview.cv_id == candidate.id).first()
    if not interview:
        interview = models.Interview(cv_id=candidate.id, status="pending")
        db.add(interview)
        db.commit()
        db.refresh(interview)

    if interview.status == "completed":
        raise HTTPException(
            status_code=400,
            detail="Buổi phỏng vấn đã kết thúc — không thêm được câu hỏi mới.",
        )

    question_text = payload.question.strip()
    if not question_text:
        raise HTTPException(status_code=400, detail="Nội dung câu hỏi không được để trống.")

    expected = (payload.expected_answer or "").strip()

    db.add(
        models.InterviewQuestion(
            interview_id=interview.id,
            question=question_text,
            expected_answer=expected or None,
            category=MANUAL_CATEGORY,
            order_index=_next_root_index(db, interview.id),
            is_ai_generated=False,
        )
    )
    db.commit()
    db.refresh(interview)
    return interview


@router.delete("/question/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_manual_question(
    question_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Xoá một câu hỏi HR tự soạn (gõ sai, hỏi trùng…).

    Không cho xoá câu AI sinh: bộ câu hỏi AI là một chỉnh thể bám theo CV/JD, muốn đổi
    thì bấm "Tạo lại". Xoá câu chính thì xoá luôn các câu đào sâu treo dưới nó, nếu không
    chúng sẽ mồ côi và bị đánh số nhầm vào câu hỏi phía trên.
    """
    question = get_owned_question(db, question_id, current_user)

    if question.is_ai_generated:
        raise HTTPException(
            status_code=400,
            detail="Chỉ xoá được câu hỏi do HR tự soạn. Muốn đổi bộ câu hỏi AI thì bấm Tạo lại.",
        )

    interview = db.query(models.Interview).filter(models.Interview.id == question.interview_id).first()
    if interview and interview.status == "completed":
        raise HTTPException(
            status_code=400,
            detail="Buổi phỏng vấn đã kết thúc — không xoá được câu hỏi.",
        )

    root_index = (question.order_index // ORDER_STEP) * ORDER_STEP
    if question.order_index == root_index:
        follow_ups = db.query(models.InterviewQuestion).filter(
            models.InterviewQuestion.interview_id == question.interview_id,
            models.InterviewQuestion.order_index > root_index,
            models.InterviewQuestion.order_index < root_index + ORDER_STEP,
        ).all()
        for f in follow_ups:
            db.delete(f)

    db.delete(question)
    db.commit()
    return None

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

    # AI HỎNG THÌ KHÔNG GHI GÌ CẢ.
    #
    # `evaluate_interview_answer_ai` nuốt mọi lỗi và trả về một bản giữ chỗ 0 điểm.
    # Lưu nó xuống là biến "chưa chấm được" thành "bị 0 điểm" — mà 0 điểm chính là con
    # số HR dùng để loại người, và về sau không ai phân biệt lại được. Thà báo lỗi để
    # HR bấm chấm lại: câu trả lời họ vừa gõ vẫn còn nguyên trên màn hình.
    if eval_failed(ai_eval):
        raise HTTPException(
            status_code=503,
            detail=(
                "AI đang không chấm được câu trả lời (thường do hết hạn mức trong ngày) "
                "nên chưa lưu gì cả. Bạn thử lại sau ít phút nhé."
            ),
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