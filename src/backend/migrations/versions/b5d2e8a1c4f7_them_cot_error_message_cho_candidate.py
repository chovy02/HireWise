"""them_cot_error_message_cho_candidate

Lưu lý do thất bại của việc trích xuất/chấm điểm CV. Trước đây lý do chỉ nằm trong
giá trị trả về của Celery task rồi mất luôn, nên giao diện chỉ hiện được chữ "Lỗi".

Revision ID: b5d2e8a1c4f7
Revises: a7c9d1e2f3b4
Create Date: 2026-07-26 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d2e8a1c4f7'
down_revision: Union[str, None] = 'a7c9d1e2f3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('candidates', sa.Column('error_message', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('candidates', 'error_message')
