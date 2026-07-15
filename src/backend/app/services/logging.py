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
