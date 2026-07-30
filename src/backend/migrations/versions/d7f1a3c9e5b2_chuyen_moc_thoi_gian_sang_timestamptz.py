"""Chuyen moi cot thoi gian sang timestamptz

SỬA LỖI "GIỜ TOÀN HỆ THỐNG SAI 7 TIẾNG".

Bối cảnh: code luôn sinh mốc thời gian bằng `datetime.now(timezone.utc)` (có offset),
nhưng phần lớn cột lại khai báo `DateTime` trần = `timestamp without time zone`.
Postgres CẮT BỎ offset khi ghi vào cột đó, nên DB giữ đúng con số giờ UTC nhưng mất
thông tin "đây là UTC". API trả ra chuỗi không offset — "2026-07-26T13:02:53" — và
theo chuẩn ECMAScript thì `new Date("2026-07-26T13:02:53")` được hiểu là GIỜ ĐỊA
PHƯƠNG của trình duyệt. Máy ở Việt Nam (UTC+7) vì thế hiển thị MỌI mốc thời gian sớm
hơn thực tế 7 tiếng.

Migration này chuyển các cột đó sang `timestamptz`. Giá trị cũ được đọc bằng
`AT TIME ZONE 'UTC'` — đúng vì dữ liệu cũ CHÍNH LÀ giờ UTC, chỉ thiếu nhãn; nhờ vậy
không mốc nào bị dịch sai khi nâng cấp.

VÌ SAO QUÉT information_schema THAY VÌ LIỆT KÊ CỨNG: repo này có hai đường dựng
schema song song — `create_all()` lúc khởi động và alembic — nên DB mới đã sẵn
timestamptz (model vừa sửa) còn DB cũ thì chưa. Ngoài ra volume dev cũ còn sót vài
bảng không còn trong models.py (project_evaluations, system_settings). Quét động thì
mọi DB đều về cùng một trạng thái, và chạy lại migration cũng không gây lỗi.

Revision ID: d7f1a3c9e5b2
Revises: a9c3f5e70b18
Create Date: 2026-07-30 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7f1a3c9e5b2'
down_revision: Union[str, None] = 'a9c3f5e70b18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns_of_type(data_type: str) -> list[tuple[str, str]]:
    """Các cột (bảng, cột) thuộc bảng THẬT trong schema public có kiểu `data_type`.

    Lọc theo table_type='BASE TABLE' để bỏ view — view không ALTER COLUMN được.
    """
    rows = op.get_bind().execute(
        sa.text(
            """
            SELECT c.table_name, c.column_name
            FROM information_schema.columns AS c
            JOIN information_schema.tables AS t
              ON t.table_schema = c.table_schema
             AND t.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND t.table_type = 'BASE TABLE'
              AND c.data_type = :dtype
            ORDER BY c.table_name, c.column_name
            """
        ),
        {"dtype": data_type},
    )
    return [(r[0], r[1]) for r in rows]


def _convert(table: str, column: str, target: str) -> None:
    # USING ... AT TIME ZONE 'UTC' là phần quan trọng nhất:
    #   - naive -> timestamptz: coi con số đang có LÀ giờ UTC (đúng với dữ liệu cũ).
    #   - timestamptz -> naive: lấy lại con số giờ UTC.
    # Thiếu USING, Postgres sẽ quy đổi theo TimeZone của session và làm lệch dữ liệu.
    op.execute(
        f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
        f'TYPE {target} USING "{column}" AT TIME ZONE \'UTC\''
    )


def upgrade() -> None:
    for table, column in _columns_of_type("timestamp without time zone"):
        _convert(table, column, "timestamptz")


def downgrade() -> None:
    for table, column in _columns_of_type("timestamp with time zone"):
        # ai_logs.created_at, users.verification_code_expires_at và
        # shortlist_items.notified_at vốn ĐÃ là timestamptz từ trước migration này;
        # hạ chúng xuống naive sẽ phá schema mà chúng vẫn luôn dùng.
        if (table, column) in _ALREADY_TZ_BEFORE:
            continue
        _convert(table, column, "timestamp without time zone")


# Các cột đã là timestamptz TRƯỚC migration này — downgrade phải để yên.
_ALREADY_TZ_BEFORE = {
    ("ai_logs", "created_at"),
    ("users", "verification_code_expires_at"),
    ("shortlist_items", "notified_at"),
}
