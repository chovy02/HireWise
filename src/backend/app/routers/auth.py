from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from jose import jwt, JWTError
import os

from app import models, schemas
from app.database import get_db
from app.utils import security
from app.services.email import send_verification_email

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # 1. Kiểm tra email đã tồn tại chưa
    user_exist = db.query(models.User).filter(models.User.email == user.email).first()
    if user_exist:
        raise HTTPException(status_code=400, detail="Email này đã được đăng ký.")

    # 2. Băm mật khẩu và lưu Database với is_active = False
    hashed_pwd = security.get_password_hash(user.password)
    new_user = models.User(
        name=user.username,
        email=user.email,
        password_hash=hashed_pwd,
        is_active=False
    )
    db.add(new_user)
    db.commit()

    # 3. Tạo mã JWT xác minh (Chỉ sống 15 phút)
    verify_token = security.create_access_token(
        data={"sub": user.email, "type": "verify_email"}, 
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

    user.is_active = True
    db.commit()
    
    return {"message": "Kích hoạt tài khoản thành công! Bạn có thể đăng nhập ngay."}


@router.post("/login")
def login(user_credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    # 1. Tìm User bằng email
    user = db.query(models.User).filter(models.User.email == user_credentials.email).first()
    if not user:
        raise HTTPException(status_code=403, detail="Tài khoản hoặc mật khẩu không chính xác.")

    # 2. Kiểm tra tài khoản đã kích hoạt chưa
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Vui lòng kiểm tra email và kích hoạt tài khoản trước khi đăng nhập.")

    # 3. Kiểm tra mật khẩu (đối chiếu chuỗi thô và chuỗi băm)
    if not security.verify_password(user_credentials.password, user.password_hash):
        raise HTTPException(status_code=403, detail="Tài khoản hoặc mật khẩu không chính xác.")

    # 4. Cấp vé thông hành Access Token
    access_token = security.create_access_token(data={"sub": user.email})
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email
        }
    }