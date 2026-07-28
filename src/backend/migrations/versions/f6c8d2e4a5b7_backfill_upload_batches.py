"""backfill_upload_batches

Dựng lại lượt tải cho các dự án ĐÃ CÓ TỪ TRƯỚC khi có bảng upload_batches.

Không có bước này thì sau khi nâng cấp, mọi dự án cũ vẫn hiện "Lượt tải lên: 0" dù
đang có hàng chục ứng viên — đúng cái lỗi mà bảng upload_batches sinh ra để sửa.

Tên file ZIP gốc thì không thể khôi phục (chưa từng được lưu ở đâu), nên để NULL và
giao diện hiển thị nhãn chung "Tải lên trực tiếp". Những gì suy ra được từ dữ liệu
thật: số CV (đếm candidates) và thời điểm (CV sớm nhất của dự án).

Revision ID: f6c8d2e4a5b7
Revises: e5b7c9d1f2a3
Create Date: 2026-07-28 11:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f6c8d2e4a5b7'
down_revision: Union[str, None] = 'e5b7c9d1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# NOT EXISTS: chỉ đụng vào JD chưa có lượt tải nào, nên chạy lại nhiều lần cũng không
# nhân bản dữ liệu, và JD mới (đã ghi lượt tải đàng hoàng) không bị thêm dòng ảo.
_BACKFILL = """
INSERT INTO upload_batches
    (id, jd_id, filename, total, staged, duplicated, failed, uploaded_by, created_at)
SELECT
    gen_random_uuid(),
    c.jd_id,
    NULL,
    COUNT(*),
    COUNT(*),
    0,
    0,
    jd.created_by,
    MIN(c.created_at)
FROM candidates c
JOIN job_descriptions jd ON jd.id = c.jd_id
WHERE NOT EXISTS (
    SELECT 1 FROM upload_batches ub WHERE ub.jd_id = c.jd_id
)
GROUP BY c.jd_id, jd.created_by
"""


def upgrade() -> None:
    op.execute(_BACKFILL)


def downgrade() -> None:
    # Chỉ gỡ đúng các dòng do backfill tạo (filename IS NULL) — lượt tải thật luôn
    # có tên file, không được đụng tới.
    op.execute("DELETE FROM upload_batches WHERE filename IS NULL")
