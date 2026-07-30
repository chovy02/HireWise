from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

# "text" = nội dung chữ thường (mọi mẫu lưu trước khi có trình soạn thảo).
# "html" = nội dung có định dạng (in đậm, danh sách, ảnh chèn giữa bài).
BodyFormat = Literal["text", "html"]


class EmailAttachmentResponse(BaseModel):
    """Một file HR đã gắn vào mẫu mail."""
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    # True = ảnh nằm giữa nội dung (HTML trỏ tới bằng src="cid:{content_id}").
    # False = file đính kèm bình thường, hiện ở cuối mail.
    is_inline: bool
    content_id: Optional[str] = None

    class Config:
        from_attributes = True


class EmailTemplateUpsert(BaseModel):
    subject: str = Field(..., example="[HireWise] Chúc mừng! Thư mời phỏng vấn vị trí {jd_title}")
    body_template: str = Field(..., example="Chào {candidate_name},\n\nChúc mừng bạn đã qua vòng CV vị trí {jd_title}.\n\nTrân trọng,\n{hr_name}")
    body_format: BodyFormat = "text"
    is_active: bool = True


class EmailTemplateResponse(EmailTemplateUpsert):
    id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    template_type: str
    updated_at: Optional[datetime] = None
    # Mẫu mặc định (chưa lưu dưới DB) không thể có file nào -> mảng rỗng.
    attachments: list[EmailAttachmentResponse] = []

    class Config:
        from_attributes = True
