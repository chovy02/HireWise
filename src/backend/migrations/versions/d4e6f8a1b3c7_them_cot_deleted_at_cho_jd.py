"""them_cot_deleted_at_cho_jd

Thùng rác cho dự án tuyển dụng (JD): cột `job_descriptions.deleted_at`.
NULL = đang hoạt động; có giá trị = đã bị xoá vào thùng rác và có thể khôi phục.

Revision ID: d4e6f8a1b3c7
Revises: c1f4a7b9d2e8
Create Date: 2026-07-28 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e6f8a1b3c7'
down_revision: Union[str, None] = 'c1f4a7b9d2e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(name: str) -> bool:
    return name in {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("job_descriptions")
    }


def upgrade() -> None:
    # DB mới toanh do create_all() dựng đã có sẵn cột này (model đã khai báo), nên
    # phải kiểm tra trước khi thêm — cùng lối viết với các migration trước.
    if not _has_column("deleted_at"):
        op.add_column(
            'job_descriptions',
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("deleted_at"):
        op.drop_column('job_descriptions', 'deleted_at')
