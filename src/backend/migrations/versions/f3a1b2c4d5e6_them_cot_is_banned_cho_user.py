"""them_cot_is_banned_cho_user

Revision ID: f3a1b2c4d5e6
Revises: ea8ae8cda1d3
Create Date: 2026-07-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a1b2c4d5e6'
down_revision: Union[str, None] = 'ea8ae8cda1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tách trạng thái "bị admin khóa" ra khỏi is_active (vốn chỉ là cờ xác minh email).
    op.add_column(
        'users',
        sa.Column('is_banned', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('users', 'is_banned')
