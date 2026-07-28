from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CandidateSkillResponse(BaseModel):
    id: UUID
    skill_name: str
    normalized_name: Optional[str] = None

    class Config:
        from_attributes = True


class CandidateProjectResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    github_url: Optional[str] = None
    tech_stack: Optional[list] = None

    class Config:
        from_attributes = True


class EvaluationResponse(BaseModel):
    id: UUID
    score: float
    score_breakdown: dict
    explanation: Optional[str] = None
    evidence: dict
    is_overridden: bool
    evaluated_at: datetime

    class Config:
        from_attributes = True


class CandidateListItem(BaseModel):
    """Dùng cho bảng xếp hạng (leaderboard - UC U004 View Candidate Leaderboard)."""
    id: UUID
    name: Optional[str] = None
    email: Optional[str] = None
    status: str
    score: Optional[float] = None
    skills: list[str] = []          # tên kỹ năng để hiển thị chip trên bảng xếp hạng
    is_overridden: bool = False     # HR đã chỉnh điểm chưa
    error_message: Optional[str] = None   # lý do khi status=FAILED (để HR bấm xem)

    class Config:
        from_attributes = True


class CandidateDetailResponse(BaseModel):
    id: UUID
    jd_id: UUID
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: str
    error_message: Optional[str] = None   # lý do khi status=FAILED
    file_hash: Optional[str] = None
    raw_text: Optional[str] = None   # text CV gốc, để đối chiếu/highlight bằng chứng
    created_at: datetime
    skills: list[CandidateSkillResponse] = []
    projects: list[CandidateProjectResponse] = []
    evaluation: Optional[EvaluationResponse] = None

    class Config:
        from_attributes = True


class UploadResultItem(BaseModel):
    """Kết quả stage 1 file CV trong batch upload ZIP."""
    filename: str
    status: str  # pending | duplicated | failed  (completed được set sau bởi worker)
    candidate_id: Optional[UUID] = None
    score: Optional[float] = None
    error: Optional[str] = None


class UploadBatchResponse(BaseModel):
    jd_id: UUID
    total: int
    completed: int
    processing: int  # số CV đang được worker chấm điểm nền
    failed: int
    duplicated: int
    results: list[UploadResultItem]


class EvaluationOverrideRequest(BaseModel):
    """UC U005 - Override AI Evaluation."""
    new_score: float = Field(..., ge=0, le=100)
    reason: str = Field(..., min_length=1)