"""them_cot_ma_xac_minh_otp

Xác minh email chuyển từ JWT sang mã OTP 6 chữ số lưu trong DB, nên cần 2 cột mới.
Thiếu migration này thì DB đang chạy sẽ không có cột và /auth/verify-email vỡ
(create_all() chỉ tạo bảng mới, KHÔNG thêm cột vào bảng đã tồn tại).

Revision ID: a7c9d1e2f3b4
Revises: f3a1b2c4d5e6
Create Date: 2026-07-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c9d1e2f3b4'
down_revision: Union[str, None] = 'f3a1b2c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}


def upgrade() -> None:
    # Bỏ qua cột đã có. Trên nhánh dev từng tồn tại một migration auto-generate trùng
    # (eff88ce6f969) cũng thêm đúng 2 cột này; máy nào đã chạy bản đó rồi mà chạy tiếp
    # bản này sẽ chết vì DuplicateColumn. create_all() với DB trống cũng dựng sẵn 2 cột.
    existing = _existing_columns()

    if "verification_code" not in existing:
        op.add_column('users', sa.Column('verification_code', sa.String(length=6), nullable=True))
    if "verification_code_expires_at" not in existing:
        op.add_column(
            'users',
            # timezone=True: code so sánh hạn dùng với datetime.now(timezone.utc).
            sa.Column('verification_code_expires_at', sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    existing = _existing_columns()
    if "verification_code_expires_at" in existing:
        op.drop_column('users', 'verification_code_expires_at')
    if "verification_code" in existing:
        op.drop_column('users', 'verification_code')
