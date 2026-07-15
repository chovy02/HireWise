"""
Lưu & dựng lại hội thoại của AI Copilot (bảng chat_sessions / chat_messages).

Trước đây lịch sử chat chỉ nằm trong React state và được gửi lại mỗi lượt — nên chỉ
còn phần TEXT, mất sạch kết quả tool (UUID ứng viên, điểm...). Hậu quả: agent "quên"
và phải đoán/bịa ID ở lượt sau.

Ở đây ta lưu 3 loại message:
  - hr_staff  -> lượt người dùng
  - ai_agent  -> câu trả lời cuối của agent
  - system    -> GHI CHÚ KẾT QUẢ TOOL của lượt đó (JSON rút gọn), để lượt sau agent
                 còn nhớ đúng ID/dữ liệu đã tra được.
"""

import json
import uuid

from sqlalchemy.orm import Session

from app import models

# Số message gần nhất nạp lại làm ngữ cảnh (giữ token trong tầm kiểm soát).
_HISTORY_LIMIT = 14
# Trần độ dài ghi chú kết quả tool cho MỖI lượt.
_TOOL_NOTE_MAX = 2500

_TOOL_NOTE_PREFIX = (
    "[Kết quả tool ở lượt trước — HÃY DÙNG ĐÚNG các id/tên dưới đây, TUYỆT ĐỐI KHÔNG bịa id mới]:\n"
)


def get_or_create_session(
    db: Session, user_id, session_id: str | None, first_message: str
) -> models.ChatSession:
    """Lấy phiên chat theo id (nếu đúng của user), không có thì tạo phiên mới."""
    if session_id:
        try:
            s = db.get(models.ChatSession, uuid.UUID(str(session_id)))
        except (ValueError, AttributeError, TypeError):
            s = None
        if s is not None and s.user_id == user_id:
            return s

    title = (first_message or "Cuộc trò chuyện").strip()[:60]
    s = models.ChatSession(user_id=user_id, title=title)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def save_message(
    db: Session,
    session_id,
    sender_role: str,
    content: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    """Lưu 1 message. Không để lỗi lưu log làm hỏng câu trả lời cho user."""
    try:
        db.add(models.ChatMessage(
            session_id=session_id,
            sender_role=sender_role,
            content=content or "",
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
        ))
        db.commit()
    except Exception:
        db.rollback()


def save_tool_note(db: Session, session_id, steps: list[dict]) -> None:
    """Lưu kết quả tool của lượt này dưới dạng message 'system' (rút gọn)."""
    if not steps:
        return
    digest = [
        {"tool": s.get("tool"), "args": s.get("args"), "result": s.get("result")}
        for s in steps
    ]
    try:
        text = json.dumps(digest, default=str, ensure_ascii=False)
    except Exception:
        return
    save_message(db, session_id, "system", text[:_TOOL_NOTE_MAX])


def list_sessions(db: Session, user_id) -> list[dict]:
    """Danh sách phiên chat của user (mới nhất trước) — cho panel Lịch sử."""
    rows = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.user_id == user_id)
        .order_by(models.ChatSession.created_at.desc())
        .all()
    )
    return [
        {
            "session_id": str(s.id),
            "title": s.title or "Cuộc trò chuyện",
            "created_at": s.created_at,
        }
        for s in rows
    ]


def get_session_messages(db: Session, session_id, user_id) -> list[dict] | None:
    """
    Các message HIỂN THỊ của 1 phiên (chỉ hr_staff + ai_agent). Message 'system' là
    ghi chú kết quả tool dùng cho trí nhớ của agent -> KHÔNG trả về cho UI.
    Trả None nếu phiên không tồn tại hoặc không thuộc user (chống xem trộm).
    """
    try:
        s = db.get(models.ChatSession, uuid.UUID(str(session_id)))
    except (ValueError, AttributeError, TypeError):
        return None
    if s is None or s.user_id != user_id:
        return None

    rows = (
        db.query(models.ChatMessage)
        .filter(
            models.ChatMessage.session_id == s.id,
            models.ChatMessage.sender_role.in_(("hr_staff", "ai_agent")),
        )
        .order_by(models.ChatMessage.created_at)
        .all()
    )
    return [
        {
            "role": "user" if m.sender_role == "hr_staff" else "ai",
            "text": m.content,
            "created_at": m.created_at,
        }
        for m in rows
    ]


def delete_session(db: Session, session_id, user_id) -> bool:
    """Xoá 1 phiên chat (kèm message nhờ cascade). False nếu không phải của user."""
    try:
        s = db.get(models.ChatSession, uuid.UUID(str(session_id)))
    except (ValueError, AttributeError, TypeError):
        return False
    if s is None or s.user_id != user_id:
        return False
    db.delete(s)
    db.commit()
    return True


def build_history(db: Session, session_id) -> list[dict]:
    """
    Dựng lại history cho LLM từ DB (KHÔNG gồm lượt hiện tại — gọi hàm này TRƯỚC khi
    lưu message mới). Ghi chú tool được đưa vào dưới role 'system' để agent nhớ đúng
    id đã tra ở lượt trước.
    """
    rows = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.created_at.desc())
        .limit(_HISTORY_LIMIT)
        .all()
    )
    rows.reverse()  # về lại thứ tự thời gian tăng dần

    history: list[dict] = []
    for m in rows:
        if m.sender_role == "hr_staff":
            history.append({"role": "user", "content": m.content})
        elif m.sender_role == "ai_agent":
            history.append({"role": "assistant", "content": m.content})
        elif m.sender_role == "system":
            history.append({"role": "system", "content": _TOOL_NOTE_PREFIX + m.content})
    return history
