"""Them cot trang thai gui mail cho shortlist_items

Thêm 4 cột theo dõi LƯỢT GỬI mail kết quả, kể cả khi lượt đó thất bại:

* notify_state            — None | "sending" | "sent" | "failed"
* notify_error_code       — mã lỗi phân loại (invalid_email, auth_failed, …)
* notify_error            — câu giải thích hiển thị cho HR
* notify_attempts         — số lượt đã thử (để biết ứng viên nào gửi mãi không được)
* notify_last_attempt_at  — mốc thử gần nhất (dùng để phát hiện lô gửi bị treo)

Hai cột `notified_at` / `notified_status` có từ migration 9e35c9fe2f0f vẫn giữ nguyên
ý nghĩa: dấu vết của lần gửi THÀNH CÔNG gần nhất. Trước khi có nhóm cột này, thất bại
không để lại dấu vết nào — UI chỉ có hai trạng thái "đã gửi"/"chưa gửi" nên HR không
phân biệt được email sai định dạng với hàng đợi chưa chạy tới.

Revision ID: f2b6d4a8c910
Revises: d7f1a3c9e5b2
Create Date: 2026-07-31 10:12:33.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b6d4a8c910'
down_revision: Union[str, None] = 'd7f1a3c9e5b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, name: str) -> bool:
    return name in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


# (tên cột, kiểu) — khai báo một chỗ để upgrade/downgrade không lệch nhau.
_COLUMNS = (
    ('notify_state', sa.String(length=20), True, None),
    ('notify_error_code', sa.String(length=50), True, None),
    ('notify_error', sa.Text(), True, None),
    # nullable=False + server_default: các dòng đã có sẵn phải nhận giá trị 0, và cột
    # này được cộng dồn trong code nên không được phép là NULL.
    ('notify_attempts', sa.Integer(), False, '0'),
    ('notify_last_attempt_at', sa.DateTime(timezone=True), True, None),
)


def upgrade() -> None:
    # DB mới toanh do create_all() dựng đã có sẵn các cột này (model đã khai báo), nên
    # phải kiểm tra trước khi thêm — cùng lối viết với các migration khác trong repo.
    for name, type_, nullable, server_default in _COLUMNS:
        if not _has_column('shortlist_items', name):
            op.add_column(
                'shortlist_items',
                sa.Column(name, type_, nullable=nullable, server_default=server_default),
            )


def downgrade() -> None:
    for name, *_ in reversed(_COLUMNS):
        if _has_column('shortlist_items', name):
            op.drop_column('shortlist_items', name)
