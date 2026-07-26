import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.core.dependencies import get_current_user
from app.database import get_db

# Router thông báo dành cho MỌI người dùng đã đăng nhập (HR + admin).
# Admin phát thông báo qua /admin/notifications; người dùng đọc qua router này.
router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationResponse(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    type: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[NotificationResponse])
def list_active_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Danh sách thông báo đang bật (is_active=True) để hiển thị ở chuông thông báo."""
    return (
        db.query(models.Notification)
        .filter(models.Notification.is_active == True)  # noqa: E712
        .order_by(models.Notification.created_at.desc())
        .all()
    )
