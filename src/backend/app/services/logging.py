import json
import uuid as _uuid_mod

from sqlalchemy.orm import Session

from app import models

# Trần kích thước payload log (tránh nhồi cả CV/markdown dài vào agent_tool_logs).
_MAX_LOG_CHARS = 8000


def _json_safe(obj):
    """Ép về JSON-serializable (UUID -> str) và cắt bớt nếu quá dài."""
    try:
        text = json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        return {"_unserializable": str(obj)[:500]}
    if len(text) > _MAX_LOG_CHARS:
        return {"_truncated": True, "preview": text[:_MAX_LOG_CHARS]}
    return json.loads(text)


def write_tool_log(
    tool_name: str,
    input_params: dict | None,
    result,
    status: str,
    user_id=None,
) -> None:
    """Ghi 1 lần gọi tool của AI Agent vào agent_tool_logs (audit trail cho Admin).

    Dùng SESSION RIÊNG: việc ghi log không được đụng vào transaction của tool (tool
    có thể vừa commit hoặc vừa rollback). Nuốt mọi lỗi — log hỏng không được làm
    hỏng nghiệp vụ.
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        if isinstance(user_id, str):
            try:
                user_id = _uuid_mod.UUID(user_id)
            except ValueError:
                user_id = None
        db.add(models.AgentToolLog(
            user_id=user_id,
            tool_name=tool_name,
            input_params=_json_safe(input_params or {}),
            result=_json_safe(result),
            status=status,
        ))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def snapshot_diff(before: dict, after: dict) -> tuple[dict, dict]:
    """Rút ra CHỈ những trường thực sự đổi giữa 2 snapshot.

    Nhật ký kiểm toán chỉ có giá trị khi đọc được ngay "cái gì đã đổi"; nhồi cả
    object vào old_data/new_data khiến admin phải tự dò. Trả về (old, new) chỉ gồm
    các key có giá trị khác nhau — rỗng nghĩa là không có gì thay đổi.
    """
    old_d: dict = {}
    new_d: dict = {}
    for key in set(before) | set(after):
        b, a = before.get(key), after.get(key)
        if b != a:
            old_d[key] = b
            new_d[key] = a
    return old_d, new_d


def write_audit_log(
    db: Session,
    user_id,
    action: str,
    entity_type: str,
    entity_id=None,
    old_data: dict | None = None,
    new_data: dict | None = None,
) -> None:
    """Ghi 1 dòng vào audit_logs — "ai đã đổi gì, từ giá trị nào sang giá trị nào".

    Khác `write_system_log` (câu chữ tự do, để đọc): bảng này có cấu trúc để LỌC và
    ĐỐI CHIẾU — action/entity_type/entity_id tra cứu được, old_data/new_data giữ giá
    trị trước & sau. Chỉ gọi cho hành động nhạy cảm (đổi quyền, khóa tài khoản, ghi
    đè điểm AI, xóa dữ liệu tuyển dụng).

    KHÔNG BAO GIỜ truyền mật khẩu/hash vào old_data/new_data — dùng nhãn dạng
    "(đã đổi)" thay thế. Lỗi ghi log bị nuốt để không phá nghiệp vụ chính.
    """
    try:
        db.add(models.AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            old_data=_json_safe(old_data) if old_data is not None else None,
            new_data=_json_safe(new_data) if new_data is not None else None,
        ))
        db.commit()
    except Exception:  # noqa: BLE001 - log hỏng không được làm hỏng nghiệp vụ
        db.rollback()


def write_system_log(
    db: Session,
    module: str,
    message: str,
    level: str = "INFO",
    payload: dict | None = None,
) -> None:
    """Ghi 1 dòng vào system_logs (NFR-8: log login & hành động quản trị quan trọng).

    KHÔNG bao giờ để lỗi ghi log làm hỏng nghiệp vụ chính: nuốt mọi exception và
    rollback riêng phần log. Tự commit để log tồn tại độc lập với transaction gọi.
    """
    try:
        db.add(models.SystemLog(level=level, module=module, message=message, payload=payload))
        db.commit()
    except Exception:
        db.rollback()
