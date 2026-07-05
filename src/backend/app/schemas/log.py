from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SystemLogResponse(BaseModel):
    id: UUID
    level: str          # INFO / WARNING / ERROR / CRITICAL
    module: str         # auth, users, ...
    message: str
    payload: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True
