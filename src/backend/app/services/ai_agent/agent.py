"""
Agent loop: LLM là chương trình chính, tự chọn & gọi tool.

LUỒNG CHÍNH ĐI QUA MCP:
    run_agent -> mcp_client (SSE) -> MCP server -> agent_tools -> DB
Danh sách tool KHÔNG còn hard-code: backend hỏi MCP server `list_tools()` rồi đưa
schema đó cho LLM; LLM chọn tool -> backend gọi `call_tool()` qua MCP.

FALLBACK: nếu MCP server không kết nối được, tự động quay về gọi thẳng hàm trong
agent_tools (in-process) để sản phẩm không chết giữa demo.
"""

import asyncio
import inspect
import json
import os
import time

from groq import Groq
from sqlalchemy.orm import Session

from app.services.ai_agent.agent_tools import TOOLS, TOOL_FUNCS, USER_BOUND
from app.services.ai_agent.mcp_client import (
    MCPUnavailable,
    call_tool,
    fetch_tools,
    mcp_session,
)
from app.services.logging import write_tool_log

_client = Groq(api_key=os.getenv("GROQ_MCP_API_KEY"))
AGENT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))
# Model llama trên Groq thỉnh thoảng sinh cú pháp gọi tool sai -> 400 tool_use_failed.
# Đây là lỗi ngẫu nhiên, gọi lại thường qua được nên ta retry vài lần.
_LLM_RETRIES = int(os.getenv("AGENT_LLM_RETRIES", "3"))


def _complete(messages: list, tools: list):
    """Gọi Groq (có tools), tự retry khi model sinh tool-call hỏng hoặc lỗi tạm thời."""
    last_err = None
    for attempt in range(_LLM_RETRIES):
        try:
            return _client.chat.completions.create(
                model=AGENT_MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
            )
        except Exception as e:  # noqa: BLE001 - thử lại cho cả tool_use_failed lẫn 429/5xx
            last_err = e
            time.sleep(0.8 * (attempt + 1))
    raise last_err


SYSTEM_PROMPT = """Bạn là trợ lý tuyển dụng thông minh của hệ thống HireWise, hỗ trợ nhân viên HR.
Bạn CÓ các công cụ (tools) để tra cứu và thao tác dữ liệu tuyển dụng thật. Hãy gọi tool khi yêu cầu của HR RÕ RÀNG cần đến tool, thay vì bịa thông tin.

Bạn còn ĐIỀU KHIỂN được giao diện bên phải qua các tool điều hướng: open_jd, open_dashboard, open_shortlisting.

QUAN TRỌNG — Khi nào KHÔNG gọi tool:
- Nếu tin nhắn MỚI NHẤT của HR là vô nghĩa (gõ phím lung tung như "hkbvnmbmn"), chỉ là lời chào, cảm ơn, hay câu nói chung chung KHÔNG nêu yêu cầu cụ thể: ĐỪNG gọi bất kỳ tool nào. Hãy hỏi lại HR muốn làm gì (vd: tạo JD, tìm ứng viên, so sánh, mở màn hình...).
- Khi không chắc HR muốn gì: hỏi lại cho rõ TRƯỚC, tuyệt đối không đoán rồi gọi tool.

Riêng về create_jd (tạo JD mới, GHI vào hệ thống):
- CHỈ gọi create_jd khi tin nhắn MỚI NHẤT của HR nêu RÕ ý định tuyển dụng cho MỘT vị trí cụ thể (có chức danh và/hoặc kỹ năng/yêu cầu). Ví dụ hợp lệ: "Tạo JD tuyển Backend Python 3 năm kinh nghiệm".
- raw_text truyền vào create_jd PHẢI lấy từ chính tin nhắn mới nhất của HR. TUYỆT ĐỐI KHÔNG tái sử dụng nội dung JD từ các tin nhắn/lượt trước để tạo JD mới — mỗi JD phải ứng với một yêu cầu mới, tường minh.
- Nếu HR chỉ gõ vài ký tự vô nghĩa hoặc chưa mô tả vị trí: KHÔNG tạo JD, hãy hỏi họ mô tả vị trí cần tuyển.

ID KỸ THUẬT LÀ CHUYỆN NỘI BỘ — HR KHÔNG BAO GIỜ ĐƯỢC THẤY:
- TUYỆT ĐỐI KHÔNG in UUID/ID ra câu trả lời. Sai: "JD có ID là 8ad393c2-9819-...". Đúng: "Đã tạo JD Backend Python."
- TUYỆT ĐỐI KHÔNG hỏi HR cung cấp jd_id / candidate_id. Các tool nhận cả TÊN (jd_id="Backend Developer", candidate_id="Nguyễn Minh Khoa") — hãy truyền tên.
- HR hỏi chung chung không nêu vị trí (vd "tìm người biết Python"): gọi search_candidates với skill="python" và BỎ TRỐNG jd_id để tìm xuyên mọi vị trí.
- Cần HR làm rõ thì hỏi bằng ngôn ngữ nghiệp vụ (tên vị trí, tên ứng viên), không hỏi ID.

VĂN PHONG TRẢ LỜI — NGẮN GỌN:
- Tối đa 1-2 câu. Chỉ nói KẾT QUẢ, không thuật lại các bước đã làm, không nhắc lại yêu cầu của HR.
- Không lặp lại chi tiết HR vừa gõ (kinh nghiệm, kỹ năng...), không thêm trạng thái thừa như 'đang ở trạng thái active'.
- Ví dụ tốt: "Đã tạo JD Backend Python và mở ra cho bạn." / "Tìm được 3 ứng viên biết Python, cao nhất là Nguyễn Minh Khoa (90)."

Nguyên tắc khác:
- Khi HR muốn "mở/xem/vào" một vị trí, một ứng viên, hay một màn hình: hãy gọi tool điều hướng phù hợp để giao diện nhảy tới đúng nơi.
- Không bao giờ bịa ID, điểm số, hay tên ứng viên. Chỉ nói những gì tool trả về.
- Với send_interview_invite (gửi email thật, không thu hồi được): PHẢI hỏi HR xác nhận và chỉ gửi (confirm=true) khi HR đồng ý rõ ràng.
- Luôn trả lời bằng tiếng Việt.
"""


# --------------------------------------------------------------------------- #
# Thực thi tool — đường FALLBACK (gọi thẳng hàm Python, không qua MCP)
# --------------------------------------------------------------------------- #
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
        result = fn(db, **args)
    except Exception as e:  # noqa: BLE001 - trả lỗi cho LLM để nó tự xử lý/thông báo
        result = {"error": f"{type(e).__name__}: {e}"}

    # Audit trail (đường MCP thì MCP server tự ghi, khỏi ghi 2 lần).
    failed = isinstance(result, dict) and "error" in result
    write_tool_log(
        tool_name=name,
        input_params=args,
        result=result,
        status="error" if failed else "success",
        user_id=user_id,
    )
    return result


# --------------------------------------------------------------------------- #
# Vòng lặp agent — dùng chung cho cả 2 đường, khác nhau ở `tools` và `execute`
# --------------------------------------------------------------------------- #
async def _agent_loop(messages: list, tools: list, execute) -> dict:
    """`execute`: async callable (name, args) -> dict kết quả tool."""
    used: list[str] = []
    steps: list[dict] = []
    ui_actions: list[dict] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def _push_ui(action: dict) -> None:
        if action and action not in ui_actions:
            ui_actions.append(action)

    def _out(reply: str, error: str | None = None) -> dict:
        d = {
            "reply": reply,
            "tool_calls": used,
            "steps": steps,
            "ui_actions": ui_actions,
            "usage": usage,
        }
        if error:
            d["error"] = error
        return d

    for _ in range(MAX_STEPS):
        try:
            resp = _complete(messages, tools)
        except Exception as e:  # noqa: BLE001 - trả lời nhẹ nhàng thay vì 500
            return _out(
                "Xin lỗi, mình gặp trục trặc khi xử lý yêu cầu này. Bạn thử diễn đạt lại giúp mình nhé.",
                error=str(e),
            )

        if getattr(resp, "usage", None):
            usage["prompt_tokens"] += resp.usage.prompt_tokens or 0
            usage["completion_tokens"] += resp.usage.completion_tokens or 0

        msg = resp.choices[0].message

        # LLM không gọi tool nữa -> câu trả lời cuối cùng.
        if not msg.tool_calls:
            return _out(msg.content or "")

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

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}

            result = await execute(name, args)
            used.append(name)
            steps.append({"tool": name, "args": args, "result": result})

            # Directive điều hướng giao diện cho frontend.
            if isinstance(result, dict):
                if isinstance(result.get("ui_action"), dict):
                    _push_ui(result["ui_action"])
                # Tạo JD xong -> làm mới danh sách và mở vị trí mới.
                if name == "create_jd" and result.get("jd_id"):
                    _push_ui({"type": "refresh"})
                    _push_ui({"type": "navigate", "path": f"/projects/{result['jd_id']}"})

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str, ensure_ascii=False),
            })

    return _out("Xin lỗi, yêu cầu cần quá nhiều bước để xử lý. Bạn thử tách nhỏ giúp mình nhé.")


async def _run_via_mcp(messages: list, user_id) -> dict:
    """Đường CHÍNH: tool lấy động từ MCP server và thực thi qua MCP."""
    async with mcp_session() as session:
        tools, names = await fetch_tools(session)

        async def execute(name: str, args: dict) -> dict:
            if name not in names:
                return {"error": f"Tool không tồn tại trên MCP server: {name}"}
            return await call_tool(session, name, args, acting_user_id=user_id)

        out = await _agent_loop(messages, tools, execute)
        out["mcp"] = True
        return out


async def _run_local(messages: list, db: Session, user_id) -> dict:
    """Đường FALLBACK: gọi thẳng agent_tools trong tiến trình."""

    async def execute(name: str, args: dict) -> dict:
        return _execute_tool(db, name, args, user_id)

    out = await _agent_loop(messages, TOOLS, execute)
    out["mcp"] = False
    return out


def run_agent(db: Session, message: str, user_id=None, history: list | None = None) -> dict:
    """
    Chạy 1 lượt hội thoại. Ưu tiên đi qua MCP; MCP chết thì fallback gọi tool nội bộ.

    Hàm này SYNC (router FastAPI sync chạy trong threadpool) nên dùng asyncio.run được.
    Phiên MCP + list_tools được mở TRƯỚC khi gọi LLM, nên nếu MCP hỏng ta fallback mà
    không tốn token nào.
    """
    def _messages() -> list:
        m = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            m += history
        m.append({"role": "user", "content": message})
        return m

    try:
        return asyncio.run(_run_via_mcp(_messages(), user_id))
    except MCPUnavailable as e:
        out = asyncio.run(_run_local(_messages(), db, user_id))
        out["mcp_error"] = str(e)
        return out
