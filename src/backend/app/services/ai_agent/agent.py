"""
Agent loop (kiến trúc B): LLM là chương trình chính, tự chọn & gọi tool.

Dùng Groq function-calling (client OpenAI-compatible, cùng GROQ_API_KEY với
gemini_client). Khác generate_text() ở chỗ có truyền `tools=` và chạy NHIỀU vòng:
LLM -> gọi tool -> đưa kết quả lại -> LLM ... cho tới khi ra câu trả lời cuối.
"""

import json
import os

from groq import Groq
from sqlalchemy.orm import Session

from app.services.ai_agent.agent_tools import TOOLS, TOOL_FUNCS, USER_BOUND

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
AGENT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "6"))

SYSTEM_PROMPT = """Bạn là trợ lý tuyển dụng thông minh của hệ thống HireWise, hỗ trợ nhân viên HR.
Bạn CÓ các công cụ (tools) để tra cứu và thao tác dữ liệu tuyển dụng thật. Hãy CHỦ ĐỘNG gọi tool khi cần thay vì bịa thông tin.

Nguyên tắc:
- Muốn thao tác trên một JD/ứng viên nhưng chưa có ID: hãy dùng list_jds / search_candidates để tìm ID trước.
- Không bao giờ bịa ID, điểm số, hay tên ứng viên. Chỉ nói những gì tool trả về.
- Với send_interview_invite (gửi email thật, không thu hồi được): PHẢI hỏi HR xác nhận và chỉ gửi (confirm=true) khi HR đồng ý rõ ràng.
- Trả lời cuối cùng bằng tiếng Việt, ngắn gọn, đi thẳng vào việc.
"""


def _execute_tool(db: Session, name: str, args: dict, user_id) -> dict:
    fn = TOOL_FUNCS.get(name)
    if fn is None:
        return {"error": f"Tool không tồn tại: {name}"}
    # Tiêm user_id cho các tool cần (LLM không được tự điền).
    if name in USER_BOUND:
        args[USER_BOUND[name]] = str(user_id)
    try:
        return fn(db, **args)
    except Exception as e:  # noqa: BLE001 - trả lỗi cho LLM để nó tự xử lý/thông báo
        return {"error": f"{type(e).__name__}: {e}"}


def run_agent(db: Session, message: str, user_id=None, history: list | None = None) -> dict:
    """
    Chạy 1 lượt hội thoại. Trả về:
      { "reply": str, "tool_calls": [tên tool đã dùng], "steps": [chi tiết để debug] }
    `history`: danh sách message trước đó (đã ở dạng dict role/content) nếu muốn nối phiên.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages += history
    messages.append({"role": "user", "content": message})

    used: list[str] = []
    steps: list[dict] = []

    for _ in range(MAX_STEPS):
        resp = _client.chat.completions.create(
            model=AGENT_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
        )
        msg = resp.choices[0].message

        # LLM không gọi tool nữa -> câu trả lời cuối cùng.
        if not msg.tool_calls:
            return {"reply": msg.content or "", "tool_calls": used, "steps": steps}

        # Ghi lại lượt assistant (kèm yêu cầu gọi tool) vào lịch sử.
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ],
        })

        # Chạy từng tool và trả kết quả về cho LLM.
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _execute_tool(db, name, args, user_id)
            used.append(name)
            steps.append({"tool": name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str, ensure_ascii=False),
            })

    return {
        "reply": "Xin lỗi, yêu cầu cần quá nhiều bước để xử lý. Bạn thử tách nhỏ giúp mình nhé.",
        "tool_calls": used,
        "steps": steps,
    }
