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


def _friendly_error(err: Exception, da_lam: list[str] | None = None) -> str:
    """Câu trả lời cho HR khi lượt LLM thất bại.

    Trước đây mọi lỗi đều thành "mình gặp trục trặc, bạn thử diễn đạt lại" — với lỗi
    cạn hạn mức thì đó là lời khuyên SAI: diễn đạt lại bao nhiêu lần cũng hỏng, mà HR
    lại tưởng do mình gõ chưa rõ.

    `da_lam` = tên các tool GHI đã chạy XONG trong lượt này. BẮT BUỘC phải nói ra.
    Lỗi thật đã gặp: HR gõ "lấy 4 người cao nhất bỏ vào shortlist, mỗi người 3 câu
    hỏi"; tool thêm shortlist xong, sinh câu hỏi xong, rồi tới lượt gọi LLM CUỐI (để
    viết câu trả lời) mới cạn hạn mức. Câu xin lỗi chung chung khiến HR đọc xong tưởng
    chưa có gì, gõ lại lần nữa — và lần này hệ thống làm thật lần hai.
    """
    het_han_muc = _is_quota_error(err)
    goi_y = _quota_wait_hint(err) if het_han_muc else ""

    if da_lam:
        # Tên tiếng Việt lấy từ chính registry (`title`), khử trùng nhưng giữ thứ tự
        # đã làm — HR đọc là hình dung được đúng những gì vừa xảy ra với dữ liệu.
        viec = ", ".join(dict.fromkeys(SPECS[t].title.lower() for t in da_lam if t in SPECS))
        ly_do = ("hệ thống hết hạn mức AI cho hôm nay" if het_han_muc
                 else "mình gặp trục trặc kỹ thuật")
        return (
            f"Mình ĐÃ kịp thực hiện: {viec}. Nhưng {ly_do} nên chưa tổng hợp được câu "
            f"trả lời. Bạn kiểm tra lại trên màn hình giúp mình, ĐỪNG gửi lại yêu cầu "
            f"để tránh bị làm hai lần.{goi_y}"
        )

    if het_han_muc:
        return (
            "Hệ thống đã dùng hết hạn mức AI cho hôm nay nên mình chưa xử lý được yêu "
            f"cầu này.{goi_y}"
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
- TUYỆT ĐỐI KHÔNG hỏi HR cung cấp jd_id / candidate_id. Tool nhận cả tên, nhưng tên đó phải là tên THẬT vừa thấy trong kết quả tool hoặc do HR gõ — ưu tiên id mà tool vừa trả về, chính xác hơn tên.
- Cần HR làm rõ thì hỏi bằng ngôn ngữ nghiệp vụ (tên vị trí, tên ứng viên), không hỏi ID.

YÊU CẦU KHÔNG NÊU VỊ TRÍ — LÀM ĐÚNG THEO THỨ TỰ NÀY, KHÔNG ĐƯỢC BỎ QUA BƯỚC 1:
1. CÓ "NGỮ CẢNH GIAO DIỆN" trong hội thoại (HR đang mở một vị trí)? -> BẮT BUỘC truyền jd_id chính là id đó vào search_candidates / compare_candidates. HR đang nhìn màn hình vị trí đó nên "4 người cao nhất" LUÔN có nghĩa là 4 người cao nhất CỦA VỊ TRÍ ĐANG MỞ. Bỏ trống jd_id ở đây là SAI NGHIÊM TRỌNG: nó gom cả ứng viên của những vị trí khác, và các tool sau (add_to_shortlist, generate_interview_questions) sẽ thao tác lan sang những vị trí HR không hề mở.
2. KHÔNG có ngữ cảnh giao diện, mà HR hỏi kiểu tra cứu chung ("tìm người biết Python", "ai điểm trên 80"): bỏ trống jd_id để tìm xuyên mọi vị trí.
3. KHÔNG có ngữ cảnh giao diện, mà HR yêu cầu HÀNH ĐỘNG (thêm vào shortlist, tạo câu hỏi, chốt nhận/loại) nhưng không nêu vị trí: gọi list_jds rồi HỎI LẠI HR làm cho vị trí nào. Đừng tự chọn, và đừng làm cho tất cả.
- HR nói rõ một vị trí khác, hoặc nói "tất cả vị trí"/"mọi vị trí": làm theo HR, ngữ cảnh giao diện nhường chỗ.

KHÔNG BAO GIỜ TỰ NGHĨ RA TÊN HAY ID — QUY TẮC QUAN TRỌNG NHẤT:
- Mọi candidate_id/tên ứng viên bạn truyền vào tool PHẢI lấy nguyên văn từ kết quả một tool đã gọi TRONG hội thoại này (thường là search_candidates), hoặc do chính HR gõ ra.
- TUYỆT ĐỐI KHÔNG dùng tên mẫu/giữ chỗ như "Nguyễn Văn A", "Trần Thị B", "Ứng viên 1". Chưa biết ai thì gọi search_candidates để biết, đừng điền tạm.
- Một tool vừa báo lỗi KHÔNG cho phép bạn đoán tiếp. Hãy ĐỌC thông báo lỗi: nó thường liệt kê sẵn các vị trí/ứng viên có thật. Dùng đúng dữ liệu đó rồi gọi lại.
- Nếu tool trả về error kèm "not_found": KHÔNG có gì được thực hiện cả. Đừng nói với HR là đã xong.

LÀM VIỆC THEO LÔ — RẤT QUAN TRỌNG:
- HR nói "tất cả những người...", "mỗi người...", "nhóm trên X điểm": TRƯỚC HẾT gọi search_candidates một lần để lấy danh sách, RỒI truyền TẤT CẢ tên đó vào MỘT lời gọi tool (add_to_shortlist, generate_interview_questions đều nhận candidate_ids là DANH SÁCH).
- HR nói "N người điểm cao nhất" / "top N": gọi search_candidates với limit=N (kết quả ĐÃ sắp theo điểm giảm dần), rồi CHÉP NGUYÊN mảng candidate_ids trong kết quả sang các tool tiếp theo. Đừng dùng compare_candidates để lấy danh sách — nó chỉ để so sánh.
- HR nói "N người điểm THẤP nhất" / "kém nhất" / "cuối bảng": gọi search_candidates với order="asc" và limit=N. ĐỪNG lấy danh sách giảm dần rồi tự chọn ra mấy người cuối, và đừng hỏi HR tên từng người — tool làm được việc này.
- "Điểm" mặc định là ĐIỂM SÀNG LỌC CV (thang 100, từ search_candidates). Chỉ khi HR nói rõ "điểm phỏng vấn" thì mới dùng list_interview_results (thang 10).
- TUYỆT ĐỐI KHÔNG gọi cùng một tool lặp đi lặp lại cho từng người. Làm vậy vừa chậm, vừa dễ hết hạn mức giữa chừng và bỏ sót người.
- HR nêu con số cụ thể (vd "mỗi người 3 câu hỏi"): PHẢI truyền num_questions=3, đừng để mặc định.

SAU PHỎNG VẤN — ĐI ĐÚNG THỨ TỰ NÀY:
- HR thuật lại ứng viên trả lời thế nào: gọi get_interview TRƯỚC để lấy danh sách câu hỏi có đánh số, rồi record_interview_answers với answers xếp ĐÚNG theo thứ tự đó (câu HR không nhắc tới thì để chuỗi rỗng ở đúng vị trí, đừng dồn lên). AI sẽ tự chấm điểm từng câu.
- Chấm xong, HR muốn đóng buổi phỏng vấn: finish_interview (mặc định chỉ xem trước; HR đồng ý thì gọi lại confirm=true).
- HR hỏi "ai phỏng vấn trên X điểm", "điểm trung bình": dùng list_interview_results, KHÔNG dùng search_candidates. Điểm phỏng vấn thang 10, điểm sàng lọc CV thang 100 — nhầm thang là chốt nhầm người.
- HR nói "đồng ý/nhận/loại/từ chối những người ...": set_candidate_decision (chỉ GHI quyết định, ứng viên chưa biết gì), rồi send_decision_emails để báo cho họ.
- send_decision_emails gửi thư THẬT, không thu hồi được: gọi lần đầu KHÔNG có confirm để lấy bản xem trước, đọc cho HR nghe sẽ gửi cho ai, rồi mới gọi lại với confirm=true khi HR đồng ý.
- Yêu cầu gộp kiểu "chốt nhận và gửi mail cho người trên 7 điểm" vẫn phải tách đúng 3 bước: list_interview_results -> set_candidate_decision -> send_decision_emails (xem trước -> HR xác nhận -> gửi).

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


# Trần độ dài kết quả tool ĐƯA VÀO NGỮ CẢNH LLM.
#
# VÌ SAO CẦN: kết quả tool được nối vào `messages` rồi GỬI LẠI TOÀN BỘ ở mọi bước sau
# của lượt. Một `search_candidates` limit=20 nặng ~3.000 token; hai ba tool như vậy là
# lượt chat chạm 10.000 token. Hậu quả đo được:
#   - cạn trần NGÀY của model chính rất nhanh (100k TPD ≈ chỉ hơn chục lượt chat);
#   - và khi rơi xuống model dự phòng thì prompt KHÔNG VỪA trần PHÚT của nó
#     (gpt-oss-120b: 8.000 TPM) -> 413 Request too large -> Copilot chết hẳn thay vì
#     chạy chậm hơn. Tức đường dự phòng chỉ tồn tại trên giấy.
#
# Cắt ở đây KHÔNG làm agent mù: các trường ĐIỀU KHIỂN (id, lỗi, cảnh báo, hướng dẫn
# bước tiếp theo) luôn được giữ nguyên; thứ bị cắt là phần liệt kê dài dòng mà model
# chỉ cần đọc lướt.
_LLM_RESULT_CHARS = int(os.getenv("AGENT_TOOL_RESULT_CHARS", "2500"))

# Những trường agent BUỘC phải thấy đầy đủ để đi tiếp cho đúng: id để chuyển sang tool
# sau, lỗi/cảnh báo để nói lại với HR, cờ xác nhận để biết phải hỏi trước khi làm.
_FIELDS_KHONG_CAT = (
    "error", "warning", "message", "how_to_proceed", "next_step", "note", "status",
    "candidate_ids", "count", "scope", "sorted_by", "by_jd", "not_found", "details",
    "needs_confirmation", "already_in", "already_set", "not_in_shortlist", "added",
    "updated", "recorded", "average_score", "question_count", "answered_count",
    "jd_id", "jd", "shortlist", "title", "candidate", "failed", "skipped",
    "will_send_count", "summary", "feedback_summary",
)


def _trim_for_llm(result):
    """Rút gọn kết quả tool trước khi đưa vào ngữ cảnh LLM.

    Giữ TRỌN các trường điều khiển, rồi nhét thêm các trường còn lại chừng nào chưa
    chạm trần. Trường bị bỏ được liệt kê tên trong `_omitted` để model biết là có, chứ
    không tưởng tool trả về thiếu.
    """
    if not isinstance(result, dict):
        return result
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {"error": "Kết quả tool không đọc được."}
    if len(text) <= _LLM_RESULT_CHARS:
        return result

    gon = {k: v for k, v in result.items() if k in _FIELDS_KHONG_CAT}
    con_lai = _LLM_RESULT_CHARS - len(json.dumps(gon, ensure_ascii=False, default=str))
    bo_qua = []
    for k, v in result.items():
        if k in gon:
            continue
        doan = json.dumps(v, ensure_ascii=False, default=str)
        chi_phi = len(doan) + len(k) + 4
        if chi_phi <= con_lai:
            gon[k] = v
            con_lai -= chi_phi
            continue
        # Danh sách quá dài thì CẮT BỚT ĐUÔI chứ đừng bỏ cả trường: `candidates` đã
        # được sắp theo điểm, nên vài mục đầu chính là phần agent cần để gọi tên người
        # cho HR. Bỏ trắng cả mảng thì nó chỉ còn con số, và một agent biết "có 20
        # người" mà không biết tên ai là một agent sắp bịa ra vài cái tên.
        if isinstance(v, list) and v:
            giu = []
            for item in v:
                s = json.dumps(item, ensure_ascii=False, default=str)
                if len(s) + 2 > con_lai:
                    break
                giu.append(item)
                con_lai -= len(s) + 2
            if giu:
                gon[k] = giu
                if len(giu) < len(v):
                    gon[f"_{k}_da_cat"] = f"chỉ hiện {len(giu)}/{len(v)} mục đầu danh sách"
                continue
        bo_qua.append(k)
    if bo_qua:
        gon["_omitted"] = bo_qua
    if bo_qua or any(k.endswith("_da_cat") for k in gon):
        gon["_note"] = (
            "Kết quả dài nên đã rút gọn. Mọi id, lỗi và cảnh báo đều còn ĐỦ ở trên — "
            "riêng phần liệt kê bị cắt bớt. TUYỆT ĐỐI không bịa nội dung phần đã cắt; "
            "cần thêm thì gọi lại tool với bộ lọc hẹp hơn."
        )
    return gon


async def _agent_loop(messages: list, tools: list, execute) -> dict:
    """`execute`: async callable (name, args) -> dict kết quả tool."""
    used: list[str] = []
    # Tool GHI đã chạy XONG và không báo lỗi. Khác `used` (gồm cả tool đọc lẫn tool
    # hỏng): đây là danh sách những TÁC DỤNG PHỤ đã thật sự xảy ra, và nếu lượt này
    # chết giữa chừng thì HR bắt buộc phải được biết đúng danh sách đó.
    da_ghi: list[str] = []
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
            # `da_ghi` là phần bắt buộc: lượt LLM cuối (viết câu trả lời) hỏng KHÔNG
            # xoá đi những gì các tool trước đó đã ghi vào DB.
            return _out(_friendly_error(e, da_ghi), error=str(e))

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

            # Ghi nhận tác dụng phụ ĐÃ xảy ra. `spec.read_only` là nguồn sự thật (khai
            # trong tool_registry), nên tool mới thêm sau này tự động được tính đúng.
            spec = SPECS.get(name)
            if spec and not spec.read_only and not (
                isinstance(result, dict) and "error" in result
            ):
                da_ghi.append(name)

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
                # Rút gọn TRƯỚC khi vào ngữ cảnh: chuỗi này được gửi lại cho LLM ở
                # MỌI bước còn lại của lượt, nên mỗi ký tự thừa ở đây bị nhân lên.
                "content": json.dumps(_trim_for_llm(result), default=str, ensure_ascii=False),
            })

    return _out("Xin lỗi, yêu cầu cần quá nhiều bước để xử lý. Bạn thử tách nhỏ giúp mình nhé.")


async def _run_via_mcp(messages: list, user_id) -> dict:
    """Đường CHÍNH: tool lấy động từ MCP server và thực thi qua MCP."""
    # Danh tính gắn vào PHIÊN (header), không gắn vào từng lời gọi tool: mọi tool chạy
    # trong lượt này đều thuộc về đúng HR đang đăng nhập, LLM không có đường can thiệp.
    async with mcp_session(user_id) as session:
        tools, names = await fetch_tools(session)

        # Các tool GHI đã chạy XONG trong lượt này. Nếu MCP chết sau đó, chạy lại cả
        # lượt ở đường fallback sẽ lặp lại đúng những tác dụng phụ này -> không được.
        applied: list[str] = []

        async def execute(name: str, args: dict) -> dict:
            if name not in names:
                return {"error": f"Tool không tồn tại trên MCP server: {name}"}
            result = await call_tool(session, name, args)
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


def _page_context_note(ctx: dict | None) -> str | None:
    """Câu nhắc về trang HR đang mở, chèn ngay TRƯỚC tin nhắn của HR.

    Vì sao cần: yêu cầu của HR thường tỉnh lược đúng phần quan trọng nhất — "lấy 3
    người điểm cao nhất" không nêu vị trí nào, vì với HR thì hiển nhiên là vị trí đang
    hiện trên màn hình. Không có câu này, agent chỉ còn cách ĐOÁN tên vị trí, và nó đã
    đoán sai thật ("Backend Developer" trong khi đang mở "Backend Python") rồi bịa tiếp
    cả danh sách ứng viên từ đó.

    Đặt ở vị trí SÁT tin nhắn HR (không phải đầu hội thoại) vì ngữ cảnh này thuộc về
    LƯỢT NÀY: HR có thể đổi trang giữa hai câu, và lượt trước đã lưu vào history với
    ngữ cảnh của riêng nó.
    """
    if not ctx:
        return None
    title, jd_id = ctx.get("jd_title"), ctx.get("jd_id")
    if not title and not jd_id:
        return None
    mo_ta = f"'{title}'" if title else "một vị trí"
    return (
        f"NGỮ CẢNH GIAO DIỆN: HR đang mở vị trí {mo_ta}"
        + (f" (jd_id={jd_id})" if jd_id else "")
        + ". Nếu yêu cầu KHÔNG nêu vị trí nào thì hiểu là vị trí này — dùng jd_id ở "
        "trên, đừng đoán tên và đừng hỏi lại HR. Nếu HR nêu rõ một vị trí khác thì "
        "làm theo HR."
    )


def run_agent(
    db: Session,
    message: str,
    user_id=None,
    history: list | None = None,
    page_context: dict | None = None,
) -> dict:
    """
    Chạy 1 lượt hội thoại. Ưu tiên đi qua MCP; MCP chết thì fallback gọi tool nội bộ.

    Hàm này SYNC (router FastAPI sync chạy trong threadpool) nên dùng asyncio.run được.
    Phiên MCP + list_tools được mở TRƯỚC khi gọi LLM, nên nếu MCP hỏng ngay từ đầu ta
    fallback mà không tốn token nào.
    """
    ghi_chu = _page_context_note(page_context)

    def _messages() -> list:
        m = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            m += history
        if ghi_chu:
            m.append({"role": "system", "content": ghi_chu})
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
