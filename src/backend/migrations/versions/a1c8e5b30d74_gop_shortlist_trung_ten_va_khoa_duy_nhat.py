"""Gop shortlist trung ten trong cung mot JD, roi khoa duy nhat

VÌ SAO: HR bảo agent "cho 3 người tiềm năng vào shortlist", mở màn hình Shortlisting
lên thì dropdown hiện HAI dòng "tiềm năng (3)" giống hệt nhau. `_shortlist_for` trong
agent_tools tra tên trước rồi mới INSERT, nên hai lượt chạy chồng nhau (HR gửi lại câu
lệnh, agent thử lại, hoặc bấm nút "Danh sách rút gọn mới" hai lần) đều đọc thấy "chưa
có" rồi cùng tạo. Mọi lớp chặn bằng Python vẫn còn khe hở đó — chỉ ràng buộc ở tầng DB
mới đóng được.

Migration làm 2 việc, theo đúng thứ tự:

1. GỘP các shortlist đã trùng: trong mỗi nhóm (jd_id, lower(btrim(name))), giữ bản
   CŨ NHẤT rồi chuyển shortlist_items của các bản còn lại về đó. Ứng viên đã có mặt
   trong bản giữ lại thì item thừa bị xoá (không thể có hai dòng cùng cv_id trong một
   shortlist). Chuyển chứ không xoá thẳng: quyết định nhận/loại và dấu vết gửi mail
   nằm trên chính shortlist_items, xoá đi là mất việc HR đã làm.

2. Tạo unique index (jd_id, lower(btrim(name))).

Bước 1 BẮT BUỘC chạy trước: DB nào đang có sẵn dòng trùng thì CREATE UNIQUE INDEX sẽ
đổ, và prestart chạy `upgrade head` lúc container api khởi động nên api sẽ không lên
được.

Revision ID: a1c8e5b30d74
Revises: f2b6d4a8c910
Create Date: 2026-08-08 09:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c8e5b30d74'
down_revision: Union[str, None] = 'f2b6d4a8c910'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = 'uq_shortlists_jd_ten'


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # ── Bước 1: gộp các shortlist trùng tên ────────────────────────────────────
    # `giu` = shortlist cũ nhất của mỗi nhóm; `bo` = các bản trùng phải gộp vào nó.
    # Chốt phá hoà bằng id để hai lần chạy trên cùng dữ liệu luôn chọn cùng một bản.
    nhom = bind.execute(sa.text("""
        SELECT s.id AS bo, k.giu
        FROM shortlists s
        JOIN (
            SELECT jd_id,
                   lower(btrim(name)) AS ten,
                   (array_agg(id ORDER BY created_at, id))[1] AS giu
            FROM shortlists
            GROUP BY jd_id, lower(btrim(name))
            HAVING count(*) > 1
        ) k ON k.jd_id = s.jd_id AND k.ten = lower(btrim(s.name))
        WHERE s.id <> k.giu
    """)).mappings().all()

    for dong in nhom:
        # Ứng viên đã nằm trong bản giữ lại -> item ở bản trùng là thừa, xoá đi.
        # Bản giữ lại là bản CŨ HƠN nên quyết định trên đó mới là cái HR chốt trước.
        bind.execute(
            sa.text("""
                DELETE FROM shortlist_items thua
                WHERE thua.shortlist_id = :bo
                  AND EXISTS (
                      SELECT 1 FROM shortlist_items giu
                      WHERE giu.shortlist_id = :giu AND giu.cv_id = thua.cv_id
                  )
            """),
            {"bo": dong["bo"], "giu": dong["giu"]},
        )
        bind.execute(
            sa.text("UPDATE shortlist_items SET shortlist_id = :giu WHERE shortlist_id = :bo"),
            {"bo": dong["bo"], "giu": dong["giu"]},
        )
        bind.execute(sa.text("DELETE FROM shortlists WHERE id = :bo"), {"bo": dong["bo"]})

    # ── Bước 2: khoá lại để không tái diễn ─────────────────────────────────────
    # DB mới toanh do create_all() dựng đã có sẵn index này (model đã khai báo trong
    # __table_args__), nên phải kiểm tra trước — cùng lối viết với các migration khác.
    if not _has_index('shortlists', INDEX_NAME):
        op.create_index(
            INDEX_NAME,
            'shortlists',
            ['jd_id', sa.text('lower(btrim(name))')],
            unique=True,
        )


def downgrade() -> None:
    # Chỉ gỡ được ràng buộc; các shortlist đã gộp ở bước 1 không tách lại được.
    if _has_index('shortlists', INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name='shortlists')
