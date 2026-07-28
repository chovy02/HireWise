"""merge 3c7c and f6c8

Revision ID: 3e0e0661f7d9
Revises: 3c7cb0d20fa8, f6c8d2e4a5b7
Create Date: 2026-07-28 14:30:57.451258

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e0e0661f7d9'
down_revision: Union[str, None] = ('3c7cb0d20fa8', 'f6c8d2e4a5b7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
