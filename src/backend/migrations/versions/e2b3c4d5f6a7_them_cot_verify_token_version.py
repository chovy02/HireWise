"""them_cot_verify_token_version cho user

Revision ID: e2b3c4d5f6a7
Revises: d1a2e3f4b5c6
Create Date: 2026-07-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b3c4d5f6a7'
down_revision: Union[str, None] = 'd1a2e3f4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Đếm số lần phát hành token xác minh; token cũ (version thấp hơn) bị vô hiệu hóa.
    op.add_column(
        'users',
        sa.Column(
            'verify_token_version',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'verify_token_version')
