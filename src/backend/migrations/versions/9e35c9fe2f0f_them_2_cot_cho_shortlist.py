"""Them 2 cot cho shortlist

Thêm `shortlist_items.notified_at` và `notified_status` để theo dõi việc đã gửi email
báo kết quả cho ứng viên hay chưa.

LƯU Ý VỀ MỘT LỆNH RÁC ĐÃ ĐƯỢC GỠ: bản autogenerate đầu tiên của migration này kèm
theo `op.drop_column('users', 'verify_token_version')` — cột đó KHÔNG liên quan gì
tới shortlist. Nó lọt vào vì `alembic revision --autogenerate` so model với DB cục bộ
lúc đó vẫn còn cột (máy ấy chưa chạy b8d0e2f3a4c5, đúng migration đã xoá cột này).

Trên mọi máy đã chạy b8d0e2f3a4c5 — mà b8d0e2f3a4c5 là TỔ TIÊN của revision này nên
luôn chạy trước — cột đã biến mất, lệnh drop ném UndefinedColumn và service `api`
chết ngay ở bước prestart rồi restart vô hạn ("Backend not reachable" ở màn đăng nhập).

Rút ra: migration autogenerate phải đọc lại trước khi commit; dòng chú thích
"please adjust!" mà alembic tự chèn chính là chỗ này.

Revision ID: 9e35c9fe2f0f
Revises: b5d2e8a1c4f7
Create Date: 2026-07-28 13:19:45.160860

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e35c9fe2f0f'
down_revision: Union[str, None] = 'b5d2e8a1c4f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, name: str) -> bool:
    return name in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # DB mới toanh do create_all() dựng đã có sẵn 2 cột này (model đã khai báo), nên
    # phải kiểm tra trước khi thêm — cùng lối viết với các migration khác trong repo.
    if not _has_column('shortlist_items', 'notified_at'):
        op.add_column(
            'shortlist_items',
            sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
        )
    if not _has_column('shortlist_items', 'notified_status'):
        op.add_column(
            'shortlist_items',
            sa.Column('notified_status', sa.String(length=50), nullable=True),
        )


def downgrade() -> None:
    # Chỉ hoàn tác đúng phần migration này thực sự làm. KHÔNG thêm lại
    # users.verify_token_version: model không còn cột đó, và việc bỏ cột thuộc trách
    # nhiệm của b8d0e2f3a4c5 — downgrade migration đó mới là chỗ dựng lại cột.
    if _has_column('shortlist_items', 'notified_status'):
        op.drop_column('shortlist_items', 'notified_status')
    if _has_column('shortlist_items', 'notified_at'):
        op.drop_column('shortlist_items', 'notified_at')
