"""them_bang_upload_batches

Lưu lịch sử từng lượt tải file ZIP CV lên cho một vị trí tuyển dụng.

Trước đây danh sách này chỉ nằm trong state React nên F5 là mất: dự án có 15 ứng
viên mà ô "Lượt tải lên" vẫn hiện 0 và khung "Hồ sơ đã tải lên" thì trống.

Revision ID: e5b7c9d1f2a3
Revises: d4e6f8a1b3c7
Create Date: 2026-07-28 11:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'e5b7c9d1f2a3'
down_revision: Union[str, None] = 'd4e6f8a1b3c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # DB mới toanh do create_all() dựng đã có sẵn bảng này (model đã khai báo), nên
    # phải kiểm tra trước khi tạo — cùng lối viết với các migration trước.
    if _has_table("upload_batches"):
        return
    op.create_table(
        'upload_batches',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('jd_id', UUID(as_uuid=True),
                  sa.ForeignKey('job_descriptions.id'), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=True),
        sa.Column('total', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('staged', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('duplicated', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('failed', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('uploaded_by', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    # Luôn truy vấn theo jd_id (liệt kê lượt tải của một dự án).
    op.create_index('ix_upload_batches_jd_id', 'upload_batches', ['jd_id'])


def downgrade() -> None:
    if _has_table("upload_batches"):
        op.drop_index('ix_upload_batches_jd_id', table_name='upload_batches')
        op.drop_table('upload_batches')
