from enum import Enum
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class UserRole(str, Enum):
    admin = "admin"
    hr_staff = "hr_staff"


class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserResponse(BaseModel):
    """Trả thông tin user từ DB. Field tên khớp với cột thật trong model.User (name, không phải username)."""
    id: UUID
    name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    is_banned: bool
    created_at: datetime

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ResendCode(BaseModel):
    """Xin cấp lại mã OTP khi mã cũ đã hết hạn (15 phút) hoặc email chưa tới."""
    email: EmailStr


class VerifyEmail(BaseModel):
    """Xác minh bằng mã OTP 6 chữ số gửi qua email (không còn là JWT).
    Vì mã chỉ có 6 chữ số nên phải kèm email để biết đối chiếu với tài khoản nào."""
    email: EmailStr
    token: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class UserCreateByAdmin(BaseModel):
    """Admin tạo tài khoản trực tiếp: tài khoản được active ngay, không cần xác minh email."""
    username: str
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole = UserRole.hr_staff


class ProfileUpdate(BaseModel):
    """Người dùng TỰ sửa thông tin của mình (trang "Quản lý tài khoản" của HR).

    Chỉ có tên: email đang là `sub` của JWT nên đổi email là vé thông hành hiện tại
    hết hiệu lực ngay giữa phiên, còn role/is_active/is_banned là quyền của admin —
    để lọt vào đây thì HR tự nâng mình thành admin được.
    """
    username: str = Field(min_length=2, max_length=255)


class PasswordChange(BaseModel):
    """Tự đổi mật khẩu. BẮT BUỘC nhập lại mật khẩu hiện tại: chỉ có token thôi thì
    ai ngồi vào máy chưa đăng xuất cũng đổi được mật khẩu và chiếm luôn tài khoản."""
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserUpdateByAdmin(BaseModel):
    """Admin sửa thông tin tài khoản. Field nào không gửi lên sẽ giữ nguyên giá trị cũ."""
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    is_banned: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8)