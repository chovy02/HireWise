from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app import models, schemas
from app.core.dependencies import get_current_user, require_role
from app.database import get_db
from app.utils import security
from app.services.logging import write_system_log

# Toàn bộ router này chỉ dành cho Admin (RBAC - FR-1: quản lý tài khoản người dùng).
router = APIRouter(
    prefix="/users",
    tags=["Account Management (Admin)"],
    dependencies=[Depends(require_role("admin"))],
)


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
        if user.id == current_user.id and not payload.is_active:
            raise HTTPException(status_code=400, detail="Không thể tự khóa tài khoản của chính mình.")
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)

    write_system_log(
        db, module="users",
        message=f"Admin {current_user.email} cập nhật tài khoản {user.email} (role={user.role}, active={user.is_active})",
    )
    return user


@router.patch("/{user_id}/deactivate", response_model=schemas.UserResponse)
def deactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Không thể tự khóa tài khoản của chính mình.")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")

    user.is_active = False
    db.commit()
    db.refresh(user)

    write_system_log(
        db, module="users", level="WARNING",
        message=f"Admin {current_user.email} khóa tài khoản {user.email}",
    )
    return user
