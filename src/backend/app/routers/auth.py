from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from app import models, schemas
from app.core.dependencies import get_current_user
from app.database import get_db
from app.utils import security
from app.services.email import send_verification_email
from app.services.logging import write_system_log, write_audit_log
from app.utils.security import generate_6_digit_code

# Gửi SMTP mất ~3.4s (đo được), so với ~0.2s cho login. Chạy đồng bộ trong request
# khiến người dùng ngồi nhìn spinner suốt quãng đó, và tệ hơn: hàng user đã commit
# TRƯỚC lệnh gửi, nên SMTP lỗi là endpoint trả 500 dù tài khoản đã tạo xong —
# người dùng thấy "thất bại", không đăng nhập được (chưa active), cũng không có mã.
# Đẩy sang BackgroundTasks: request trả về ngay, lỗi gửi mail không thể làm hỏng
# một lượt đăng ký đã thành công (người dùng vẫn còn nút "Gửi lại mã").
async def _send_code_safely(email_to: str, code: str) -> None:
    try:
        await send_verification_email(email_to=email_to, token=code)
    except Exception as e:  # noqa: BLE001 - chạy nền, không có ai để ném lỗi lên
        print(f"[auth] Không gửi được mã xác minh tới {email_to}: {type(e).__name__}: {e}")

# Mã OTP sống 15 phút; hai lần xin mã phải cách nhau ít nhất 60 giây.
OTP_TTL = timedelta(minutes=15)
RESEND_COOLDOWN = timedelta(seconds=60)


def _as_utc(dt: datetime | None) -> datetime | None:
    """Hàng cũ có thể lưu naive -> gán UTC, tránh vỡ khi so sánh với now(timezone.utc)."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    user: schemas.UserCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
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

    db.commit()
    db.refresh(user_obj)

    # 3. Sinh mã OTP 6 chữ số (sống 15 phút). Đăng ký lại sẽ ghi đè mã cũ, nên mã
    #    trước đó tự động mất hiệu lực — không cần cơ chế version như thời dùng JWT.
    otp_code = generate_6_digit_code()
    expires_at = datetime.now(timezone.utc) + OTP_TTL

    user_obj.verification_code = otp_code
    user_obj.verification_code_expires_at = expires_at

    db.commit()
    db.refresh(user_obj)

    # 4. Gửi email (chạy nền, xem ghi chú ở _send_code_safely)
    background.add_task(_send_code_safely, user.email, otp_code)

    return {"message": "Đăng ký thành công. Vui lòng kiểm tra email để lấy mã kích hoạt."}


@router.post("/resend-code")
def resend_code(
    data: schemas.ResendCode,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Cấp lại mã OTP mới. Mã chỉ sống 15 phút, mà trước đây cách duy nhất để lấy mã
    mới là đăng ký lại từ đầu (phải nhập lại cả mật khẩu) — người dùng bị kẹt.

    LUÔN trả cùng một thông điệp dù email có tồn tại hay không: phản hồi khác nhau
    sẽ biến endpoint này thành công cụ dò xem email nào đã đăng ký.

    CHẶN TẦN SUẤT Ở SERVER: cooldown 60s bên frontend chỉ là state của React, F5 một
    cái là mất. Không chặn ở đây thì bất kỳ ai cũng bơm được vô hạn email qua hạn
    mức SMTP. Mốc "lần gửi gần nhất" suy ra từ chính hạn dùng của mã đang lưu
    (expires_at - OTP_TTL) nên không cần thêm cột.
    """
    generic = {"message": "Nếu email tồn tại và chưa kích hoạt, mã mới đã được gửi đi."}

    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user or user.is_active:
        return generic

    now = datetime.now(timezone.utc)
    expires_at = _as_utc(user.verification_code_expires_at)
    if user.verification_code and expires_at:
        last_sent = expires_at - OTP_TTL
        if now - last_sent < RESEND_COOLDOWN:
            # Im lặng bỏ qua: trả cùng `generic` để không tiết lộ là có tài khoản.
            return generic

    user.verification_code = generate_6_digit_code()
    user.verification_code_expires_at = now + OTP_TTL
    db.commit()
    db.refresh(user)

    background.add_task(_send_code_safely, user.email, user.verification_code)
    return generic


@router.post("/verify-email")
def verify_email(data: schemas.VerifyEmail, db: Session = Depends(get_db)):
    
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    if user.is_active:
        return {"message": "Tài khoản này đã được kích hoạt từ trước."}

    if not user.verification_code or user.verification_code != data.token.strip():
        raise HTTPException(status_code=400, detail="Mã xác minh không chính xác.")

    # Hàng cũ (đăng ký trước khi có OTP) có thể thiếu hạn dùng -> coi như hết hạn,
    # thay vì so sánh với None và ném 500.
    expires_at = user.verification_code_expires_at
    if expires_at is None:
        raise HTTPException(status_code=400, detail="Mã xác minh đã hết hạn. Vui lòng đăng ký lại để nhận mã mới.")
    # Cột lưu timezone-aware; hàng cũ có thể còn naive -> gán UTC trước khi so sánh
    # để không vỡ vì "can't compare offset-naive and offset-aware datetimes".
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Mã xác minh đã hết hạn. Vui lòng đăng ký lại để nhận mã mới.")

    user.is_active = True
    user.verification_code = None
    user.verification_code_expires_at = None
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


# ---- Tự quản lý tài khoản (HR/Admin sửa CHÍNH tài khoản mình đang đăng nhập) ----
# Tách hẳn khỏi router /users (chỉ admin vào được): ở đây `user_id` không phải tham
# số — luôn là current_user — nên không có đường nào để sửa tài khoản người khác.


@router.patch("/me", response_model=schemas.UserResponse)
def update_me(
    payload: schemas.ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Đổi tên hiển thị của chính mình."""
    new_name = payload.username.strip()
    if len(new_name) < 2:
        raise HTTPException(status_code=400, detail="Tên hiển thị phải có ít nhất 2 ký tự.")

    # Không đổi gì -> trả về luôn, đừng ghi một dòng audit rỗng.
    if new_name == current_user.name:
        return current_user

    before = current_user.name
    current_user.name = new_name
    db.commit()
    db.refresh(current_user)

    write_audit_log(
        db, user_id=current_user.id, action="UPDATE_PROFILE", entity_type="user",
        entity_id=current_user.id,
        old_data={"name": before},
        new_data={"name": current_user.name},
    )
    return current_user


@router.put("/me/password")
def change_my_password(
    payload: schemas.PasswordChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Tự đổi mật khẩu, có xác nhận bằng mật khẩu hiện tại.

    LƯU Ý: token đang giữ VẪN còn hiệu lực tới khi hết hạn (JWT không có danh sách
    thu hồi) — đổi mật khẩu ở đây không đá các phiên khác ra ngoài.
    """
    if not security.verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng.")

    if security.verify_password(payload.new_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải khác mật khẩu hiện tại.")

    current_user.password_hash = security.get_password_hash(payload.new_password)
    db.commit()

    write_system_log(
        db, module="auth",
        message=f"Đổi mật khẩu: {current_user.email}",
        payload={"user_id": str(current_user.id)},
    )
    # Chỉ ghi NHẬN việc đã đổi — tuyệt đối không đưa mật khẩu/hash vào nhật ký.
    write_audit_log(
        db, user_id=current_user.id, action="CHANGE_PASSWORD", entity_type="user",
        entity_id=current_user.id,
        old_data={"password": "•••"},
        new_data={"password": "••• (đã đổi)"},
    )
    return {"message": "Đổi mật khẩu thành công."}