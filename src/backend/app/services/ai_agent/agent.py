"""
Agent loop: LLM là chương trình chính, tự chọn & gọi tool.

LUỒNG CHÍNH ĐI QUA MCP:
    run_agent -> mcp_client (Streamable HTTP) -> MCP server -> agent_tools -> DB
Danh sách tool KHÔNG hard-code: backend hỏi MCP server `list_tools()` rồi đưa schema
đó cho LLM; LLM chọn tool -> backend gọi `call_tool()` qua MCP.

FALLBACK: nếu MCP server không kết nối được, tự động quay về gọi thẳng hàm trong
agent_tools (in-process) để sản phẩm không chết giữa demo. Schema của đường fallback
sinh từ CÙNG `tool_registry` mà MCP server dùng, nên LLM thấy y hệt nhau ở hai đường.

FALLBACK GIỮA LƯỢT: nếu MCP chết SAU khi một tool GHI đã chạy xong, ta KHÔNG chạy lại
cả lượt — làm vậy sẽ tạo JD lần hai, gửi email lần hai. Trường hợp đó báo lỗi trung
thực cho HR thay vì âm thầm nhân đôi tác dụng phụ.
"""

import asyncio
import inspect
import json
import logging
import os
import re
import time

from groq import Groq
from sqlalchemy.orm import Session

from app.services.ai_agent.tool_registry import SPECS, llm_tool_schemas
from app.services.ai_agent.mcp_client import (
    MCPUnavailable,
    call_tool,
    fetch_tools,
    mcp_session,
)
from app.services.logging import write_tool_log
from app.services.ai_agent.gemini_client import record_ai_log

log = logging.getLogger(__name__)

_client = Groq(api_key=os.getenv("GROQ_MCP_API_KEY"))
AGENT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Model dự phòng khi model chính CẠN HẠN MỨC NGÀY (TPD).
#
# Groq tính TPD theo TỪNG MODEL và theo ORGANIZATION — không theo API key. Nghĩa là
# đổi sang một key khác trong cùng tài khoản KHÔNG hồi phục được hạn mức (đã kiểm
# chứng: 3 key của dự án báo về cùng một số dư). Thứ thực sự còn hạn mức là một MODEL
# khác. Hết 70b thì hạ xuống model khác còn hơn là ném cho HR câu "gặp trục trặc".
#
# THỨ TỰ QUAN TRỌNG: xếp theo NĂNG LỰC GỌI TOOL giảm dần, không phải theo tốc độ.
# Đã thử `llama-3.1-8b-instant` đứng đầu: nó bịa ra ứng viên không tồn tại ("Trần Văn
# A", "Nguyễn Thị B") thay vì dùng kết quả search vừa nhận. Một agent thao tác dữ liệu
# thật mà bịa tham số thì tệ hơn hẳn việc báo lỗi thẳng, nên model yếu để cuối cùng.
_FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv("GROQ_FALLBACK_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b").split(",")
    if m.strip()
]
_MODEL_CHAIN = [AGENT_MODEL] + [m for m in _FALLBACK_MODELS if m != AGENT_MODEL]
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))
# Model llama trên Groq thỉnh thoảng sinh cú pháp gọi tool sai -> 400 tool_use_failed.
# Đây là lỗi ngẫu nhiên, gọi lại thường qua được nên ta retry vài lần.
_LLM_RETRIES = int(os.getenv("AGENT_LLM_RETRIES", "3"))


# Trần độ dài prompt ghi vào ai_logs: hội thoại nhiều lượt kèm kết quả tool có thể
# rất dài, không đáng để phình bảng log.
_LOG_PROMPT_CHARS = 8000


def _prompt_for_log(messages: list) -> str:
    try:
        text = json.dumps(messages, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        text = str(messages)
    return text[:_LOG_PROMPT_CHARS]


def _completion_for_log(resp) -> str:
    """Nội dung trả lời + tên tool mà model quyết định gọi (nếu có).

    Lượt agent thường trả content rỗng và chỉ chứa tool_calls; nếu chỉ ghi content
    thì trang Giám sát AI hiện một dòng trống, mất đúng thông tin đáng xem nhất.
    """
    try:
        msg = resp.choices[0].message
        parts = []
        if getattr(msg, "content", None):
            parts.append(msg.content)
        calls = getattr(msg, "tool_calls", None)
        if calls:
            parts.append("[tool_calls] " + ", ".join(c.function.name for c in calls))
        return "\n".join(parts)
    except Exception:  # noqa: BLE001
        return ""


def _is_quota_error(err: Exception) -> bool:
    """Lỗi này là do CẠN HẠN MỨC nhà cung cấp (429), không phải lỗi lập trình."""
    text = str(err).lower()
    return "rate_limit" in text or "rate limit" in text or "error code: 429" in text


def _quota_wait_hint(err: Exception) -> str:
    """Rút thời gian chờ mà Groq gợi ý ('try again in 34m45.6s') thành lời người đọc."""
    m = re.search(r"try again in\s+(?:(\d+)m)?([\d.]+)s", str(err), re.IGNORECASE)
    if not m:
        return ""
    phut = int(m.group(1) or 0)
    if phut >= 1:
        return f" Hạn mức sẽ mở lại sau khoảng {phut} phút."
    return " Bạn thử lại sau ít phút nhé."


def _friendly_error(err: Exception) -> str:
    """Câu trả lời cho HR khi lượt LLM thất bại.

    Trước đây mọi lỗi đều thành "mình gặp trục trặc, bạn thử diễn đạt lại" — với lỗi
    cạn hạn mức thì đó là lời khuyên SAI: diễn đạt lại bao nhiêu lần cũng hỏng, mà HR
    lại tưởng do mình gõ chưa rõ.
    """
    if _is_quota_error(err):
        return (
            "Hệ thống đã dùng hết hạn mức AI cho hôm nay nên mình chưa xử lý được yêu cầu "
            "này." + _quota_wait_hint(err)
        )
    return "Xin lỗi, mình gặp trục trặc khi xử lý yêu cầu này. Bạn thử diễn đạt lại giúp mình nhé."


def _complete_sync(messages: list, tools: list):
    """Gọi Groq (có tools), tự retry khi model sinh tool-call hỏng hoặc lỗi tạm thời.

    Mọi lượt gọi đều ghi vào ai_logs như các agent khác: agent chat đi thẳng qua
    Groq chứ không qua `generate_text`, nên nếu không ghi ở đây thì phần token/độ
    trễ tốn nhiều nhất của hệ thống lại vô hình với trang Giám sát AI.
    """
    last_err = None
    start = time.time()
    for model in _MODEL_CHAIN:
        for attempt in range(_LLM_RETRIES):
            try:
                # Temperature TĂNG DẦN qua các lần thử. Với temperature cố định, một
                # prompt làm llama sinh cú pháp tool-call hỏng (`tool_use_failed`) sẽ
                # sinh ra đúng chuỗi hỏng đó ở cả 3 lần retry — retry thành vô nghĩa,
                # và HR nhận câu "mình gặp trục trặc" một cách rất ổn định. Nới ngẫu
                # nhiên để lần thử sau thực sự là một lần thử KHÁC.
                resp = _client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.2 + 0.3 * attempt,
                )
                completion = _completion_for_log(resp)
                if model != AGENT_MODEL:
                    completion = f"[model dự phòng: {model}]\n{completion}"
                record_ai_log(
                    agent_name="copilot_agent",
                    prompt=_prompt_for_log(messages),
                    completion=completion,
                    total_tokens=getattr(getattr(resp, "usage", None), "total_tokens", 0) or 0,
                    latency_ms=(time.time() - start) * 1000,
                    is_error=False,
                    error_message=None,
                )
                return resp
            except Exception as e:  # noqa: BLE001 - cả tool_use_failed lẫn 429/5xx
                last_err = e
                if _is_quota_error(e):
                    # Hết hạn mức thì thử lại CÙNG model chỉ tốn thêm thời gian chờ —
                    # hạn mức không hồi phục trong vài giây. Sang model khác ngay.
                    log.warning("Model %s hết hạn mức, chuyển model dự phòng: %s", model, e)
                    break
                time.sleep(0.8 * (attempt + 1))

    # Hết lượt retry -> ghi 1 dòng lỗi rồi mới ném ra.
    record_ai_log(
        agent_name="copilot_agent",
        prompt=_prompt_for_log(messages),
        completion=None,
        total_tokens=0,
        latency_ms=(time.time() - start) * 1000,
        is_error=True,
        error_message=str(last_err),
    )
    raise last_err


async def _complete(messages: list, tools: list):
    """Gọi Groq mà KHÔNG chặn event loop.

    SDK Groq là đồng bộ, `record_ai_log` ghi DB đồng bộ, và `_complete_sync` còn
    `time.sleep` tới ~4.8s giữa các lần retry. Gọi thẳng trong vòng lặp agent thì suốt
    thời gian đó event loop đứng im — kể cả tác vụ nền đang giữ luồng SSE của transport
    MCP. Hệ quả quan sát được: một lượt LLM chậm hoặc phải retry làm phiên MCP đứt
    (`anyio.BrokenResourceError`) ở lần gọi tool kế tiếp, dù server vẫn hoàn toàn khoẻ.
    Đẩy sang thread thì loop rảnh để nuôi transport.
    """
    return await asyncio.to_thread(_complete_sync, messages, tools)


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

LÀM VIỆC THEO LÔ — RẤT QUAN TRỌNG:
- HR nói "tất cả những người...", "mỗi người...", "nhóm trên X điểm": TRƯỚC HẾT gọi search_candidates một lần để lấy danh sách, RỒI truyền TẤT CẢ tên đó vào MỘT lời gọi tool (add_to_shortlist, generate_interview_questions đều nhận candidate_ids là DANH SÁCH).
- TUYỆT ĐỐI KHÔNG gọi cùng một tool lặp đi lặp lại cho từng người. Làm vậy vừa chậm, vừa dễ hết hạn mức giữa chừng và bỏ sót người.
- HR nêu con số cụ thể (vd "mỗi người 3 câu hỏi"): PHẢI truyền num_questions=3, đừng để mặc định.

VĂN PHONG TRẢ LỜI — NGẮN GỌN:
- Tối đa 1-2 câu. Chỉ nói KẾT QUẢ, không thuật lại các bước đã làm, không nhắc lại yêu cầu của HR.
- Không lặp lại chi tiết HR vừa gõ (kinh nghiệm, kỹ năng...), không thêm trạng thái thừa như 'đang ở trạng thái active'.
- Ví dụ tốt: "Đã tạo JD Backend Python và mở ra cho bạn." / "Tìm được 3 ứng viên biết Python, cao nhất là Nguyễn Minh Khoa (90)."

Nguyên tắc khác:
- Khi HR muốn "mở/xem/vào" một vị trí, một ứng viên, hay một màn hình: hãy gọi tool điều hướng phù hợp để giao diện nhảy tới đúng nơi.
- Không bao giờ bịa ID, điểm số, hay tên ứng viên. Chỉ nói những gì tool trả về.
- Với send_interview_invite (gửi email thật, không thu hồi được): PHẢI hỏi HR xác nhận và chỉ gửi (confirm=true) khi HR đồng ý rõ ràng.
- Nếu một tool trả về error="needs_confirmation": ĐỪNG gọi lại ngay. Hãy nói cho HR biết rủi ro trong trường "message" rồi chờ họ đồng ý, sau đó mới gọi lại kèm cờ xác nhận.
- Luôn trả lời bằng tiếng Việt.
"""


# --------------------------------------------------------------------------- #
# Thực thi tool — đường FALLBACK (gọi thẳng hàm Python, không qua MCP)
# --------------------------------------------------------------------------- #
def _execute_tool(db: Session, name: str, args: dict, user_id) -> dict:
    spec = SPECS.get(name)
    if spec is None:
        return {"error": f"Tool không tồn tại: {name}"}
    fn = spec.fn
    # Tiêm user_id cho các tool cần (LLM không được tự điền).
    if spec.user_bound:
        args[spec.user_bound] = str(user_id)
    # Phạm vi dữ liệu: mọi tool chỉ được thấy JD/ứng viên của HR đang đăng nhập.
    # GHI ĐÈ chứ không setdefault — owner_id không nằm trong schema đưa cho LLM, nên
    # nếu nó vẫn bịa ra một giá trị thì đó là mưu toan đọc dữ liệu tài khoản khác.
    args["owner_id"] = str(user_id)
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
        if not isinstance(result, dict):  # giao kèo: tool luôn trả dict
            result = {"result": result}
    except Exception as e:  # noqa: BLE001 - trả lỗi cho LLM để nó tự xử lý/thông báo
        db.rollback()
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
# Trần độ dài kết quả tool ghi vào `steps`. `steps` đi ra frontend VÀ được lưu làm
# "trí nhớ" của agent cho lượt sau (chat_store). Một kết quả compare_candidates hay
# get_jd đầy đủ dễ chiếm trọn hạn mức ghi chú, đẩy id của các tool khác ra ngoài.
_STEP_RESULT_CHARS = 1500


def _trim_step_result(result):
    """Cắt bớt kết quả tool trước khi ghi vào `steps` (không đụng bản gửi cho LLM)."""
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {"_unserializable": str(result)[:200]}
    if len(text) <= _STEP_RESULT_CHARS:
        return result
    return {"_truncated": True, "preview": text[:_STEP_RESULT_CHARS]}


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
            resp = await _complete(messages, tools)
        except Exception as e:  # noqa: BLE001 - trả lời nhẹ nhàng thay vì 500
            return _out(_friendly_error(e), error=str(e))

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
            steps.append({"tool": name, "args": args, "result": _trim_step_result(result)})

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

        # Các tool GHI đã chạy XONG trong lượt này. Nếu MCP chết sau đó, chạy lại cả
        # lượt ở đường fallback sẽ lặp lại đúng những tác dụng phụ này -> không được.
        applied: list[str] = []

        async def execute(name: str, args: dict) -> dict:
            if name not in names:
                return {"error": f"Tool không tồn tại trên MCP server: {name}"}
            result = await call_tool(session, name, args, acting_user_id=user_id)
            spec = SPECS.get(name)
            if spec and not spec.read_only and not (isinstance(result, dict) and "error" in result):
                applied.append(name)
            return result

        try:
            out = await _agent_loop(messages, tools, execute)
        except MCPUnavailable as e:
            e.applied_tools = applied  # để run_agent quyết định có fallback được không
            raise
        out["mcp"] = True
        return out


async def _run_local(messages: list, db: Session, user_id) -> dict:
    """Đường FALLBACK: gọi thẳng agent_tools trong tiến trình."""

    async def execute(name: str, args: dict) -> dict:
        return _execute_tool(db, name, args, user_id)

    out = await _agent_loop(messages, llm_tool_schemas(), execute)
    out["mcp"] = False
    return out


def run_agent(db: Session, message: str, user_id=None, history: list | None = None) -> dict:
    """
    Chạy 1 lượt hội thoại. Ưu tiên đi qua MCP; MCP chết thì fallback gọi tool nội bộ.

    Hàm này SYNC (router FastAPI sync chạy trong threadpool) nên dùng asyncio.run được.
    Phiên MCP + list_tools được mở TRƯỚC khi gọi LLM, nên nếu MCP hỏng ngay từ đầu ta
    fallback mà không tốn token nào.
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
        applied = getattr(e, "applied_tools", None) or []
        if applied:
            # Đã có tool GHI chạy xong rồi mới mất kết nối. Chạy lại lượt này sẽ tạo
            # JD lần hai / gửi email lần hai. Thà báo thật để HR kiểm tra lại.
            return {
                "reply": (
                    "Mình đã thực hiện xong thao tác nhưng mất kết nối trước khi tổng hợp "
                    "câu trả lời. Bạn kiểm tra lại trên màn hình giúp mình, đừng gửi lại "
                    "yêu cầu để tránh bị lặp."
                ),
                "tool_calls": applied,
                "steps": [],
                "ui_actions": [{"type": "refresh"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                "mcp": True,
                "error": str(e),
                "mcp_error": str(e),
            }
        out = asyncio.run(_run_local(_messages(), db, user_id))
        out["mcp_error"] = str(e)
        return out
