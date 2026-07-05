from sqlalchemy.orm import Session

from app import models


def write_system_log(
    db: Session,
    module: str,
    message: str,
    level: str = "INFO",
    payload: dict | None = None,
) -> None:
    """Ghi 1 dòng vào system_logs (NFR-8: log login & hành động quản trị quan trọng).

    KHÔNG bao giờ để lỗi ghi log làm hỏng nghiệp vụ chính: nuốt mọi exception và
    rollback riêng phần log. Tự commit để log tồn tại độc lập với transaction gọi.
    """
    try:
        db.add(models.SystemLog(level=level, module=module, message=message, payload=payload))
        db.commit()
    except Exception:
        db.rollback()
