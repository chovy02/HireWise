from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID

class CompareRequest(BaseModel):
    candidate_ids: list[UUID] = Field(
        ..., 
        min_length=2, 
        description="Danh sách ID của ít nhất 2 ứng viên cần so sánh"
    )
    aspect: Optional[str] = Field(
        None, 
        description="Tiêu chí so sánh (ví dụ: 'Ai làm backend tốt hơn?', 'Kỹ năng lãnh đạo'). Nếu bỏ trống sẽ so sánh toàn diện."
    )

class CompareResponse(BaseModel):
    """Kết quả so sánh trả về cho giao diện."""
    recommendation: str = Field(..., description="Đề xuất trực diện ứng viên phù hợp nhất")
    detailed_comparison: str = Field(..., description="Bài phân tích so sánh chi tiết dạng Markdown")