"""Email template: dinh dang HTML va file gan kem

Thêm `email_templates.body_format` ('text' | 'html') và bảng
`email_template_attachments` để HR gắn ảnh chèn giữa bài + file đính kèm vào mẫu mail.

Vì sao cần body_format thay vì tự đoán: một mẫu chữ thường viết "mức lương < 20 triệu"
sẽ bị bộ dò HTML nhận nhầm. Cột mặc định 'text' nên MỌI mẫu đã lưu trước đây vẫn gửi
đúng như cũ, không cần backfill.

Lưu ý về create_all(): app/main.py gọi models.Base.metadata.create_all() lúc khởi động,
nên DB mới dựng đã có sẵn cột/bảng này — mọi lệnh dưới đây đều phải kiểm tra trước khi
tạo, đúng lối viết của 9e35c9fe2f0f và các migration khác trong repo. create_all() KHÔNG
sửa bảng đã tồn tại, nên với DB cũ thì migration này mới là chỗ thêm cột.

Revision ID: c4a7e91b6d20
Revises: 3e0e0661f7d9
Create Date: 2026-07-30 09:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a7e91b6d20'
down_revision: Union[str, None] = '3e0e0661f7d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    return name in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    return name in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if not _has_column('email_templates', 'body_format'):
        op.add_column(
            'email_templates',
            # server_default để các hàng đang có nhận 'text' ngay, khỏi phải UPDATE
            # riêng; nullable=False an toàn vì đã có default cho hàng cũ.
            sa.Column(
                'body_format',
                sa.String(length=10),
                nullable=False,
                server_default='text',
            ),
        )

    if not _has_table('email_template_attachments'):
        op.create_table(
            'email_template_attachments',
            sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('template_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('filename', sa.String(length=255), nullable=False),
            sa.Column('content_type', sa.String(length=150), nullable=False),
            sa.Column('size_bytes', sa.Integer(), nullable=False),
            sa.Column('file_path', sa.String(length=500), nullable=False),
            sa.Column('is_inline', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('content_id', sa.String(length=100), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            # ondelete CASCADE: xoá mẫu thì file gắn kèm không được thành hàng mồ côi
            # trỏ tới template_id không còn tồn tại.
            sa.ForeignKeyConstraint(['template_id'], ['email_templates.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    # Index đứng NGOÀI khối tạo bảng ở trên, có guard riêng.
    #
    # Gộp vào trong đó là một cái bẫy: create_all() lúc khởi động app đã dựng bảng
    # trước khi alembic chạy, nên nhánh "chưa có bảng" gần như không bao giờ vào, và
    # index sẽ vĩnh viễn không được tạo dù migration trông như đã khai báo. (Đã gặp
    # thật: bảng có đủ cột nhưng get_indexes() trả về rỗng.)
    if _has_table('email_template_attachments') and not _has_index(
        'email_template_attachments', 'ix_email_template_attachments_template_id'
    ):
        op.create_index(
            'ix_email_template_attachments_template_id',
            'email_template_attachments',
            ['template_id'],
        )


def downgrade() -> None:
    if _has_table('email_template_attachments'):
        op.drop_index(
            'ix_email_template_attachments_template_id',
            table_name='email_template_attachments',
        )
        op.drop_table('email_template_attachments')
    if _has_column('email_templates', 'body_format'):
        op.drop_column('email_templates', 'body_format')
