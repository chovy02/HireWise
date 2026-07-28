from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Optional

class EmailTemplateUpsert(BaseModel):
    subject: str = Field(..., example="[HireWise] Chúc mừng! Thư mời phỏng vấn vị trí {jd_title}")
    body_template: str = Field(..., example="Chào {candidate_name},\n\nChúc mừng bạn đã qua vòng CV vị trí {jd_title}.\n\nTrân trọng,\n{hr_name}")
    is_active: bool = True

class EmailTemplateResponse(EmailTemplateUpsert):
    id: Optional[UUID] = None       
    user_id: Optional[UUID] = None
    template_type: str
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True