from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.utils import security

# /auth/login nhận JSON {email, password}, không phải OAuth2 form login, nên dùng HTTPBearer
# để Swagger UI hiện ô "Value" dán thẳng access_token vào, thay vì popup username/password.
bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Không thể xác thực, vui lòng đăng nhập lại.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = security.decode_access_token(token)
        email: str | None = payload.get("sub")
        # Token xác minh email không được dùng để truy cập API như một phiên đăng nhập.
        if email is None or payload.get("type") == "verify_email":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản của bạn đã bị khóa bởi quản trị viên.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản chưa được kích hoạt (chưa xác minh email).",
        )
    return user


def require_role(*allowed_roles: str):
    """Dependency factory cho RBAC: chặn truy cập nếu role của user không thuộc allowed_roles."""

    def role_checker(current_user: models.User = Depends(get_current_user)) -> models.User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thực hiện hành động này.",
            )
        return current_user

    return role_checker
