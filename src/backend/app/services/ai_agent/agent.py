"""
Agent loop (kiến trúc B): LLM là chương trình chính, tự chọn & gọi tool.

Dùng Groq function-calling (client OpenAI-compatible, cùng GROQ_API_KEY với
gemini_client). Khác generate_text() ở chỗ có truyền `tools=` và chạy NHIỀU vòng:
LLM -> gọi tool -> đưa kết quả lại -> LLM ... cho tới khi ra câu trả lời cuối.
"""

import inspect
import json
import os
import time

from groq import Groq
from sqlalchemy.orm import Session

from app.services.ai_agent.agent_tools import TOOLS, TOOL_FUNCS, USER_BOUND

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
AGENT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "6"))
# Model llama trên Groq thỉnh thoảng sinh cú pháp gọi tool sai -> 400 tool_use_failed.
# Đây là lỗi ngẫu nhiên, gọi lại thường qua được nên ta retry vài lần.
_LLM_RETRIES = int(os.getenv("AGENT_LLM_RETRIES", "3"))


def _complete(messages: list):
    """Gọi Groq (có tools), tự retry khi model sinh tool-call hỏng hoặc lỗi tạm thời."""
    last_err = None
    for attempt in range(_LLM_RETRIES):
        try:
            return _client.chat.completions.create(
                model=AGENT_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
            )
        except Exception as e:  # noqa: BLE001 - thử lại cho cả tool_use_failed lẫn 429/5xx
            last_err = e
            time.sleep(0.8 * (attempt + 1))
    raise last_err

SYSTEM_PROMPT = """Bạn là trợ lý tuyển dụng thông minh của hệ thống HireWise, hỗ trợ nhân viên HR.
Bạn CÓ các công cụ (tools) để tra cứu và thao tác dữ liệu tuyển dụng thật. Hãy CHỦ ĐỘNG gọi tool khi cần thay vì bịa thông tin.

Bạn còn ĐIỀU KHIỂN được giao diện bên phải qua các tool điều hướng: open_jd, open_dashboard, open_shortlisting.

Nguyên tắc:
- Muốn thao tác trên một JD/ứng viên nhưng chưa có ID: hãy dùng list_jds / search_candidates để tìm ID trước.
- Khi HR muốn "mở/xem/vào" một vị trí, một ứng viên, hay một màn hình: hãy gọi tool điều hướng phù hợp để giao diện bên phải nhảy tới đúng nơi (vd tìm JD bằng list_jds rồi open_jd).
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
    # Lọc bỏ tham số thừa mà LLM có thể bịa (llama hay kèm arg lạ, nhất là với tool
    # không có tham số) -> tránh TypeError làm tool điều hướng thất bại.
    try:
        sig = inspect.signature(fn)
        has_var_kw = any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
        if not has_var_kw:
            allowed = set(sig.parameters) - {"db"}
            args = {k: v for k, v in args.items() if k in allowed}
    except (TypeError, ValueError):
        pass
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
    ui_actions: list[dict] = []

    def _push_ui(action: dict) -> None:
        if action and action not in ui_actions:
            ui_actions.append(action)

    for _ in range(MAX_STEPS):
        try:
            resp = _complete(messages)
        except Exception as e:  # noqa: BLE001 - trả lời nhẹ nhàng thay vì 500
            return {
                "reply": "Xin lỗi, mình gặp trục trặc khi xử lý yêu cầu này. Bạn thử diễn đạt lại giúp mình nhé.",
                "tool_calls": used,
                "steps": steps,
                "ui_actions": ui_actions,
                "error": str(e),
            }
        msg = resp.choices[0].message

        # LLM không gọi tool nữa -> câu trả lời cuối cùng.
        if not msg.tool_calls:
            return {
                "reply": msg.content or "",
                "tool_calls": used,
                "steps": steps,
                "ui_actions": ui_actions,
            }

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
            if not isinstance(args, dict):
                args = {}
            result = _execute_tool(db, name, args, user_id)
            used.append(name)
            steps.append({"tool": name, "args": args, "result": result})

            # Gom directive điều hướng giao diện cho frontend.
            if isinstance(result, dict):
                if isinstance(result.get("ui_action"), dict):
                    _push_ui(result["ui_action"])
                # Tạo JD xong -> tự làm mới danh sách và mở vị trí mới ở bên phải.
                if name == "create_jd" and result.get("jd_id"):
                    _push_ui({"type": "refresh"})
                    _push_ui({"type": "navigate", "path": f"/projects/{result['jd_id']}"})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str, ensure_ascii=False),
            })

    return {
        "reply": "Xin lỗi, yêu cầu cần quá nhiều bước để xử lý. Bạn thử tách nhỏ giúp mình nhé.",
        "tool_calls": used,
        "steps": steps,
        "ui_actions": ui_actions,
    }
