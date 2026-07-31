"""Thứ tự xếp hạng ứng viên — dùng CHUNG cho mọi bảng có cột "Hạng".

Vì sao phải nằm một chỗ: leaderboard (GET /jds/{id}/candidates) và shortlist
(GET /shortlists/{id}) là hai endpoint khác nhau nhưng HR đọc chúng như một. Mỗi bên tự
viết một phép sắp xếp thì hai ứng viên TRÙNG ĐIỂM hiện thứ tự này ở tab Leaderboard và
thứ tự ngược lại ở tab Shortlist — đúng kiểu "thứ tự trông hơi kì" mà không ai chỉ ra
được sai ở đâu.
"""
from datetime import datetime, timezone
from typing import Optional, Protocol

# Mốc thay cho created_at bị thiếu: xếp ứng viên đó lên trước trong nhóm cùng điểm.
# Phải là aware để so sánh được với timestamptz đọc từ DB.
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Gắn UTC cho mốc thời gian còn "naive".

    Mọi cột thời gian trong hệ thống là timestamptz, nhưng dữ liệu ghi từ trước lúc đổi
    kiểu (migration d7f1a3c9e5b2) có thể đọc ra naive — so sánh naive với aware ném
    TypeError, và ở đây nó sẽ làm sập cả bảng xếp hạng chứ không chỉ một dòng.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class _Rankable(Protocol):
    score: Optional[float]
    created_at: Optional[datetime]


def score_sort_key(item: _Rankable):
    """Khoá sắp xếp: điểm CAO trước, ứng viên chưa có điểm xếp cuối.

    Chốt phá hoà là (created_at, id) — bắt buộc phải có và phải là thứ KHÔNG đổi:
    `db.query(...).all()` trả về theo thứ tự vật lý trong heap của Postgres, nên chỉ cần
    một lần UPDATE lên hàng nào đó (HR chỉnh điểm, đổi quyết định) là hai ứng viên cùng
    điểm đổi chỗ nhau sau khi nạp lại trang.
    """
    return (
        item.score is None,
        -(item.score or 0),
        as_utc(getattr(item, "created_at", None)) or _EPOCH,
        str(item.id),
    )
