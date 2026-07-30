"""them_cot_details_cho_evaluation

Lưu phân tích chi tiết của mỗi lượt chấm điểm: kết luận + độ tin cậy, điểm và nhận
xét từng trục theo thang điểm, đối chiếu từng yêu cầu của JD (đạt/một phần/thiếu),
điểm mạnh - điểm yếu kèm mức độ và bằng chứng, rủi ro, gợi ý cần kiểm chứng khi
phỏng vấn.

Trước đây một đánh giá chỉ có: 1 con điểm, 3 thanh breakdown và vài câu giải thích —
HR không truy được điểm số từ đâu ra, cũng không biết ứng viên trượt ở yêu cầu nào.

nullable=True và KHÔNG backfill: dữ liệu chi tiết chỉ có được bằng cách gọi lại AI,
không suy ra được từ các cột cũ. Giao diện tự lùi về cách hiển thị cũ khi cột này
rỗng, nên các đánh giá đã có vẫn xem được bình thường.

Revision ID: a9c3f5e70b18
Revises: c4a7e91b6d20
Create Date: 2026-07-30 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a9c3f5e70b18'
down_revision: Union[str, None] = 'c4a7e91b6d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'evaluations',
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('evaluations', 'details')
