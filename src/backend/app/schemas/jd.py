from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class JDCreate(BaseModel):
    """HR nhập yêu cầu tuyển dụng bằng ngôn ngữ tự nhiên (UC U001 - Initiate JD)."""
    raw_text: str = Field(..., min_length=10, description="Mô tả tuyển dụng bằng ngôn ngữ tự nhiên")


class JDResponse(BaseModel):
    id: UUID
    title: str
    raw_text: str
    jd_markdown: str
    requirements: dict
    status: str
    created_by: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class JDListItem(BaseModel):
    """Bản rút gọn cho danh sách JD."""
    id: UUID
    title: str
    status: str
    created_at: datetime
    candidate_count: int = 0   # số ứng viên thật của JD (để hiển thị trên dashboard)

    class Config:
        from_attributes = True