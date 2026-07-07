from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.services.ai_agent.agent import run_agent

router = APIRouter(
    prefix="/agent",
    tags=["AI Agent"],
    dependencies=[Depends(require_role("hr_staff", "admin"))],
)


class ChatRequest(BaseModel):
    message: str
    history: list | None = None  # [{role, content}, ...] nếu muốn nối phiên


@router.post("/chat")
def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Điểm vào của AI Agent (kiến trúc B). HR gửi 1 câu, agent tự chọn & gọi tool,
    trả về câu trả lời + danh sách tool đã dùng.
    """
    return run_agent(db, body.message, user_id=current_user.id, history=body.history)
