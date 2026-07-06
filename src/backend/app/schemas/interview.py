from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class GenerateInterviewRequest(BaseModel):
    aspect: Optional[str] = Field(None, description="Trọng tâm HR muốn xoáy sâu (tùy chọn)")

class EvaluateAnswerRequest(BaseModel):
    answer_text: str = Field(..., description="Tóm tắt câu trả lời của ứng viên do HR gõ lại")

class InterviewQuestionResponse(BaseModel):
    id: UUID
    question: str
    expected_answer: Optional[str]
    category: Optional[str]
    answer_text: Optional[str]
    ai_evaluation: Optional[str]
    score: Optional[float]
    is_ai_generated: bool
    order_index: int

    class Config:
        from_attributes = True

class InterviewResponse(BaseModel):
    id: UUID
    cv_id: UUID
    status: str
    scheduled_at: Optional[datetime]
    questions: List[InterviewQuestionResponse] = []

    class Config:
        from_attributes = True

class EvaluationResultResponse(BaseModel):
    """Kết quả trả về khi HR chấm điểm 1 câu trả lời"""
    evaluated_question: InterviewQuestionResponse
    follow_up_question: Optional[InterviewQuestionResponse] = None