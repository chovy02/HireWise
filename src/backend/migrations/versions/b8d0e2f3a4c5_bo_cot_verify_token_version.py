"""bo_cot_verify_token_version

Cột `users.verify_token_version` phục vụ cơ chế xác minh bằng JWT: token mang theo
version tại thời điểm phát hành, đăng ký lại thì tăng version để vô hiệu hoá token cũ.
Từ khi chuyển sang OTP 6 chữ số lưu thẳng trong DB (a7c9d1e2f3b4), việc thu hồi mã cũ
do chính `verification_code` đảm nhiệm — cột này chỉ còn được GHI mà không ai ĐỌC.

Revision ID: b8d0e2f3a4c5
Revises: a7c9d1e2f3b4
Create Date: 2026-07-26 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d0e2f3a4c5'
down_revision: Union[str, None] = 'a7c9d1e2f3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(name: str) -> bool:
    return name in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}


def upgrade() -> None:
    # DB mới toanh do create_all() dựng sẽ không có cột này (đã bỏ khỏi model), nên
    # phải kiểm tra trước khi drop.
    if _has_column("verify_token_version"):
        op.drop_column('users', 'verify_token_version')


def downgrade() -> None:
    if not _has_column("verify_token_version"):
        op.add_column(
            'users',
            sa.Column(
                'verify_token_version',
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
