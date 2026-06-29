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
    created_at: datetime

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class VerifyEmail(BaseModel):
    token: str


class UserCreateByAdmin(BaseModel):
    """Admin tạo tài khoản trực tiếp: tài khoản được active ngay, không cần xác minh email."""
    username: str
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole = UserRole.hr_staff


class UserUpdateByAdmin(BaseModel):
    """Admin sửa thông tin tài khoản. Field nào không gửi lên sẽ giữ nguyên giá trị cũ."""
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8)