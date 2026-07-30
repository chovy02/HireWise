"""Múi giờ hiển thị của HireWise: UTC+7 (giờ Việt Nam).

QUY ƯỚC CHUNG CỦA HỆ THỐNG — đọc trước khi thêm cột/chỗ hiển thị thời gian mới:

  * LƯU: luôn là UTC. Cột dùng `DateTime(timezone=True)` (timestamptz), giá trị ghi
    vào là `datetime.now(timezone.utc)`. DB giữ một MỐC THỜI ĐIỂM tuyệt đối.
  * TRUYỀN qua API: chuỗi ISO-8601 CÓ offset ("...+00:00"). Pydantic tự làm việc này
    khi cột là timestamptz — không được trả chuỗi không offset, vì trình duyệt sẽ
    hiểu nhầm thành giờ địa phương.
  * HIỂN THỊ cho người dùng: quy sang UTC+7. Ở frontend dùng utils/datetime.js; ở
    backend (CSV, email, log) dùng `to_local`/`format_local` trong file này.

VÌ SAO DÙNG OFFSET CỐ ĐỊNH thay vì ZoneInfo("Asia/Ho_Chi_Minh"): Việt Nam KHÔNG có
giờ mùa hè (DST) từ năm 1975, nên UTC+7 là hằng số — không cần phụ thuộc gói tzdata
của hệ điều hành, thứ vốn có thể thiếu trong image slim.
"""

from datetime import datetime, timedelta, timezone

# Múi giờ hiển thị của toàn hệ thống.
APP_TIMEZONE = timezone(timedelta(hours=7), name="UTC+7")

# Định dạng mặc định cho CSV/email: đọc được bằng mắt và sort được bằng chuỗi.
DEFAULT_FORMAT = "%Y-%m-%d %H:%M:%S"


def to_local(dt: datetime | None) -> datetime | None:
    """Quy một mốc thời gian sang UTC+7.

    Giá trị naive được coi là UTC — đúng với dữ liệu cũ sinh ra hồi các cột còn là
    `timestamp without time zone` nhưng vẫn ghi giờ UTC vào.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(APP_TIMEZONE)


def format_local(dt: datetime | None, fmt: str = DEFAULT_FORMAT, empty: str = "") -> str:
    """Như `to_local` nhưng trả chuỗi đã format, dùng trực tiếp cho CSV/email."""
    local = to_local(dt)
    return empty if local is None else local.strftime(fmt)
