from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app import models, schemas
from app.core.dependencies import get_current_user, require_role
from app.database import get_db
from app.utils import security
from app.services.logging import write_system_log, write_audit_log, snapshot_diff

# Toàn bộ router này chỉ dành cho Admin (RBAC - FR-1: quản lý tài khoản người dùng).
router = APIRouter(
    prefix="/users",
    tags=["Account Management (Admin)"],
    dependencies=[Depends(require_role("admin"))],
)


def _user_snapshot(u: models.User) -> dict:
    """Ảnh chụp các trường CÓ THỂ kiểm toán của user.

    Cố ý bỏ password_hash: nhật ký kiểm toán do admin đọc được, không được chứa
    bất kỳ dấu vết mật khẩu nào. Việc đổi mật khẩu ghi riêng bằng nhãn "(đã đổi)".
    """
    return {
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "is_active": u.is_active,
        "is_banned": u.is_banned,
    }


@router.get("", response_model=list[schemas.UserResponse])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


@router.get("/{user_id}", response_model=schemas.UserResponse)
def get_user(user_id: UUID, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    return user


@router.post("", status_code=status.HTTP_201_CREATED, response_model=schemas.UserResponse)
def create_user(
    payload: schemas.UserCreateByAdmin,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email này đã được đăng ký.")

    new_user = models.User(
        name=payload.username,
        email=payload.email,
        password_hash=security.get_password_hash(payload.password),
        role=payload.role.value,
        is_active=True,  # Admin tạo trực tiếp nên không cần luồng xác minh email.
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    write_system_log(
        db, module="users",
        message=f"Admin {current_user.email} tạo tài khoản {new_user.email} (role={new_user.role})",
    )
    write_audit_log(
        db, user_id=current_user.id, action="CREATE_USER", entity_type="user",
        entity_id=new_user.id,
        old_data=None,  # tạo mới -> không có trạng thái "trước"
        new_data=_user_snapshot(new_user),
    )
    return new_user


@router.put("/{user_id}", response_model=schemas.UserResponse)
def update_user(
    user_id: UUID,
    payload: schemas.UserUpdateByAdmin,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")

    # Chụp trạng thái TRƯỚC khi gán, nếu không SQLAlchemy đã đổi object tại chỗ và
    # diff sẽ luôn rỗng.
    before = _user_snapshot(user)

    if payload.email and payload.email != user.email:
        if db.query(models.User).filter(models.User.email == payload.email).first():
            raise HTTPException(status_code=400, detail="Email này đã được sử dụng.")
        user.email = payload.email

    if payload.username is not None:
        user.name = payload.username
    if payload.role is not None:
        user.role = payload.role.value
    if payload.password is not None:
        user.password_hash = security.get_password_hash(payload.password)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_banned is not None:
        if user.id == current_user.id and payload.is_banned:
            raise HTTPException(status_code=400, detail="Không thể tự khóa tài khoản của chính mình.")
        user.is_banned = payload.is_banned

    db.commit()
    db.refresh(user)

    write_system_log(
        db, module="users",
        message=f"Admin {current_user.email} cập nhật tài khoản {user.email} (role={user.role}, active={user.is_active}, banned={user.is_banned})",
    )

    old_data, new_data = snapshot_diff(before, _user_snapshot(user))
    if payload.password is not None:
        # Chỉ ghi NHẬN đã đổi mật khẩu, tuyệt đối không ghi giá trị/hash.
        old_data["password"] = "•••"
        new_data["password"] = "••• (đã đổi)"
    if old_data or new_data:  # không ghi log rỗng khi PUT không đổi gì
        write_audit_log(
            db, user_id=current_user.id, action="UPDATE_USER", entity_type="user",
            entity_id=user.id, old_data=old_data, new_data=new_data,
        )
    return user


@router.patch("/{user_id}/deactivate", response_model=schemas.UserResponse)
def deactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Khóa tài khoản (ban). Đặt is_banned=True, KHÔNG đụng tới is_active (xác minh email)."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Không thể tự khóa tài khoản của chính mình.")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")

    was_banned = user.is_banned
    user.is_banned = True
    db.commit()
    db.refresh(user)

    write_system_log(
        db, module="users", level="WARNING",
        message=f"Admin {current_user.email} khóa tài khoản {user.email}",
    )
    write_audit_log(
        db, user_id=current_user.id, action="BAN_USER", entity_type="user",
        entity_id=user.id,
        old_data={"is_banned": was_banned, "email": user.email},
        new_data={"is_banned": True, "email": user.email},
    )
    return user
