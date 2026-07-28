"""hop_nhat_hai_nhanh_migration

Hai migration b5d2e8a1c4f7 (thêm cột candidates.error_message) và b8d0e2f3a4c5
(bỏ cột users.verify_token_version) được viết song song trên hai nhánh, cùng nhận
a7c9d1e2f3b4 làm cha. Khi hai nhánh gặp nhau lúc merge, đồ thị migration có HAI
head, và `alembic upgrade head` không biết chọn head nào nên báo lỗi:

    CommandError: Multiple head revisions are present for given argument 'head'

Hậu quả là service `api` chết ngay ở bước prestart rồi restart vô hạn. Revision này
không đổi schema, chỉ nối hai nhánh lại làm một để đồ thị có duy nhất một head.

ĐỪNG XOÁ FILE NÀY. Bảng alembic_version trong DB đang trỏ tới đúng revision này;
xoá file đi thì alembic không tìm thấy nó và API lại chết, lần này với thông báo
khác: "Can't locate revision identified by 'c1f4a7b9d2e8'".

Revision ID: c1f4a7b9d2e8
Revises: b5d2e8a1c4f7, b8d0e2f3a4c5
Create Date: 2026-07-28 09:45:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'c1f4a7b9d2e8'
down_revision: Union[str, Sequence[str], None] = ('b5d2e8a1c4f7', 'b8d0e2f3a4c5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Chỉ hợp nhất đồ thị revision, không đụng gì tới schema."""


def downgrade() -> None:
    """Tách lại thành hai nhánh — cũng không đụng gì tới schema."""
