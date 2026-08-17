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
from app.services.ai_agent import rate_limiter
from app.services.ai_agent.gemini_client import (
    MODEL_KHONG_TON_TAI,
    is_model_missing,
    reasoning_kwargs,
    record_ai_log,
)

log = logging.getLogger(__name__)

# Mặc định phải là model tài khoản THẬT SỰ còn gọi được — Groq đã gỡ họ llama-3.x khỏi
# free tier (404 model_not_found). Xem chú thích cùng chủ đề trong gemini_client.
AGENT_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# MỌI TÀI KHOẢN GROQ ĐỀU DÙNG ĐƯỢC CHO KHUNG CHAT, key riêng của chat đứng đầu.
#
# Groq tính hạn mức theo TÀI KHOẢN × MODEL. Trước đây khung chat chỉ dùng
# GROQ_MCP_API_KEY, trong khi dự án có sẵn 3 tài khoản — hai cái kia để dành cho
# pipeline chấm CV. Hậu quả đo được trong log: `Rate limit reached ... on tokens per
# day (TPD): Limit 100000, Used 98732`. Cạn trần NGÀY của một tài khoản là mọi lượt
# chat còn lại trong ngày phải bò trên model dự phòng yếu hơn, cộng thêm một vòng 429
# vô ích trước mỗi lượt. Gộp cả 3 tài khoản = gấp 3 ngân sách, và vì `key_id` đặt theo
# cùng quy ước với gemini_client (8 ký tự cuối) nên hai bên dùng CHUNG sổ sách Redis,
# không ai tiêu lẹm phần của ai.
_CHAT_KEY_ENV = ("GROQ_MCP_API_KEY", "GROQ_API_KEY_1", "GROQ_API_KEY_2")

# Trần output cho MỘT lượt trả lời. SYSTEM_PROMPT đã yêu cầu "tối đa 1-2 câu", nên
# 700 là rộng rãi. Không phải chuyện tiết kiệm vặt: Groq trừ hạn mức theo token YÊU
# CẦU (prompt + phần output đặt chỗ) — xem "Requested 7301" trong chính lỗi 429 ở
# trên — nên bỏ trống là mỗi lượt gọi tự ăn thêm ngân sách mình không hề dùng tới.
_MAX_OUTPUT = int(os.getenv("AGENT_MAX_OUTPUT_TOKENS", "700"))
# Trần cứng khi nới output cho lần thử lại (xem `_goi`).
_MAX_OUTPUT_CAP = int(os.getenv("AGENT_MAX_OUTPUT_TOKENS_CAP", "1500"))


def _cac_key() -> list[tuple[str, str]]:
    """(key_id, api_key) của mọi tài khoản Groq khung chat được phép dùng."""
    raw = [v for v in ((os.getenv(n) or "").strip() for n in _CHAT_KEY_ENV) if v]
    if not raw:
        legacy = (os.getenv("GROQ_API_KEY") or "").strip()
        if legacy:
            raw.append(legacy)
    # Khử trùng: hai biến trỏ cùng một tài khoản mà đếm thành hai ngân sách độc lập
    # thì bộ đặt chỗ cấp phát gấp đôi rồi cả hai cùng đâm vào 429.
    return [(k[-8:], k) for k in dict.fromkeys(raw)]


_clients: dict[str, Groq] = {}


def _client_for(key_id: str, api_key: str) -> Groq:
    """Client dùng lại theo key. `max_retries=0` là CỐ Ý.

    Mặc định SDK của Groq tự ngủ rồi thử lại 2 lần khi gặp 429 — im lặng, ngay bên
    trong lời gọi. Đó chính là thứ biến một lần cạn hạn mức thành 30-40 giây mà tầng
    trên không hề thấy gì để mà xử lý. Tắt đi thì `_complete_sync` nhận lỗi NGAY và tự
    quyết: đổi sang tài khoản khác, hoặc đổi model.
    """
    if key_id not in _clients:
        _clients[key_id] = Groq(api_key=api_key, max_retries=0)
    return _clients[key_id]

# Model dự phòng khi model chính CẠN HẠN MỨC NGÀY (TPD).
#
# Groq tính TPD theo TỪNG MODEL và theo ORGANIZATION — không theo API key. Nghĩa là
# đổi sang một key khác trong cùng tài khoản KHÔNG hồi phục được hạn mức (đã kiểm
# chứng: 3 key của dự án báo về cùng một số dư). Thứ thực sự còn hạn mức là một MODEL
# khác. Hết 70b thì hạ xuống model khác còn hơn là ném cho HR câu "gặp trục trặc".
#
# THỨ TỰ QUAN TRỌNG: xếp theo NĂNG LỰC GỌI TOOL giảm dần, không phải theo tốc độ.
# Đã thử model rút gọn đứng đầu: nó bịa ra ứng viên không tồn tại ("Trần Văn A",
# "Nguyễn Thị B") thay vì dùng kết quả search vừa nhận. Một agent thao tác dữ liệu
# thật mà bịa tham số thì tệ hơn hẳn việc báo lỗi thẳng, nên model yếu để cuối cùng.
_FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv("GROQ_FALLBACK_MODELS", "openai/gpt-oss-20b").split(",")
    if m.strip()
]
_MODEL_CHAIN = [AGENT_MODEL] + [m for m in _FALLBACK_MODELS if m != AGENT_MODEL]
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))
# Trần THỜI GIAN cho một lượt chat, tính cả thời gian Groq bắt chờ vì chạm hạn mức.
# Quá mốc này thì dừng và trả lời trung thực — HR ngồi nhìn "Đang xử lý…" quá lâu còn
# tệ hơn một câu "chưa xong, bạn thử lại".
TURN_BUDGET = float(os.getenv("AGENT_TURN_BUDGET", "75"))
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


class _TraLoiRong(Exception):
    """Groq trả 200 nhưng lượt đó không có chữ nào và cũng không gọi tool nào."""


def _qua_lon(err: Exception) -> bool:
    """413: MỘT request vượt trần token/phút — KHÁC HẲN "hết hạn mức".

    Groq gắn nhãn `rate_limit_exceeded` cho cả hai, nên trước đây 413 rơi thẳng vào
    nhánh quota: Copilot đi báo HR "hệ thống hết hạn mức AI cho hôm nay" trong khi hạn
    mức còn nguyên — thứ cạn là chỗ trong MỘT lời gọi. Đúng màn hình HR đã gặp: lượt đó
    tạo shortlist + sinh câu hỏi xong xuôi, chỉ mỗi lời gọi cuối (viết câu trả lời) mang
    theo lịch sử 8.446 token nên không lọt qua trần 8.000.

    Cách chữa cũng ngược nhau: hết hạn mức thì phải CHỜ, còn request quá lớn thì phải
    CẮT NHỎ rồi gọi lại ngay — chờ bao lâu cũng không giúp gì.
    """
    text = str(err).lower()
    # SO KHỚP CHẶT, KHÔNG BẮT CHUỖI "413" TRẦN.
    #
    # Bản đầu tìm mỗi substring "413" trong thông báo lỗi — mà "413" xuất hiện đầy rẫy
    # trong những chỗ chẳng liên quan: một uuid ứng viên, một số token, một id phiên.
    # Hậu quả đúng như HR gặp: một yêu cầu ngắn ("gửi thư chấp nhận cho <tên>") lỗi vì
    # nguyên nhân khác hẳn, nhưng bị dán nhãn "yêu cầu gom quá nhiều dữ liệu" — vừa nói
    # sai với HR, vừa che mất lỗi thật.
    return "request too large" in text or "error code: 413" in text or "status code: 413" in text


def _is_quota_error(err: Exception) -> bool:
    """Lỗi này là do CẠN HẠN MỨC nhà cung cấp (429), không phải lỗi lập trình."""
    if _qua_lon(err):
        return False
    text = str(err).lower()
    return "rate_limit" in text or "rate limit" in text or "error code: 429" in text


# Độ dài giữ lại cho MỘT kết quả tool cũ khi phải cắt lịch sử vì 413.
_TOOL_MSG_MIN_CHARS = int(os.getenv("AGENT_TOOL_MSG_MIN_CHARS", "400"))


def _bo_bot_lich_su_cu(messages: list) -> bool:
    """Bỏ tin nhắn CŨ NHẤT của các lượt trước. True nếu bỏ được.

    Đây là nước thứ hai, dùng khi kết quả tool trong lượt này đã lược hết mà request vẫn
    quá lớn — tình huống có thật: HR dán nguyên một câu trả lời phỏng vấn dài rồi nhờ
    ghi lại, trong khi phiên chat đã tích vài lượt tương tự.

    CHỈ ĐỘNG VÀO PHẦN TRƯỚC CÂU HỎI HIỆN TẠI. Câu HR vừa gõ phải giữ NGUYÊN VĂN (nó là
    dữ liệu sẽ được ghi vào buổi phỏng vấn), và cặp assistant(tool_calls) + tool của
    lượt đang chạy cũng không được đụng tới — bỏ lẻ một vế là Groq báo lỗi thiếu
    tool_call_id. Phần lịch sử cũ thì chỉ gồm user/assistant/system rời rạc nên bỏ an
    toàn.
    """
    vi_tri_user = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if not vi_tri_user:
        return False
    hien_tai = vi_tri_user[-1]
    # index 0 là system prompt — không bao giờ bỏ.
    if hien_tai <= 1:
        return False
    messages.pop(1)
    return True


def _thu_gon_lich_su(messages: list) -> bool:
    """Cắt bớt kết quả các tool CŨ trong lịch sử. Trả True nếu cắt được gì.

    Kết quả tool được gửi LẠI nguyên vẹn ở mọi bước sau của lượt, nên một lượt nhiều
    bước (tìm ứng viên -> tạo shortlist -> sinh câu hỏi -> trả lời) tự phình lên tới
    trần. Bước sau chỉ cần biết bước trước đã làm gì và ra sao, không cần đọc lại toàn
    bộ bảng dữ liệu — nên cắt phần cũ là cách rẻ nhất để lượt chạy tới cùng.

    KẾT QUẢ TOOL MỚI NHẤT LUÔN GIỮ NGUYÊN: đó chính là thứ model đang cần để viết câu
    trả lời hoặc quyết định bước kế tiếp.
    """
    chi_so = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    if len(chi_so) <= 1:
        return _bo_bot_lich_su_cu(messages)
    da_cat = False
    for i in chi_so[:-1]:
        noi_dung = messages[i].get("content") or ""
        gon = noi_dung[:_TOOL_MSG_MIN_CHARS] + " …(đã lược bớt cho vừa trần token)"
        # CHỈ tính là cắt được khi bản mới NGẮN THẬT. Nếu không, phần đuôi "…đã lược
        # bớt" tự nó làm chuỗi dài hơn ngưỡng, và mỗi lần gọi lại hàm này lại báo "cắt
        # được" trong khi kích thước đứng yên — vòng thử lại chạy đủ lượt rồi vẫn 413.
        if len(gon) < len(noi_dung):
            messages[i] = {**messages[i], "content": gon}
            da_cat = True
    # Kết quả tool đã lược sạch mà vẫn còn to -> chuyển sang bỏ bớt lịch sử lượt cũ.
    return da_cat or _bo_bot_lich_su_cu(messages)


def _quota_wait_seconds(err: Exception) -> float:
    """Số giây Groq bảo phải chờ ('try again in 1h2m19.4s'). 0 nếu không nói."""
    m = re.search(
        r"try again in\s+(?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", str(err), re.IGNORECASE
    )
    if not m:
        return 0.0
    gio, phut, giay = m.group(1), m.group(2), m.group(3)
    return int(gio or 0) * 3600 + int(phut or 0) * 60 + float(giay or 0)


def _quota_wait_hint(err: Exception) -> str:
    """Thời gian chờ Groq gợi ý, diễn đạt cho người đọc."""
    giay = _quota_wait_seconds(err)
    if giay <= 0:
        return ""
    if giay >= 60:
        return f" Hạn mức sẽ mở lại sau khoảng {int(giay // 60)} phút."
    return " Bạn thử lại sau ít phút nhé."


# Model nào đang bị Groq khoá, và tới bao giờ. Khoá theo TRẦN NGÀY (TPD) có thể kéo
# hàng giờ; không nhớ lại thì MỌI lời gọi sau đó vẫn thử model đó trước, ăn thêm một
# vòng 429 rồi mới chịu đổi — tức mỗi lượt chat lãng phí 2 round-trip vô ích, đúng lúc
# hệ thống đang chậm nhất. Bộ nhớ này ở cấp tiến trình là đủ: mất khi restart thì cùng
# lắm là học lại một lần.
#
# KHOÁ THEO (TÀI KHOẢN, MODEL), KHÔNG PHẢI THEO MODEL.
#
# Groq tính hạn mức theo TỔ CHỨC: đã kiểm chứng bằng chính thông báo lỗi của Groq —
# ba key của dự án thuộc BA org khác nhau (org_01kykyty…, org_01kym0mg…, org_01kysbpa…),
# tức ba ngân sách hoàn toàn độc lập. Bản trước khoá theo tên model, nên một tài khoản
# cạn 8.000 token/phút là model đó bị gạch khỏi chuỗi cho CẢ BA tài khoản — tự vứt đi
# 2/3 ngân sách rồi tụt xuống model yếu hơn, đúng lúc HR đang chờ.
_model_cooldown: dict[tuple[str, str], float] = {}

# TRẦN cho một lần nghỉ, BẤT KỂ Groq hứa bao lâu.
#
# Groq báo "try again in 1h2m" theo trần NGÀY, nhưng ngân sách đó hồi lại DẦN theo cửa
# sổ trượt — đo được: nó mở lại chỉ sau vài phút. Tin nguyên con số đó là tự khoá mình
# khỏi model TỐT NHẤT cả tiếng, ép mọi lượt chat xuống model yếu hơn (trần phút thấp
# hơn, gọi tool kém hơn). Đã trả giá thật: một câu hỏi đơn giản mất 941 giây và kết
# thúc bằng việc hỏi ngược HR một cái id.
#
# Thà cứ vài phút phí một round-trip để thử lại còn hơn.
_COOLDOWN_MAX = float(os.getenv("AGENT_MODEL_COOLDOWN_MAX", "180"))


def _kha_dung(model: str) -> bool:
    """Model này còn ÍT NHẤT MỘT tài khoản chưa bị khoá không?

    Chỉ cần một tài khoản còn mở là model vẫn dùng được — `try_reserve` sẽ tự chọn đúng
    tài khoản đó và bỏ qua những tài khoản đang nghỉ.
    """
    bay_gio = time.time()
    con_khoa = 0
    keys = _cac_key()
    for key_id, _ in keys:
        het_han = _model_cooldown.get((key_id, model), 0.0)
        if het_han and bay_gio < het_han:
            con_khoa += 1
        else:
            _model_cooldown.pop((key_id, model), None)
    return con_khoa < len(keys) if keys else True


# Model KHÔNG GỌI ĐƯỢC TOOL (vd groq/compound: "`tool calling` is not supported with
# this model"). Khác với model chết hẳn: nó vẫn chạy tốt cho các việc JSON của pipeline,
# nên danh sách này là RIÊNG của khung chat, không dùng chung với gemini_client.
_MODEL_KHONG_GOI_DUOC_TOOL: set[str] = set()


def _khong_goi_duoc_tool(err: Exception) -> bool:
    text = str(err).lower()
    return "tool calling" in text and "not supported" in text


def _con_song() -> list[str]:
    """Chuỗi model bỏ đi những model NHÀ CUNG CẤP KHÔNG CÒN PHỤC VỤ (404).

    Khác hẳn cooldown ở trên: cooldown là tạm thời nên hết hạn là thử lại, còn model bị
    gỡ khỏi tài khoản thì thử lại bao nhiêu lần cũng 404. Danh sách chết dùng chung với
    `gemini_client` để hai đường gọi Groq (khung chat và pipeline) chỉ phải học một lần.
    Chết sạch thì vẫn trả chuỗi đầy đủ — để lỗi thật của Groq nói ra nguyên nhân, thay
    vì ta tự dựng một lỗi khác che mất nó.
    """
    bo = MODEL_KHONG_TON_TAI | _MODEL_KHONG_GOI_DUOC_TOOL
    con = [m for m in _MODEL_CHAIN if m not in bo]
    return con or list(_MODEL_CHAIN)


def _chain_kha_dung() -> list[str]:
    """Chuỗi model theo thứ tự ưu tiên, đã bỏ những model đang bị khoá.

    Nếu KHOÁ HẾT thì vẫn trả về chuỗi đầy đủ: thà thử và nhận lỗi thật còn hơn tự từ
    chối trong khi có thể Groq đã mở lại sớm hơn con số nó hứa.
    """
    song = _con_song()
    con = [m for m in song if _kha_dung(m)]
    return con or song


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
    if _qua_lon(err) and not da_lam:
        # Nói đúng bản chất: yêu cầu này quá dài cho một lời gọi, KHÔNG phải hết hạn mức
        # (bảo HR "hết hạn mức hôm nay" khiến họ ngồi chờ tới mai một cách vô ích).
        return (
            "Yêu cầu này gom quá nhiều dữ liệu cho một lượt xử lý nên mình chưa trả lời "
            "được. Bạn tách nhỏ ra giúp mình nhé (ví dụ làm từng nhóm ứng viên, hoặc "
            "hỏi từng việc một)."
        )

    if da_lam:
        # Tên tiếng Việt lấy từ chính registry (`title`), khử trùng nhưng giữ thứ tự
        # đã làm — HR đọc là hình dung được đúng những gì vừa xảy ra với dữ liệu.
        viec = ", ".join(dict.fromkeys(SPECS[t].title.lower() for t in da_lam if t in SPECS))
        if het_han_muc:
            ly_do = "hệ thống hết hạn mức AI cho hôm nay"
        elif _qua_lon(err):
            ly_do = "yêu cầu này quá dài cho một lượt xử lý"
        else:
            ly_do = "mình gặp trục trặc kỹ thuật"
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
    if isinstance(err, _TraLoiRong):
        # Đã thử lại với trần output rộng dần mà model vẫn không nói được câu nào. Nói
        # thật là hơn: dòng "(không có phản hồi)" trắng trơn khiến HR không biết yêu cầu
        # của mình đã chạy hay chưa.
        return (
            "Mình chưa soạn được câu trả lời cho yêu cầu này (model AI trả về lượt "
            "rỗng). Chưa có gì bị thay đổi thêm; bạn thử gửi lại yêu cầu ngắn gọn hơn "
            "giúp mình nhé."
        )
    if is_model_missing(err):
        # Đây là lỗi CẤU HÌNH, không phải lỗi cách HR diễn đạt: model khai trong
        # GROQ_MODEL đã bị nhà cung cấp gỡ. Khuyên "diễn đạt lại" ở đây là đẩy HR đi
        # gõ lại mãi một yêu cầu không đời nào chạy được.
        return (
            "Hệ thống đang cấu hình một model AI mà nhà cung cấp không còn phục vụ, nên "
            "mình chưa xử lý được. Việc này cần quản trị viên cập nhật cấu hình (biến "
            "GROQ_MODEL), gõ lại yêu cầu sẽ không giúp được gì."
        )
    return "Xin lỗi, mình gặp trục trặc khi xử lý yêu cầu này. Bạn thử diễn đạt lại giúp mình nhé."


# UUID trong câu trả lời gửi cho HR: CẤM, và chặn bằng CODE chứ không chỉ bằng prompt.
#
# `SYSTEM_PROMPT` đã dặn "không bao giờ in UUID", nhưng prompt chỉ là xác suất — model
# dự phòng (yếu hơn) vẫn trả về "Nguyễn Minh Khoa (ID: 6828d1a8-63b1-...)". Với HR thì
# một chuỗi 36 ký tự vô nghĩa giữa câu là rác, và nó còn mời gọi họ chép id vào lượt sau
# thay vì gọi tên người.
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
# Dọn phần bao quanh còn sót sau khi bỏ uuid: "(ID: )", "[id: ]", " - ID:" ...
_UUID_KEM_NHAN = re.compile(
    r"[\s,;–-]*[\(\[\{]?\s*(?:(?:với|là|có|mang)\s+)?(?:id|mã|uuid)\s*[:=]?"
    r"\s*\)?\]?\}?\s*(?=[\)\]\},.;]|$)",
    re.IGNORECASE,
)


def _bo_uuid(text: str) -> str:
    """Bỏ mọi UUID khỏi câu trả lời, kèm nhãn 'ID:' đi cùng nó nếu có."""
    if not text or "-" not in text:
        return text
    sach = _UUID_RE.sub("", text)
    if sach == text:
        return text
    sach = _UUID_KEM_NHAN.sub("", sach)
    # Dọn dấu ngoặc rỗng và khoảng trắng thừa do phần bị xoá để lại.
    sach = re.sub(r"[\(\[\{]\s*[\)\]\}]", "", sach)
    sach = re.sub(r"\s+([,.;:!?])", r"\1", sach)
    return re.sub(r"[ \t]{2,}", " ", sach).strip()


def _qua_lau(da_lam: list[str] | None = None) -> str:
    """Câu trả lời khi lượt chạm trần thời gian.

    Vẫn phải nói ra những tool GHI đã chạy xong — cùng lý do với `_friendly_error`:
    im lặng ở đây thì HR gõ lại và hệ thống làm lần hai.
    """
    if da_lam:
        viec = ", ".join(dict.fromkeys(SPECS[t].title.lower() for t in da_lam if t in SPECS))
        return (
            f"Mình ĐÃ kịp thực hiện: {viec}, nhưng yêu cầu này mất quá nhiều thời gian nên "
            "mình dừng lại. Bạn kiểm tra trên màn hình giúp mình, ĐỪNG gửi lại để tránh bị "
            "làm hai lần."
        )
    return (
        "Yêu cầu này đang mất quá nhiều thời gian nên mình tạm dừng, chưa thay đổi gì cả. "
        "Bạn thử tách nhỏ yêu cầu hoặc nói rõ hơn giúp mình nhé."
    )


def _complete_sync(messages: list, tools: list):
    """Gọi Groq (có tools), tự retry khi model sinh tool-call hỏng hoặc lỗi tạm thời.

    Mọi lượt gọi đều ghi vào ai_logs như các agent khác: agent chat đi thẳng qua
    Groq chứ không qua `generate_text`, nên nếu không ghi ở đây thì phần token/độ
    trễ tốn nhiều nhất của hệ thống lại vô hình với trang Giám sát AI.
    """
    last_err = None
    start = time.time()
    keys = _cac_key()
    # Ước lượng để ĐẶT CHỖ trước. Prompt của lượt chat = system + lịch sử + kết quả
    # tool, cộng schema tool (gửi lại nguyên vẹn ở MỌI lời gọi) — phải tính cả schema,
    # nếu không sổ sách hụt đúng phần chiếm 3/4 mỗi lời gọi.
    est_prompt = json.dumps(messages, default=str, ensure_ascii=False) + json.dumps(
        tools, default=str, ensure_ascii=False
    )

    da_goi = False  # đã THỰC SỰ gọi Groq lần nào chưa (dù thành công hay không)

    def _goi(model: str, key_id: str, api_key: str, attempt: int, est: int):
        """Một lượt gọi Groq. Ném nguyên lỗi ra cho vòng ngoài xử lý."""
        # Temperature TĂNG DẦN qua các lần thử. Với temperature cố định, một prompt
        # làm llama sinh cú pháp tool-call hỏng (`tool_use_failed`) sẽ sinh ra đúng
        # chuỗi hỏng đó ở cả 3 lần retry — retry thành vô nghĩa, và HR nhận câu "mình
        # gặp trục trặc" một cách rất ổn định. Nới ngẫu nhiên để lần sau khác thật.
        resp = _client_for(key_id, api_key).chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2 + 0.3 * attempt,
            # Trần output NỚI DẦN theo lần thử: lần đầu tiết kiệm, nhưng nếu model
            # reasoning tiêu hết trần vào phần suy nghĩ và trả về rỗng thì lần sau phải
            # rộng hơn, chứ thử lại y nguyên là rỗng y nguyên. CÓ TRẦN CỨNG vì Groq trừ
            # hạn mức phút theo (prompt + output đặt chỗ): nới vô tội vạ là tự đẩy request
            # vượt 8.000 TPM rồi ăn 413 "Request too large".
            max_tokens=min(_MAX_OUTPUT * (attempt + 1), _MAX_OUTPUT_CAP),
            **reasoning_kwargs(model),
        )
        dung_that = getattr(getattr(resp, "usage", None), "total_tokens", 0) or 0
        # Trả lại phần đặt chỗ thừa, để lượt sau không bị từ chối oan.
        rate_limiter.reconcile(key_id, model, est, dung_that)

        # LƯỢT RỖNG = LƯỢT HỎNG, KHÔNG PHẢI LƯỢT THÀNH CÔNG.
        #
        # Model reasoning tiêu hết trần output vào phần suy nghĩ thì API vẫn trả 200,
        # chỉ là `content` rỗng và không có tool_calls nào. Trước đây lượt đó được ghi
        # log là THÀNH CÔNG rồi trả thẳng lên khung chat, thành đúng dòng "(không có
        # phản hồi)" mà HR nhìn thấy — một lượt tiêu 8.446 token nhưng nói không nên
        # lời. Ném ra để vòng ngoài thử lại với trần rộng hơn / model khác.
        msg = resp.choices[0].message
        if not (getattr(msg, "content", None) or "").strip() and not getattr(msg, "tool_calls", None):
            record_ai_log(
                agent_name="copilot_agent",
                prompt=_prompt_for_log(messages),
                completion=None,
                total_tokens=dung_that,
                latency_ms=(time.time() - start) * 1000,
                is_error=True,
                error_message=(
                    f"{model} trả lời rỗng (finish_reason="
                    f"{getattr(resp.choices[0], 'finish_reason', '?')}); nhiều khả năng "
                    f"phần suy luận đã ăn hết trần {_MAX_OUTPUT * (attempt + 1)} token."
                ),
            )
            raise _TraLoiRong(f"{model} trả về lượt rỗng")

        completion = _completion_for_log(resp)
        if model != AGENT_MODEL:
            completion = f"[model dự phòng: {model}]\n{completion}"
        record_ai_log(
            agent_name="copilot_agent",
            prompt=_prompt_for_log(messages),
            completion=completion,
            total_tokens=dung_that,
            latency_ms=(time.time() - start) * 1000,
            is_error=False,
            error_message=None,
        )
        return resp

    for model in _chain_kha_dung():
        for attempt in range(_LLM_RETRIES):
            est = rate_limiter.estimate_tokens(est_prompt, _MAX_OUTPUT)
            # Chọn TÀI KHOẢN còn ngân sách cho model này. `try_reserve` fail-open khi
            # Redis chết (reason='no_redis') nên sự cố Redis không chặn khung chat.
            key_id = api_key = None
            for kid, akey in keys:
                ok, _wait, _reason = rate_limiter.try_reserve(kid, model, est)
                if ok:
                    key_id, api_key = kid, akey
                    break
            if key_id is None:
                # Cả 3 tài khoản đều cạn cho model này -> xuống model kế tiếp NGAY,
                # đừng ngồi đợi: mỗi giây ở đây là HR nhìn "Đang xử lý…".
                log.info("Mọi tài khoản đều cạn ngân sách cho %s, thử model kế tiếp.", model)
                break

            try:
                da_goi = True
                return _goi(model, key_id, api_key, attempt, est)
            except Exception as e:  # noqa: BLE001 - cả tool_use_failed lẫn 429/5xx
                last_err = e
                if not isinstance(e, _TraLoiRong):
                    # Lượt rỗng thì token ĐÃ TIÊU THẬT và `_goi` đã reconcile bằng số
                    # thật rồi — trả chỗ thêm lần nữa là ghi khống cho mình một ngân
                    # sách không có, rồi lượt sau đâm vào 429.
                    rate_limiter.release_reservation(key_id, model, est)
                if is_model_missing(e):
                    # Groq không phục vụ model này nữa -> gạch tên và XUỐNG MODEL KẾ
                    # TIẾP NGAY. Trước đây 404 rơi vào nhánh "lỗi ngẫu nhiên" ở cuối:
                    # 3 lần gọi lại + 2 lần ngủ cho mỗi lượt chat, chỉ để nhận đúng
                    # một câu trả lời tất định.
                    MODEL_KHONG_TON_TAI.add(model)
                    log.warning(
                        "Groq không còn model %s cho tài khoản %s; chuyển model kế tiếp. "
                        "Cập nhật GROQ_MODEL/GROQ_FALLBACK_MODELS theo /v1/models.",
                        model, key_id,
                    )
                    break
                if _qua_lon(e):
                    # KHÔNG phải hết hạn mức -> KHÔNG cooldown, KHÔNG bỏ model. Cắt bớt
                    # lịch sử rồi gọi lại NGAY: đổi model chỉ vô ích vì mọi model trên
                    # tài khoản free đều cùng trần 8.000 token/phút.
                    if _thu_gon_lich_su(messages) and attempt + 1 < _LLM_RETRIES:
                        est_prompt = json.dumps(messages, default=str, ensure_ascii=False) + json.dumps(
                            tools, default=str, ensure_ascii=False
                        )
                        log.warning(
                            "Request vượt trần token/phút của %s; đã lược bớt lịch sử và gọi lại.",
                            model,
                        )
                        continue
                    log.warning(
                        "Request vẫn vượt trần token/phút của %s sau khi lược; thử model kế tiếp.",
                        model,
                    )
                    break
                if _khong_goi_duoc_tool(e):
                    # CÙNG MỘT HÌNH DẠNG với 404: lỗi tất định về NĂNG LỰC model, thử
                    # lại bao nhiêu lần cũng vậy. Gạch tên khỏi chuỗi CHAT (model vẫn
                    # tốt cho việc JSON của pipeline) rồi xuống model kế tiếp ngay.
                    _MODEL_KHONG_GOI_DUOC_TOOL.add(model)
                    log.warning(
                        "Model %s không hỗ trợ tool calling nên không dùng cho Copilot "
                        "được; chuyển model kế tiếp. Sửa GROQ_MODEL trong .env.", model,
                    )
                    break
                if _is_quota_error(e):
                    # Groq đã chặn -> ghi vào sổ Redis để các tiến trình KHÁC (worker
                    # chấm CV dùng chung tài khoản này) không đâm vào cùng bức tường.
                    cho = min(_quota_wait_seconds(e), _COOLDOWN_MAX)
                    rate_limiter.cooldown(key_id, model, cho)
                    if cho > 0:
                        _model_cooldown[(key_id, model)] = time.time() + cho
                    log.warning(
                        "Tài khoản %s hết hạn mức cho %s (nghỉ ~%ds): %s",
                        key_id, model, int(cho), e,
                    )
                    # Còn tài khoản khác cho model này thì thử tiếp NGAY ở vòng sau;
                    # `try_reserve` sẽ tự bỏ qua tài khoản vừa bị cooldown.
                    if len(keys) > 1 and attempt + 1 < _LLM_RETRIES:
                        continue
                    break
                time.sleep(0.8 * (attempt + 1))

    # KHÔNG LỜI GỌI NÀO ĐƯỢC THỬ -> sổ Redis nói mọi tài khoản đều cạn cho mọi model.
    #
    # Sổ đó chỉ là ƯỚC LƯỢNG: nó đặt chỗ trước theo số token DỰ ĐOÁN và mang theo
    # cooldown học từ một lần 429 cũ, nên nó sai theo hướng BI QUAN khá thường xuyên —
    # Groq vẫn cho gọi mà HR đã nhận "trục trặc". Thà thử một phát thật rồi nhận lỗi
    # thật, cùng nguyên tắc với `_chain_kha_dung` ("thà thử còn hơn tự từ chối").
    if not da_goi and keys:
        # Model đầu tiên CÒN SỐNG: thử lại một model đã 404 thì chắc chắn 404 lần nữa.
        model = _con_song()[0]
        key_id, api_key = keys[0]
        log.warning(
            "Sổ ngân sách báo cạn hết; vẫn thử %s bằng tài khoản %s để Groq tự quyết.",
            model, key_id,
        )
        try:
            da_goi = True
            return _goi(model, key_id, api_key, 0, 0)
        except Exception as e:  # noqa: BLE001
            last_err = e

    # `last_err` CÓ THỂ VẪN LÀ None nếu ngay cả lần thử liều ở trên cũng không chạy
    # (không có key nào). `raise None` ném TypeError — một lỗi KHÔNG phải quota, nên
    # `_friendly_error` rơi xuống nhánh chung và khuyên HR "thử diễn đạt lại", trong
    # khi diễn đạt lại bao nhiêu lần cũng hỏng. Đúng lỗi HR gặp.
    if last_err is None:
        last_err = RuntimeError(
            "rate limit: hết ngân sách token cho mọi tài khoản Groq và mọi model, "
            "chưa gọi được lần nào."
        )

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


# PROMPT NÀY PHẢI NGẮN — ĐÂY LÀ RÀNG BUỘC HIỆU NĂNG, KHÔNG PHẢI SỞ THÍCH.
#
# Nó được gửi kèm MỌI lời gọi LLM, hai lần mỗi lượt chat, cùng với schema của 20 tool.
# Đo thực tế trên Groq free tier: bản dài trước đây (2.240 token) + schema (5.085 token)
# = 7.326 token CỐ ĐỊNH mỗi lời gọi -> một lượt chat tiêu ~14.650 token trong khi trần
# là 12.000 token/PHÚT. Nghĩa là ngay cả câu hỏi đơn giản nhất cũng vượt trần, lời gọi
# thứ hai ăn 429 rồi phải chờ/đổi model: đo được 35,6s trung bình, cá biệt 130s, trong
# khi lượt nào lọt trần chỉ mất 1,5s.
#
# QUY TẮC KHI SỬA: mỗi luật viết ĐÚNG MỘT LẦN, ở đúng một nơi.
#   - Cách dùng một tool cụ thể  -> `description` của tool đó trong tool_registry.
#   - Hành vi chung của trợ lý   -> ở đây.
#   - Lý do lịch sử/bối cảnh     -> comment Python như đoạn này, KHÔNG gửi cho LLM.
SYSTEM_PROMPT = """Bạn là trợ lý tuyển dụng của HireWise, hỗ trợ nhân viên HR. Bạn có tool để tra cứu và thao tác dữ liệu tuyển dụng THẬT, và điều khiển được giao diện bên trái qua open_jd / open_dashboard / open_shortlisting.

CHỈ GỌI ĐÚNG TOOL MÀ YÊU CẦU CẦN, KHÔNG GỌI THÊM:
- HR hỏi XEM / TRA CỨU / LIỆT KÊ -> chỉ gọi tool ĐỌC rồi trả lời ngay. TUYỆT ĐỐI không gọi kèm tool GHI (tạo câu hỏi, nhập câu trả lời, chốt, gửi thư) khi HR không yêu cầu.
- Gọi xong tool cần thiết là DỪNG và trả lời. Đừng "làm sẵn bước tiếp theo" cho HR.
- Tin nhắn vô nghĩa, chào hỏi, hoặc bạn không chắc HR muốn gì -> không gọi tool nào, hỏi lại cho rõ.

KHÔNG BỊA — quy tắc quan trọng nhất:
- Mọi id/tên truyền vào tool phải lấy NGUYÊN VĂN từ kết quả tool trong hội thoại này, hoặc do HR gõ. Không dùng tên giữ chỗ ("Nguyễn Văn A", "Ứng viên 1") và không dùng id giữ chỗ ("ID1", "ID2").
- HR GỌI ĐÍCH DANH một người ("xem hồ sơ của Nguyễn Minh Khoa") -> truyền THẲNG cái tên HR vừa gõ vào tool. TUYỆT ĐỐI không gọi search_candidates rồi tự chọn một id trong danh sách: chọn nhầm là trả lời về người khác mà không ai phát hiện được. Tool tự tra tên chính xác, tên nhập nhằng thì nó sẽ báo.
- Chưa biết ai thì gọi search_candidates để biết. Tool vừa báo lỗi thì ĐỌC thông báo lỗi rồi làm lại cho đúng, đừng đoán tiếp.
- Tool trả 'not_found' hoặc 'needs_confirmation' = CHƯA làm gì cả. Đừng báo với HR là đã xong.
- Chỉ nói những gì tool trả về: không bịa điểm, tên, hay kết quả.

VỊ TRÍ NÀO — khi HR không nêu tên vị trí:
1. Có "NGỮ CẢNH GIAO DIỆN" (HR đang mở một vị trí) -> BẮT BUỘC truyền jd_id đó. "4 người cao nhất" nghĩa là của vị trí ĐANG MỞ. Bỏ trống là gom nhầm ứng viên vị trí khác rồi thao tác lan sang đó.
2. Không có ngữ cảnh + HR chỉ TRA CỨU chung -> bỏ trống jd_id.
3. Không có ngữ cảnh + HR yêu cầu HÀNH ĐỘNG -> gọi list_jds rồi HỎI LẠI làm cho vị trí nào. Đừng tự chọn, đừng làm cho tất cả.
HR nêu rõ vị trí khác hoặc nói "mọi vị trí" thì làm theo HR.

THEO LÔ: HR nói "tất cả/mỗi người/top N" -> gọi search_candidates MỘT lần rồi chép nguyên candidate_ids sang MỘT lời gọi tool tiếp theo. Không gọi lặp từng người.

HAI THANG ĐIỂM KHÁC NHAU: "điểm" mặc định là điểm sàng lọc CV thang 100 (search_candidates). Chỉ khi HR nói rõ "điểm phỏng vấn" mới dùng list_interview_results (thang 10). Nhầm thang là chốt nhầm người.

SAU PHỎNG VẤN — mỗi bước có ĐIỀU KIỆN riêng, KHÔNG phải chuỗi phải chạy hết:
- HR chỉ muốn XEM buổi phỏng vấn -> get_interview, rồi DỪNG.
- HR THUẬT LẠI ứng viên đã trả lời gì -> get_interview để lấy số thứ tự câu hỏi, rồi record_interview_answers.
- HR muốn ĐÓNG buổi phỏng vấn -> finish_interview.
- HR hỏi ai đạt bao nhiêu ĐIỂM PHỎNG VẤN -> list_interview_results.
- HR nói nhận/loại ai -> set_candidate_decision. HR muốn BÁO cho ứng viên -> send_decision_emails.
Yêu cầu gộp ("chốt nhận và gửi mail cho người trên 7 điểm") thì mới chạy nhiều bước liền nhau.

HÀNH ĐỘNG KHÔNG THU HỒI ĐƯỢC (gửi thư, đóng phỏng vấn, ghi đè dữ liệu): gọi lần đầu KHÔNG bật cờ confirm/replace để lấy bản xem trước, nói cho HR biết sẽ ảnh hưởng tới ai, chờ HR đồng ý rõ ràng rồi mới gọi lại kèm cờ.

create_jd: chỉ tạo khi tin nhắn MỚI NHẤT nêu rõ vị trí cần tuyển, và raw_text lấy từ chính tin nhắn đó — không tái sử dụng nội dung lượt trước.

TRẢ LỜI: tiếng Việt, tối đa 1-2 câu, chỉ nói KẾT QUẢ. Không thuật lại các bước, không nhắc lại yêu cầu, KHÔNG BAO GIỜ in UUID và không hỏi HR cung cấp id.
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
#
# 3.500 ký tự (~1.170 token) là mức vừa đủ để một danh sách 20 ứng viên còn giữ ĐỦ TÊN
# ở dạng rút gọn. Hạ xuống 2.500 thì nhánh "giữ đủ tên" không vừa, tool rơi về cắt bớt
# còn 4 người — và HR hỏi về người thứ 7 là agent trả lời nhầm sang người khác.
_LLM_RESULT_CHARS = int(os.getenv("AGENT_TOOL_RESULT_CHARS", "3500"))

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


# Những trường ĐỦ để agent nhận ra và gọi đúng một mục trong danh sách. Phần bị bỏ
# (kỹ năng, email, nhận xét dài...) agent luôn lấy lại được bằng một tool đọc chi tiết.
#
# CỐ Ý KHÔNG có `candidate_id`: mảng `candidate_ids` ở cấp trên đã liệt kê đủ id theo
# ĐÚNG thứ tự này rồi. Lặp lại 38 ký tự uuid trong từng mục là thứ đẩy danh sách vượt
# ngân sách, và cái giá phải trả khi vượt là bị cắt mất người ở cuối bảng.
_MUC_TOI_THIEU = (
    "name", "candidate", "score", "average_score", "cv_score",
    "jd_title", "status", "index", "decision", "title",
)


def _muc_gon(item):
    """Rút một mục trong danh sách xuống các trường nhận dạng."""
    if not isinstance(item, dict):
        return item
    nho = {k: v for k, v in item.items() if k in _MUC_TOI_THIEU}
    return nho or item


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
            # NHƯNG thử RÚT GỌN TỪNG MỤC trước đã. Cắt mất mục thứ 7 nghĩa là người
            # thứ 7 biến mất khỏi tầm nhìn của model — HR hỏi đúng người đó thì nó
            # đành chọn đại một người nó thấy được, và trả lời về NGƯỜI KHÁC. Giữ đủ
            # tên với ít trường hơn vừa rẻ hơn vừa không đánh rơi ai.
            nhe = [_muc_gon(it) for it in v]
            doan_nhe = json.dumps(nhe, ensure_ascii=False, default=str)
            if len(doan_nhe) + len(k) + 4 <= con_lai:
                gon[k] = nhe
                con_lai -= len(doan_nhe) + len(k) + 4
                gon[f"_{k}_rut_gon"] = (
                    "Đủ MỌI mục, chỉ bớt chi tiết. Id nằm ở 'candidate_ids' theo ĐÚNG "
                    "thứ tự này."
                )
                continue
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
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    # DIRECTIVE GIAO DIỆN — gom lại chứ không xếp hàng.
    #
    # HR chỉ có MỘT màn hình, nên một lượt chat chỉ được đưa họ tới MỘT nơi. Trước đây
    # mọi ui_action được đẩy vào một danh sách rồi frontend chạy tuần tự, nên yêu cầu
    # gộp "thêm 3 người điểm cao nhất vào shortlist X, mỗi người 3 câu hỏi" sinh ra 3
    # directive: search_candidates nhảy sang /projects (tô sáng kết quả),
    # add_to_shortlist nhảy sang /shortlisting, generate_interview_questions xin làm
    # mới. HR thấy màn hình giật qua một trang rồi mới tới nơi, và đích đến phụ thuộc
    # tool nào TÌNH CỜ chạy sau cùng.
    #
    # Luật ở đây: directive của tool GHI THẮNG directive của tool ĐỌC. Việc HR nhờ làm
    # là "thêm vào shortlist" — cái search_candidates tra ra dọc đường chỉ là bước phụ,
    # không được quyết định HR nhìn thấy gì.
    dieu_huong_ghi: dict | None = None  # navigate cuối cùng do một tool GHI phát ra
    dieu_huong_doc: dict | None = None  # navigate cuối cùng do một tool ĐỌC phát ra
    can_lam_moi = False  # có tool GHI nào chạy mà không tự điều hướng

    def _ui_cuoi() -> list[dict]:
        """`refresh` trước, `navigate` sau — frontend chạy tuần tự nên navigate chốt."""
        out: list[dict] = []
        if can_lam_moi:
            out.append({"type": "refresh"})
        dich = dieu_huong_ghi or dieu_huong_doc
        if dich:
            out.append(dich)
        return out

    def _out(reply: str, error: str | None = None) -> dict:
        d = {
            # Lọc uuid ở ĐÚNG MỘT CỬA RA: mọi nhánh trả lời đều đi qua `_out`, nên không
            # có đường nào lọt ra ngoài mà quên lọc.
            "reply": _bo_uuid(reply),
            "tool_calls": used,
            "steps": steps,
            "ui_actions": _ui_cuoi(),
            "usage": usage,
        }
        if error:
            d["error"] = error
        return d

    bat_dau = time.time()
    for _ in range(MAX_STEPS):
        # TRẦN THỜI GIAN CHO CẢ LƯỢT. `MAX_STEPS` giới hạn SỐ bước nhưng không giới hạn
        # THỜI GIAN: khi Groq chạm trần token/phút, SDK của nó tự chờ rồi thử lại ngầm,
        # nên mỗi bước có thể ngốn hàng chục giây mà code ở đây không hề thấy lỗi.
        # Cộng dồn 10 bước là HR ngồi nhìn "Đang xử lý…" rất lâu — đo được 941 giây cho
        # một câu hỏi tra cứu bình thường. Thà dừng sớm và nói thật.
        if time.time() - bat_dau > TURN_BUDGET:
            log.warning("Lượt agent vượt trần %.0fs, dừng sớm sau %d tool", TURN_BUDGET, len(used))
            return _out(_qua_lau(da_ghi), error=f"turn_budget_exceeded ({TURN_BUDGET}s)")
        try:
            resp = await _complete(messages, tools)
        except Exception as e:  # noqa: BLE001 - trả lời nhẹ nhàng thay vì 500
            # `da_ghi` là phần bắt buộc: lượt LLM cuối (viết câu trả lời) hỏng KHÔNG
            # xoá đi những gì các tool trước đó đã ghi vào DB.
            # GHI NGUYÊN VĂN LỖI THẬT. Câu trả lời cho HR cố tình được viết lại cho dễ
            # hiểu, nên nếu chỗ này không log thì nguyên nhân thật biến mất hoàn toàn —
            # và mọi lỗi khác nhau đều trông giống nhau từ phía màn hình chat.
            log.warning(
                "Lượt agent hỏng sau %d tool (%s): %s", len(used), type(e).__name__, e
            )
            return _out(_friendly_error(e, da_ghi), error=str(e))

        if getattr(resp, "usage", None):
            usage["prompt_tokens"] += resp.usage.prompt_tokens or 0
            usage["completion_tokens"] += resp.usage.completion_tokens or 0

        msg = resp.choices[0].message

        # LLM không gọi tool nữa -> câu trả lời cuối cùng.
        if not msg.tool_calls:
            # Chốt chặn cuối: KHÔNG BAO GIỜ trả chuỗi rỗng lên khung chat. `_complete`
            # đã coi lượt rỗng là lỗi và thử lại, nhưng nếu vì lý do nào đó vẫn lọt tới
            # đây thì HR phải nhận một câu nói được điều gì đã xảy ra, chứ không phải
            # dòng "(không có phản hồi)" — nhất là khi các tool GHI đã chạy xong.
            reply = (msg.content or "").strip()
            if not reply:
                reply = _friendly_error(_TraLoiRong("lượt cuối rỗng"), da_ghi)
            return _out(reply)

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
            vua_ghi = bool(spec) and not spec.read_only and not (
                isinstance(result, dict) and "error" in result
            )
            if vua_ghi:
                da_ghi.append(name)

            # Directive điều hướng giao diện cho frontend.
            co_dieu_huong = isinstance(result, dict) and isinstance(
                result.get("ui_action"), dict
            )
            if co_dieu_huong:
                if vua_ghi:
                    dieu_huong_ghi = result["ui_action"]
                else:
                    dieu_huong_doc = result["ui_action"]

            # Việc mở trang vị trí mới do chính `create_jd` khai (nó trả ui_action).
            # Còn đây là thứ chỉ tầng này làm được: nạp lại danh sách dự án ở cột trái.
            # JD vừa tạo chưa có trong `projects` của frontend, không nạp lại thì trang
            # /projects/<id mới> không tìm thấy nó và đá HR ngược về Dashboard.
            if isinstance(result, dict) and name == "create_jd" and result.get("jd_id"):
                can_lam_moi = True

            # TOOL GHI CHẠY XONG THÌ MÀN HÌNH PHẢI ĐỘNG ĐẬY.
            #
            # Không phải tool ghi nào cũng biết nên mở trang nào (gửi thư mời, sửa JD,
            # gỡ người khỏi shortlist...), nên chúng không trả `ui_action` gì cả — và HR
            # ngồi nhìn dữ liệu cũ cho tới khi tự F5. `refresh` không kéo HR đi đâu, chỉ
            # bảo trang đang mở nạp lại chính nó.
            #
            # Dùng `vua_ghi` (kết quả của ĐÚNG lời gọi này) chứ không phải `name in
            # da_ghi`: cùng một tool có thể chạy hai lần trong một lượt, lần đầu xong
            # lần sau lỗi — tra theo tên thì lần lỗi vẫn được tính là đã ghi.
            if vua_ghi and not co_dieu_huong:
                can_lam_moi = True

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                # Rút gọn TRƯỚC khi vào ngữ cảnh: chuỗi này được gửi lại cho LLM ở
                # MỌI bước còn lại của lượt, nên mỗi ký tự thừa ở đây bị nhân lên.
                "content": json.dumps(_trim_for_llm(result), default=str, ensure_ascii=False),
            })

    # Hết MAX_STEPS. Log ra ĐÚNG chuỗi tool đã gọi: HR chỉ nhờ một việc mà chạm trần
    # bước thì gần như luôn là agent gọi lặp một tool (mỗi lần một tham số hơi khác),
    # và không có danh sách này thì không có cách nào biết nó lặp ở đâu.
    log.warning("Lượt agent chạm trần %d bước; chuỗi tool đã gọi: %s", MAX_STEPS, used)
    return _out(
        "Xin lỗi, yêu cầu cần quá nhiều bước để xử lý. Bạn thử tách nhỏ giúp mình nhé.",
        error=f"max_steps_exceeded ({MAX_STEPS}): {used}",
    )


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
