from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from jose import jwt, JWTError
import os

from app import models, schemas
from app.core.dependencies import get_current_user
from app.database import get_db
from app.utils import security
from app.services.email import send_verification_email
from app.services.logging import write_system_log

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # 1. Kiểm tra email đã tồn tại chưa
    user_exist = db.query(models.User).filter(models.User.email == user.email).first()
    
    hashed_pwd = security.get_password_hash(user.password)

    if user_exist:
        if user_exist.is_active:
            # Nếu đã tồn tại và đã xác minh -> Báo lỗi
            raise HTTPException(status_code=400, detail="Email này đã được đăng ký và kích hoạt.")
        else:
            # Nếu tồn tại nhưng chưa xác minh -> Cập nhật lại thông tin mới nhất và đi tiếp
            user_exist.name = user.username
            user_exist.password_hash = hashed_pwd
            user_obj = user_exist
    else:
        # 2. Nếu chưa từng tồn tại -> Tạo user mới với is_active = False
        user_obj = models.User(
            name=user.username,
            email=user.email,
            password_hash=hashed_pwd,
            is_active=False
        )
        db.add(user_obj)

    # Mỗi lần đăng ký lại -> tăng version để VÔ HIỆU HÓA mọi token xác minh cũ.
    # Token phát hành lần trước mang version cũ sẽ bị verify-email từ chối.
    user_obj.verify_token_version = (user_obj.verify_token_version or 0) + 1
    db.commit()
    db.refresh(user_obj)

    # 3. Tạo mã JWT xác minh (Chỉ sống 15 phút), gắn kèm version hiện tại.
    verify_token = security.create_access_token(
        data={
            "sub": user.email,
            "type": "verify_email",
            "ver": user_obj.verify_token_version,
        },
        expires_delta=timedelta(minutes=15)
    )

    # 4. Gửi email
    await send_verification_email(email_to=user.email, token=verify_token)

    return {"message": "Đăng ký thành công. Vui lòng kiểm tra email để lấy mã kích hoạt."}


@router.post("/verify-email")
def verify_email(data: schemas.VerifyEmail, db: Session = Depends(get_db)):
    try:
        # 1. Giải mã token người dùng gửi lên
        payload = jwt.decode(data.token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        token_ver = payload.get("ver")

        if email is None or token_type != "verify_email":
            raise HTTPException(status_code=400, detail="Mã xác minh không hợp lệ.")

    except JWTError:
        raise HTTPException(status_code=400, detail="Mã xác minh đã hết hạn hoặc bị sai.")

    # 2. Tìm User và kích hoạt
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    if user.is_active:
        return {"message": "Tài khoản này đã được kích hoạt từ trước."}

    # Chỉ chấp nhận token MỚI NHẤT: version trong token phải khớp version hiện tại
    # của user. Token từ lần đăng ký trước (version cũ, hoặc token cũ không có "ver")
    # bị từ chối.
    if token_ver != user.verify_token_version:
        raise HTTPException(
            status_code=400,
            detail="Mã xác minh này đã hết hiệu lực. Vui lòng dùng mã mới nhất được gửi tới email của bạn.",
        )

    user.is_active = True
    db.commit()
    
    return {"message": "Kích hoạt tài khoản thành công! Bạn có thể đăng nhập ngay."}


@router.post("/login")
def login(user_credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    # 1. Tìm User bằng email
    user = db.query(models.User).filter(models.User.email == user_credentials.email).first()
    if not user:
        raise HTTPException(status_code=403, detail="Tài khoản hoặc mật khẩu không chính xác.")

    # 2a. Tài khoản bị admin khóa -> chặn đăng nhập (tách khỏi trạng thái xác minh).
    if user.is_banned:
        raise HTTPException(status_code=403, detail="Tài khoản của bạn đã bị khóa bởi quản trị viên.")

    # 2b. Kiểm tra tài khoản đã kích hoạt (xác minh email) chưa
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Vui lòng kiểm tra email và kích hoạt tài khoản trước khi đăng nhập.")

    # 3. Kiểm tra mật khẩu (đối chiếu chuỗi thô và chuỗi băm)
    if not security.verify_password(user_credentials.password, user.password_hash):
        raise HTTPException(status_code=403, detail="Tài khoản hoặc mật khẩu không chính xác.")

    # NFR-8: ghi log hoạt động đăng nhập.
    write_system_log(
        db, module="auth", message=f"Đăng nhập: {user.email} (role={user.role})",
        payload={"user_id": str(user.id), "role": user.role},
    )

    # 4. Cấp vé thông hành Access Token
    access_token = security.create_access_token(data={"sub": user.email})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role
        }
    }


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    """Trả thông tin + role của user đang đăng nhập, dùng để Frontend dựng UI theo RBAC."""
    return current_user