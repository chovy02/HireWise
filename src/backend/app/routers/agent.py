import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.services.ai_agent.agent import run_agent
from app.services.ai_agent import chat_store

router = APIRouter(
    prefix="/agent",
    tags=["AI Agent"],
    dependencies=[Depends(require_role("hr_staff", "admin"))],
)


class PageContext(BaseModel):
    """Trang mà HR đang xem lúc gõ tin nhắn (frontend gửi lên, xem PageContext.jsx).

    CHỈ LÀ GỢI Ý, KHÔNG PHẢI QUYỀN. `jd_id` đi vào prompt để agent khỏi đoán vị trí,
    nhưng mọi tool vẫn lọc theo `owner_id` của HR đang đăng nhập — một jd_id giả gửi
    lên đây không mở được dữ liệu của tài khoản khác.

    Khai schema chặt (thay vì nhận `dict` bất kỳ) để nội dung client gửi lên không
    chảy tự do vào prompt của LLM.
    """

    page: str | None = None
    jd_id: uuid.UUID | None = None
    jd_title: str | None = Field(default=None, max_length=200)


class ChatRequest(BaseModel):
    message: str
    # Phiên chat. Bỏ trống ở lượt đầu -> backend tạo mới và trả session_id về.
    session_id: str | None = None
    context: PageContext | None = None


@router.post("/chat")
def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Điểm vào của AI Agent. Lịch sử hội thoại được LƯU và DỰNG LẠI TỪ DB (kèm kết quả
    tool của các lượt trước) thay vì tin vào history do frontend gửi lên — nhờ vậy
    agent nhớ đúng id/dữ liệu đã tra, không phải đoán.
    """
    session = chat_store.get_or_create_session(
        db, current_user.id, body.session_id, body.message
    )

    # Dựng history TRƯỚC khi lưu lượt hiện tại (run_agent tự nối message vào cuối).
    history = chat_store.build_history(db, session.id)
    chat_store.save_message(db, session.id, "hr_staff", body.message)

    out = run_agent(
        db,
        body.message,
        user_id=current_user.id,
        history=history,
        page_context=body.context.model_dump() if body.context else None,
    )

    usage = out.get("usage") or {}
    chat_store.save_message(
        db,
        session.id,
        "ai_agent",
        out.get("reply", ""),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
    )
    # Ghi chú kết quả tool -> lượt sau agent còn nhớ đúng UUID/dữ liệu.
    chat_store.save_tool_note(db, session.id, out.get("steps") or [])

    out["session_id"] = str(session.id)
    return out


# --------------------------------------------------------------------------- #
# Lịch sử hội thoại (panel History kiểu ChatGPT/Claude)
# --------------------------------------------------------------------------- #
@router.get("/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Danh sách phiên chat của HR đang đăng nhập (mới nhất trước)."""
    return chat_store.list_sessions(db, current_user.id)


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Nội dung 1 phiên chat để mở lại (chỉ message hiển thị, bỏ ghi chú tool)."""
    messages = chat_store.get_session_messages(db, session_id, current_user.id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện.")
    return {"session_id": session_id, "messages": messages}


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Xoá 1 phiên chat."""
    if not chat_store.delete_session(db, session_id, current_user.id):
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện.")
