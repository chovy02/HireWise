from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.dependencies import require_role
from app.database import get_db

# Khu vực giám sát chỉ dành cho Admin (RBAC): xem log hệ thống, log hành động quản trị.
router = APIRouter(
    prefix="/admin",
    tags=["Admin Monitoring"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("/system-logs", response_model=list[schemas.SystemLogResponse])
def list_system_logs(
    limit: int = 200,
    db: Session = Depends(get_db),
):
    """NFR-8: xem log hoạt động đăng nhập + hành động quản trị (mới nhất trước)."""
    return (
        db.query(models.SystemLog)
        .order_by(models.SystemLog.created_at.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )
