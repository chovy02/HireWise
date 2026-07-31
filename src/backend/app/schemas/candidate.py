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


class EvaluationResponse(BaseModel):
    id: UUID
    score: float
    score_breakdown: dict
    explanation: Optional[str] = None
    evidence: dict
    # Phân tích chi tiết (rubric từng trục, đối chiếu yêu cầu JD, rủi ro...).
    # None với các đánh giá chấm từ trước khi có cột này — UI lùi về hiển thị
    # điểm mạnh/yếu từ `evidence`.
    details: Optional[dict] = None
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
    # Thời điểm tải CV lên. Dùng làm CHỐT PHÁ HOÀ khi sắp theo điểm — cả backend và
    # frontend đều cần: hai ứng viên trùng điểm phải luôn ra cùng một thứ tự, và khi
    # HR đổi sang "điểm thấp → cao" thì thứ tự đó phải ĐẢO lại chứ không giữ nguyên.
    created_at: Optional[datetime] = None

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


class UploadHistoryItem(BaseModel):
    """Một lượt tải ZIP đã lưu (GET /jds/{id}/uploads) — dựng lại được sau khi F5."""
    id: UUID
    filename: Optional[str] = None
    total: int = 0
    staged: int = 0
    duplicated: int = 0
    failed: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class EvaluationOverrideRequest(BaseModel):
    """UC U005 - Override AI Evaluation."""
    new_score: float = Field(..., ge=0, le=100)
    reason: str = Field(..., min_length=1)