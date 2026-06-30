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

    class Config:
        from_attributes = True


class CandidateDetailResponse(BaseModel):
    id: UUID
    jd_id: UUID
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: str
    file_hash: Optional[str] = None
    created_at: datetime
    skills: list[CandidateSkillResponse] = []
    projects: list[CandidateProjectResponse] = []
    evaluation: Optional[EvaluationResponse] = None

    class Config:
        from_attributes = True


class UploadResultItem(BaseModel):
    """Kết quả xử lý 1 file CV trong batch upload ZIP."""
    filename: str
    status: str  # completed | failed | duplicated
    candidate_id: Optional[UUID] = None
    score: Optional[float] = None
    error: Optional[str] = None


class UploadBatchResponse(BaseModel):
    jd_id: UUID
    total: int
    completed: int
    failed: int
    duplicated: int
    results: list[UploadResultItem]


class EvaluationOverrideRequest(BaseModel):
    """UC U005 - Override AI Evaluation."""
    new_score: float = Field(..., ge=0, le=100)
    reason: str = Field(..., min_length=1)