import os
from sqlalchemy.orm import Session

from app import models
from app.utils import security


def ensure_default_admin(db: Session) -> None:
    """Tạo tài khoản Admin đầu tiên từ biến môi trường nếu hệ thống chưa có Admin nào.

    Đây là cách duy nhất để "phá vòng trứng-gà": mọi endpoint quản lý tài khoản đều
    yêu cầu role=admin, nên cần một admin gốc tồn tại sẵn trước khi có thể tạo thêm
    admin/HR khác qua API. Nếu không cấu hình DEFAULT_ADMIN_EMAIL/PASSWORD, bỏ qua.
    """
    if db.query(models.User).filter(models.User.role == "admin").first():
        return

    email = os.getenv("DEFAULT_ADMIN_EMAIL")
    password = os.getenv("DEFAULT_ADMIN_PASSWORD")
    if not email or not password:
        return

    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        existing.role = "admin"
        existing.is_active = True
    else:
        db.add(models.User(
            name="System Administrator",
            email=email,
            password_hash=security.get_password_hash(password),
            role="admin",
            is_active=True,
        ))
    db.commit()
