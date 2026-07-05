from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# Trạng thái ứng viên trong shortlist (khớp cột ShortlistItem.candidate_status).
ShortlistItemStatus = Literal["pending", "accepted", "rejected"]


class ShortlistCreate(BaseModel):
    """HR tạo một danh sách rút gọn (shortlist) cho một vị trí tuyển dụng."""
    name: str = Field(..., min_length=1, max_length=255, description="Tên shortlist")


class ShortlistItemAdd(BaseModel):
    """Thêm 1 ứng viên vào shortlist."""
    candidate_id: UUID


class ShortlistItemStatusUpdate(BaseModel):
    """Cập nhật quyết định của HR cho ứng viên trong shortlist."""
    candidate_status: ShortlistItemStatus


class ShortlistCandidate(BaseModel):
    """Thông tin ứng viên rút gọn hiển thị trong shortlist (kèm điểm AI)."""
    id: UUID
    name: Optional[str] = None
    email: Optional[str] = None
    status: str                     # trạng thái xử lý CV: PENDING/COMPLETED/FAILED
    score: Optional[float] = None   # điểm phù hợp (None nếu chưa chấm xong)
    skills: list[str] = []
    is_overridden: bool = False


class ShortlistItemResponse(BaseModel):
    id: UUID                        # id của ShortlistItem (dùng để PATCH/DELETE)
    candidate_status: ShortlistItemStatus
    added_at: datetime
    candidate: ShortlistCandidate


class ShortlistListItem(BaseModel):
    """Bản rút gọn cho danh sách shortlist của một JD."""
    id: UUID
    jd_id: UUID
    name: str
    item_count: int
    created_at: datetime


class ShortlistResponse(BaseModel):
    id: UUID
    jd_id: UUID
    name: str
    created_by: UUID
    created_at: datetime
    items: list[ShortlistItemResponse] = []
