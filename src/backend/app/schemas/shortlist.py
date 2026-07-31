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
    # Trạng thái buổi phỏng vấn: pending/in_progress/completed, None nếu chưa tạo.
    # Frontend dựa vào đây để biết ứng viên nào có tóm tắt phỏng vấn để mở xem.
    interview_status: Optional[str] = None
    # Thời điểm CV được tải lên. Dùng làm CHỐT PHÁ HOÀ khi sắp theo điểm: hai ứng viên
    # cùng điểm phải luôn ra cùng một thứ tự ở mọi bảng (leaderboard và shortlist), nếu
    # không thì cùng một cặp trùng điểm lại hiện thứ tự khác nhau giữa hai tab.
    created_at: Optional[datetime] = None


class ShortlistItemResponse(BaseModel):
    id: UUID                        # id của ShortlistItem (dùng để PATCH/DELETE)
    candidate_status: ShortlistItemStatus
    added_at: datetime
    candidate: ShortlistCandidate
    # Dấu vết lần gửi THÀNH CÔNG gần nhất (POST /shortlists/{id}/send-notifications).
    # Frontend cần cả hai để biết ứng viên nào ĐÃ gửi, và gửi ở trạng thái nào —
    # backend chỉ gửi lại khi notified_status khác candidate_status hiện tại, nên
    # thiếu hai field này thì UI không thể hiện đúng "còn bao nhiêu người cần gửi".
    notified_at: Optional[datetime] = None
    notified_status: Optional[str] = None
    # Trạng thái của LƯỢT GỬI hiện tại, kể cả khi thất bại:
    #   None -> chưa gửi lần nào | "sending" -> đang trong hàng đợi nền
    #   "sent" -> thành công     | "failed" -> thất bại, xem notify_error_code
    # Không có nhóm field này thì UI chỉ nói được "đã gửi/chưa gửi", còn mail lỗi lại
    # hiện y như chưa tới lượt gửi.
    notify_state: Optional[str] = None
    notify_error_code: Optional[str] = None
    notify_error: Optional[str] = None
    notify_attempts: int = 0
    notify_last_attempt_at: Optional[datetime] = None


class ShortlistNotifyResponse(BaseModel):
    """Kết quả xếp hàng gửi mail hàng loạt.

    `total_queued` là số mail ĐƯỢC XẾP HÀNG, chưa phải số gửi thành công (việc gửi chạy
    nền). Các con số `skipped_*` nói rõ ai bị bỏ qua và vì sao — trước đây ứng viên
    thiếu email bị loại trong im lặng, nên tổng số trên UI không bao giờ khớp thực tế.
    """
    message: str
    total_queued: int
    skipped_no_email: int = 0
    skipped_invalid_email: int = 0
    skipped_already_sent: int = 0
    skipped_not_decided: int = 0
    skipped_in_flight: int = 0


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
