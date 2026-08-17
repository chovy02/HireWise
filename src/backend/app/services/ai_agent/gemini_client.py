import os
import re
import time
import threading

from sqlalchemy.orm import Session
from app.models import AILog
from app.database import SessionLocal
from app.services.ai_agent import rate_limiter
from app.services.ai_agent.exceptions import (
    AIServiceError,
    LLMBudgetExhausted,
    LLMResponseTruncated,
)

from groq import Groq

# LƯU Ý: file vẫn tên gemini_client vì lịch sử; hiện dùng Groq (OpenAI-compatible,
# free tier). Giữ nguyên chữ ký generate_text() nên parser/scorer/jd_processor
# KHÔNG cần sửa gì.
#
# BÀI TOÁN CỦA FILE NÀY: free tier Groq chặn theo TOKEN/PHÚT (12k với model 70b),
# không phải theo số request. Một ZIP 15 CV tiêu vài trăm nghìn token, nên cách duy
# nhất để chạy trọn vẹn là RẢI ĐỀU lời gọi trong ngân sách thay vì bắn hết rồi retry.
# Ba tuyến phòng thủ, theo thứ tự:
#   1. rate_limiter đặt chỗ token trước khi gọi  -> phần lớn 429 không bao giờ xảy ra.
#   2. Còn ăn 429 thì đọc `retry-after` của Groq -> nghỉ đúng bằng con số nó bảo.
#   3. Chờ quá lâu thì ném LLMBudgetExhausted    -> Celery hẹn giờ chạy lại CV đó.

# ────────────────────────────────────────────────────────────
# Pool API key
# ────────────────────────────────────────────────────────────
# Hạn mức Groq tính theo TÀI KHOẢN. Nhiều key CÙNG một tài khoản thì KHÔNG tăng
# quota; chỉ key của TÀI KHOẢN KHÁC mới cộng thêm ngân sách thật.
#
# Pipeline chấm CV dùng GROQ_API_KEY_1 + GROQ_API_KEY_2 (hai tài khoản Groq riêng)
# -> ngân sách token gấp đôi. GROQ_API_KEY (tên cũ) vẫn được chấp nhận để .env cũ
# không gãy.
# CỐ Ý KHÔNG đụng tới GROQ_MCP_API_KEY: key đó dành riêng cho agent chat (agent.py).
# Gộp chung thì lúc HR đang upload ZIP, khung chat sẽ đứng hình vì hết token —
# tách ra để hai tính năng không giành quota của nhau.
_KEY_ENV_NAMES = ("GROQ_API_KEY_1", "GROQ_API_KEY_2")


def _load_keys() -> list[tuple[str, str]]:
    """Trả list (key_id, api_key). key_id chỉ để đánh nhãn sổ sách trên Redis."""
    raw_keys: list[str] = []
    # GROQ_API_KEYS (danh sách ngăn cách dấu phẩy) để thêm tài khoản thứ 3, 4...
    # mà không phải sửa code.
    for item in (os.getenv("GROQ_API_KEYS") or "").split(","):
        if item.strip():
            raw_keys.append(item.strip())
    for name in _KEY_ENV_NAMES:
        value = (os.getenv(name) or "").strip()
        if value:
            raw_keys.append(value)

    # GROQ_API_KEY (tên cũ) CHỈ dùng khi chưa khai báo tên mới. Cộng gộp cả hai sẽ
    # rất tai hại nếu chúng là cùng một tài khoản: bộ đếm tưởng có hai ngân sách độc
    # lập nên cấp phát gấp đôi, và ta lại rơi đúng vào 429 như trước.
    if not raw_keys:
        legacy = (os.getenv("GROQ_API_KEY") or "").strip()
        if legacy:
            raw_keys.append(legacy)

    # Khử trùng, giữ thứ tự — cùng lý do trên.
    keys = list(dict.fromkeys(raw_keys))
    if not keys:
        raise AIServiceError(
            "Chưa cấu hình GROQ_API_KEY_1 / GROQ_API_KEY_2 trong biến môi trường."
        )
    # key_id = 8 ký tự cuối, đủ phân biệt mà không lộ key vào log/Redis.
    return [(k[-8:], k) for k in keys]


_clients: dict[str, Groq] = {}
_clients_lock = threading.Lock()


def _client_for(key_id: str, api_key: str) -> Groq:
    """Groq client tái sử dụng theo key (mở client mới mỗi lời gọi là phí kết nối)."""
    if key_id not in _clients:
        with _clients_lock:
            if key_id not in _clients:
                # max_retries=0: TẮT retry tự động của SDK.
                #
                # Mặc định SDK tự nuốt 429 rồi backoff mù trong tiến trình của nó.
                # Nghe thì tiện, nhưng nó (a) giấu luôn 429 khỏi lớp điều tiết nên
                # rate_limiter không bao giờ học được là phải lùi lại, (b) không đọc
                # `retry-after`, và (c) các worker khác vẫn thản nhiên bắn tiếp vào
                # đúng cái trần đang cạn. Để lớp bên dưới tự xử lý thì cooldown mới
                # lan được ra MỌI tiến trình qua Redis.
                _clients[key_id] = Groq(api_key=api_key, max_retries=0)
    return _clients[key_id]


# ────────────────────────────────────────────────────────────
# Chọn model theo loại việc
# ────────────────────────────────────────────────────────────
# Groq tính hạn mức RIÊNG cho từng model, nên dùng thêm model thứ hai là CỘNG THÊM
# ngân sách thật, không chỉ là đổi model.
#
# CHÍNH SÁCH (cố ý khác nhau giữa hai loại việc):
#   - cv_parser: thử model chính trước, hết chỗ thì rớt xuống model rút gọn. Trích
#     xuất là việc máy móc nên CV này parse bằng model lớn, CV kia bằng model nhỏ
#     cũng không làm lệch thứ hạng; đổi lại throughput tăng mạnh.
#   - cv_scorer: KHÓA CỨNG ở model chính, thà xếp hàng chờ. Điểm số là thứ tạo ra bảng
#     xếp hạng — chấm mỗi ứng viên bằng một model khác nhau là so sánh không công bằng.

# MẶC ĐỊNH PHẢI LÀ MODEL TÀI KHOẢN THẬT SỰ CÒN ĐƯỢC GỌI.
#
# Trước đây mặc định là `llama-3.3-70b-versatile` / `llama-3.1-8b-instant`. Groq đã gỡ
# cả họ llama-3.x khỏi free tier: mọi lời gọi trả 404 `model_not_found`, mà 404 không
# phải 429 cũng không phải lỗi tạm thời nên nó xuyên thẳng qua mọi lớp retry — HR nhận
# "AI không sinh được câu hỏi" cho TOÀN BỘ danh sách, còn log chỉ thấy 404. Danh sách
# model thật của tài khoản lấy bằng:
#   curl -H "Authorization: Bearer $GROQ_API_KEY_1" https://api.groq.com/openai/v1/models
SMART_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
FAST_MODEL = os.getenv("GROQ_MODEL_FAST", "openai/gpt-oss-20b")

# Model DỰ PHÒNG cùng đẳng cấp với SMART_MODEL (không phải model rút gọn như
# FAST_MODEL). Ngân sách của nó hoàn toàn tách biệt: Groq tính TPM theo TỪNG model, nên
# mỗi model thêm vào chuỗi là cộng thêm 8.000 TPM thật.
BACKUP_MODEL = os.getenv("GROQ_MODEL_BACKUP", "openai/gpt-oss-20b")

# Agent được phép rớt xuống model nhanh khi model chính hết chỗ.
# Để trống (LLM_FALLBACK_AGENTS=) nếu muốn mọi việc chạy hết bằng SMART_MODEL.
_FALLBACK_AGENTS = {
    a.strip() for a in os.getenv("LLM_FALLBACK_AGENTS", "cv_parser").split(",") if a.strip()
}

# Agent được phép rớt xuống BACKUP_MODEL khi model chính hết chỗ.
#
# VÌ SAO CẦN: các việc dưới đây chạy ĐỒNG BỘ ngay trong lượt chat của HR — HR gõ
# "chấm câu trả lời này" rồi ngồi đợi. Khoá cứng ở một model nghĩa là hễ model đó dính
# cooldown (đã gặp thật: chờ ~21 phút) thì cả tính năng đứng im, và HR chỉ nhận được
# "AI đang không chấm được". Trong khi Groq tính hạn mức theo TỪNG MODEL, tức luôn còn
# một ngân sách khác chưa hề đụng tới.
#
# CỐ Ý KHÔNG CÓ cv_scorer Ở ĐÂY. Điểm số tạo ra bảng xếp hạng, chấm mỗi ứng viên bằng
# một model khác nhau là so sánh không công bằng — việc đó thà xếp hàng chờ. Các agent
# dưới đây thì mỗi lượt là một sản phẩm độc lập (một bộ câu hỏi, một bản nhận xét), đổi
# model không làm ai bị so sánh lệch với ai.
_BACKUP_AGENTS = {
    a.strip()
    for a in os.getenv(
        "LLM_BACKUP_AGENTS",
        "interview_questions,interview_evaluate,interview_summary,comparator,jd_processor,evidence",
    ).split(",")
    if a.strip()
}


def _models_for(agent_name: str) -> list[str]:
    """Danh sách model theo thứ tự ưu tiên cho 1 agent.

    Thứ tự = NĂNG LỰC giảm dần: model chính -> model dự phòng cùng đẳng cấp -> model
    rút gọn. `_acquire_slot` duyệt đúng thứ tự này và lấy chỗ đầu tiên còn ngân sách,
    nên chất lượng chỉ giảm khi thực sự không còn lựa chọn nào tốt hơn.
    """
    chain = [SMART_MODEL]
    if agent_name in _BACKUP_AGENTS and BACKUP_MODEL and BACKUP_MODEL not in chain:
        chain.append(BACKUP_MODEL)
    if agent_name in _FALLBACK_AGENTS and FAST_MODEL and FAST_MODEL not in chain:
        chain.append(FAST_MODEL)
    return chain

# Số token output dự kiến theo từng agent, dùng để ĐẶT CHỖ trước cho sát thực tế.
_EXPECTED_OUTPUT = {
    "cv_parser": 1400,
    # Bản đánh giá chi tiết (điểm + nhận xét từng trục, đối chiếu từng yêu cầu JD,
    # điểm mạnh/yếu, rủi ro, gợi ý phỏng vấn) dài gấp ~2.5 lần bản cũ. Đặt chỗ thiếu
    # thì rate limiter tưởng còn dư ngân sách, cho chạy rồi bị Groq chặn ở giữa batch.
    "cv_scorer": 2600,
    "jd_processor": 700,
    "evidence": 500,
}
_DEFAULT_EXPECTED_OUTPUT = 800

# Trần output. Phải đủ rộng cho JSON của CV dài, nếu không JSON bị cắt giữa chừng
# và lỗi hiện ra dưới dạng "không parse được JSON" — rất khó đoán ra nguyên nhân.
MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))

# Số lần thử tối đa cho 1 lời gọi trước khi bỏ cuộc.
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "4"))
# Tổng thời gian tối đa chịu chờ ngân sách token trong 1 lời gọi. Quá mức này thì
# nhả ra cho Celery hẹn lại, để worker không bị 1 CV chiếm chỗ hàng chục phút.
MAX_WAIT_TOTAL = float(os.getenv("LLM_MAX_WAIT_TOTAL", "180"))
# Trần cho MỘT lần nghỉ, tránh ngủ một mạch tới nửa đêm khi đụng trần ngày.
MAX_WAIT_PER_SLEEP = float(os.getenv("LLM_MAX_WAIT", "60"))


# ────────────────────────────────────────────────────────────
# Đọc thời gian chờ do Groq chỉ định
# ────────────────────────────────────────────────────────────

_DURATION_RE = re.compile(
    r"(?:(\d+(?:\.\d+)?)\s*m(?!s))?\s*(?:(\d+(?:\.\d+)?)\s*s)?", re.IGNORECASE
)


def _parse_duration(value: str) -> float | None:
    """Đổi '7.66s', '2m59.56s', '120' thành số giây."""
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return float(value)
    m = _DURATION_RE.match(value)
    if not m or not (m.group(1) or m.group(2)):
        return None
    return float(m.group(1) or 0) * 60 + float(m.group(2) or 0)


def _retry_after_seconds(err: Exception) -> float | None:
    """
    Lấy thời gian chờ CHÍNH XÁC mà Groq trả về khi 429.

    Quan trọng hơn nhiều so với exponential backoff: khi trần TOKEN/PHÚT cạn, Groq
    bảo chờ vài phút; backoff mù 5-10-20s chỉ tổ đốt hết lượt retry rồi báo lỗi
    trong khi chỉ cần chờ đúng lúc là chạy được.
    """
    resp = getattr(err, "response", None)
    headers = getattr(resp, "headers", None)
    if headers is not None:
        for name in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
            try:
                parsed = _parse_duration(headers.get(name) or "")
            except Exception:  # noqa: BLE001 - header lạ thì bỏ qua
                parsed = None
            if parsed:
                return parsed
    # Không có header thì moi từ body: "Please try again in 6m30.5s".
    m = re.search(r"try again in\s+([0-9hms.\s]+)", str(err), re.IGNORECASE)
    if m:
        return _parse_duration(m.group(1))
    return None


# Model mà NHÀ CUNG CẤP không phục vụ nữa (hoặc tài khoản không có quyền) -> Groq trả
# 404 `model_not_found`. Nhớ lại trong tiến trình để không hỏi lại cùng một model đã
# chết ở mọi lời gọi sau: một lô 7 ứng viên = 7 lần đâm vào đúng bức tường đó.
MODEL_KHONG_TON_TAI: set[str] = set()


def is_model_missing(err: Exception) -> bool:
    """Lỗi này là 'model không tồn tại', tức ĐỔI MODEL mới cứu được — retry thì vô ích.

    Đây là lỗi đã làm chết tính năng sinh câu hỏi phỏng vấn: Groq gỡ llama-3.x khỏi free
    tier, mà 404 không rơi vào nhánh 429 lẫn nhánh lỗi tạm thời nên nó xuyên thẳng ra
    ngoài, trong khi chuỗi model dự phòng vẫn còn nguyên một model chạy tốt chưa hề thử.
    """
    msg = str(err).lower()
    return "model_not_found" in msg or ("404" in msg and "does not exist" in msg)


def _is_rate_limit(err: Exception) -> bool:
    msg = str(err).lower()
    return "429" in msg or "rate limit" in msg or "rate_limit" in msg or "quota" in msg


def _is_transient(err: Exception) -> bool:
    """5xx / timeout / mất kết nối: lỗi TẠM THỜI, thử lại là được."""
    msg = str(err).lower()
    return any(
        k in msg
        for k in ("500", "502", "503", "504", "overloaded", "unavailable",
                  "timeout", "timed out", "connection", "temporarily")
    )


# ────────────────────────────────────────────────────────────
# Ghi log AI
# ────────────────────────────────────────────────────────────


def record_ai_log(agent_name, prompt, completion, total_tokens, latency_ms, is_error, error_message):
    """Ghi 1 dòng AILog để trang Giám sát AI (admin) thống kê request/độ trễ/token/lỗi.

    Dùng session RIÊNG (SessionLocal) để không đụng transaction của caller — hàm này
    được gọi cả trong Celery worker lẫn request API. Lỗi khi ghi log KHÔNG được làm
    hỏng luồng chính, nên nuốt mọi exception.
    """
    db = SessionLocal()
    try:
        db.add(AILog(
            agent_name=agent_name,
            prompt=prompt,
            completion=completion,
            total_tokens=total_tokens or 0,
            latency_ms=round(latency_ms, 2),
            is_error=is_error,
            error_message=error_message,
        ))
        db.commit()
    except Exception:  # noqa: BLE001 - log lỗi không được phá luồng chính
        db.rollback()
    finally:
        db.close()


# ────────────────────────────────────────────────────────────
# Xin suất gọi
# ────────────────────────────────────────────────────────────


def _acquire_slot(
    models: list[str], prompt: str, expected_out: int, deadline: float
) -> tuple[str, str, str, int]:
    """
    Chờ tới khi có ngân sách token rồi trả về (key_id, api_key, model, est_tokens).

    Duyệt mọi cặp (model, key) theo thứ tự ưu tiên: cặp nào còn chỗ thì dùng ngay,
    không cặp nào còn thì ngủ tới lúc cặp sớm nhất mở lại. Nhờ vậy 2 tài khoản Groq
    × 2 model = 4 ngân sách độc lập, tự động dùng hết công suất mà chỗ gọi không
    cần biết gì.

    Ước tính token tính LẠI cho từng model vì trần TPM mỗi model một khác.

    Raises:
        LLMBudgetExhausted: chờ quá `deadline` mà vẫn chưa tới lượt.
    """
    keys = _load_keys()
    while True:
        soonest = None
        reasons = set()
        for model in models:
            est = rate_limiter.estimate_tokens(prompt, expected_out)
            for key_id, api_key in keys:
                ok, wait, reason = rate_limiter.try_reserve(key_id, model, est)
                if ok:
                    return key_id, api_key, model, est
                reasons.add(reason)
                if soonest is None or wait < soonest:
                    soonest = wait

        remaining = deadline - time.time()
        if remaining <= 0 or (soonest or 0) > remaining:
            raise LLMBudgetExhausted(
                f"Hết ngân sách token cho {'/'.join(models)} "
                f"({'/'.join(sorted(reasons)) or 'unknown'}); cần chờ ~{int(soonest or 0)}s.",
                retry_after=float(soonest or 60),
            )
        time.sleep(min(soonest or 1, MAX_WAIT_PER_SLEEP, remaining))


# ────────────────────────────────────────────────────────────
# Hàm gọi chính
# ────────────────────────────────────────────────────────────


def generate_text(model_name: str, prompt: str, agent_name: str = None) -> str:
    """
    Gọi Groq và trả về text kết quả.

    `model_name` (tên model Gemini cũ mà các module truyền vào) được BỎ QUA; model
    thật do `_models_for(agent_name)` quyết định. Bật JSON mode vì mọi prompt trong
    pipeline đều yêu cầu trả về JSON thuần -> khỏi phải strip markdown.

    `agent_name`: nhãn agent để hiển thị ở trang Giám sát AI (vd: cv_parser, cv_scorer)
    và cũng là căn cứ chọn model. Mọi lượt gọi đều được ghi vào bảng ai_logs.

    Raises:
        LLMBudgetExhausted: hết quota, ĐÁNG THỬ LẠI SAU (Celery sẽ hẹn giờ).
        LLMResponseTruncated: JSON bị cắt vì chạm trần output.
    """
    label = agent_name or model_name
    models = [m for m in _models_for(label) if m not in MODEL_KHONG_TON_TAI]
    if not models:
        raise AIServiceError(
            f"Không còn model nào dùng được cho {label}: "
            f"{', '.join(sorted(MODEL_KHONG_TON_TAI))} đều bị Groq trả model_not_found. "
            "Cập nhật GROQ_MODEL / GROQ_MODEL_BACKUP theo danh sách model thật của tài "
            "khoản (GET https://api.groq.com/openai/v1/models)."
        )
    expected_out = _EXPECTED_OUTPUT.get(label, _DEFAULT_EXPECTED_OUTPUT)

    start_time = time.time()
    deadline = start_time + MAX_WAIT_TOTAL
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        key_id, api_key, model, est_tokens = _acquire_slot(
            models, prompt, expected_out, deadline
        )
        try:
            resp = _client_for(key_id, api_key).chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=MAX_OUTPUT_TOKENS,
                response_format={"type": "json_object"},
            )
            choice = resp.choices[0]
            content = choice.message.content
            total_tokens = getattr(getattr(resp, "usage", None), "total_tokens", 0) or 0

            # Cập nhật sổ sách bằng số token THẬT (ước tính luôn lệch ít nhiều).
            rate_limiter.reconcile(key_id, model, est_tokens, total_tokens)

            # JSON bị cắt vì chạm trần output. Không phát hiện ở đây thì lát nữa nó
            # hiện ra thành "không parse được JSON" và rất dễ đổ oan cho rate limit.
            if getattr(choice, "finish_reason", None) == "length":
                raise LLMResponseTruncated(
                    f"Model trả về JSON bị cắt vì chạm trần {MAX_OUTPUT_TOKENS} token "
                    "(CV quá dài). Tăng biến môi trường LLM_MAX_OUTPUT_TOKENS nếu cần."
                )

            record_ai_log(
                agent_name=label, prompt=prompt, completion=content,
                total_tokens=total_tokens,
                latency_ms=(time.time() - start_time) * 1000,
                is_error=False, error_message=None,
            )
            return content

        except LLMResponseTruncated as e:
            # Lỗi tất định: thử lại y nguyên cũng cắt đúng chỗ đó, nên báo lỗi luôn.
            record_ai_log(
                agent_name=label, prompt=prompt, completion=None, total_tokens=0,
                latency_ms=(time.time() - start_time) * 1000,
                is_error=True, error_message=str(e),
            )
            raise

        except Exception as e:  # noqa: BLE001 - phân loại lại ngay bên dưới
            last_error = e
            # Lời gọi hỏng thì token chưa bị tiêu -> trả lại chỗ đã đặt.
            rate_limiter.release_reservation(key_id, model, est_tokens)

            if is_model_missing(e):
                # Model này KHÔNG BAO GIỜ chạy lại được: gạch tên rồi thử ngay model kế
                # tiếp trong chuỗi, thay vì để cả tính năng chết theo một model đã bị
                # nhà cung cấp gỡ.
                MODEL_KHONG_TON_TAI.add(model)
                models = [m for m in models if m != model]
                if models and attempt < MAX_RETRIES:
                    continue
                record_ai_log(
                    agent_name=label, prompt=prompt, completion=None, total_tokens=0,
                    latency_ms=(time.time() - start_time) * 1000,
                    is_error=True, error_message=str(e),
                )
                raise AIServiceError(
                    f"Groq không còn phục vụ model {model} cho tài khoản này và chuỗi "
                    "dự phòng đã cạn. Cập nhật GROQ_MODEL / GROQ_MODEL_BACKUP theo "
                    "GET https://api.groq.com/openai/v1/models."
                ) from e

            if _is_rate_limit(e):
                # Vẫn ăn 429 dù đã đặt chỗ: nghĩa là có luồng khác (agent chat, script
                # chạy tay...) cũng đang tiêu quota. Đóng băng đúng khoảng Groq yêu cầu
                # để mọi tiến trình cùng lùi lại, thay vì thay nhau đâm đầu vào tường.
                wait = _retry_after_seconds(e) or 30.0
                rate_limiter.cooldown(key_id, model, wait)
                if attempt < MAX_RETRIES and time.time() + wait <= deadline:
                    time.sleep(min(wait, MAX_WAIT_PER_SLEEP))
                    continue
                record_ai_log(
                    agent_name=label, prompt=prompt, completion=None, total_tokens=0,
                    latency_ms=(time.time() - start_time) * 1000,
                    is_error=True, error_message=str(e),
                )
                raise LLMBudgetExhausted(
                    f"Groq báo vượt hạn mức, cần chờ ~{int(wait)}s.", retry_after=wait
                ) from e

            if _is_transient(e) and attempt < MAX_RETRIES:
                time.sleep(min(2 ** attempt, MAX_WAIT_PER_SLEEP))
                continue

            record_ai_log(
                agent_name=label, prompt=prompt, completion=None, total_tokens=0,
                latency_ms=(time.time() - start_time) * 1000,
                is_error=True, error_message=str(e),
            )
            raise

    # Hết lượt thử mà vẫn toàn lỗi tạm thời.
    record_ai_log(
        agent_name=label, prompt=prompt, completion=None, total_tokens=0,
        latency_ms=(time.time() - start_time) * 1000,
        is_error=True, error_message=str(last_error),
    )
    raise AIServiceError(f"Gọi AI thất bại sau {MAX_RETRIES} lần thử: {last_error}")


def execute_and_log_ai(db: Session, agent_name: str, prompt: str, ai_action_func):
    """
    Hàm Wrapper: Đo thời gian, bắt lỗi và lưu log tự động.
    `ai_action_func` là một lambda hoặc function trả về (response_text, token_count).
    """
    start_time = time.time()
    log_entry = AILog(agent_name=agent_name, prompt=prompt)

    try:
        # Thực thi hàm gọi LLM (VD: model.generate_content)
        response_text, token_count = ai_action_func()

        # Ghi nhận thành công
        log_entry.completion = response_text
        log_entry.total_tokens = token_count
        log_entry.is_error = False

        return response_text

    except Exception as e:
        # Ghi nhận lỗi
        log_entry.is_error = True
        log_entry.error_message = str(e)
        raise e

    finally:
        # Tính toán ms và lưu DB dù thành công hay thất bại
        log_entry.latency_ms = (time.time() - start_time) * 1000
        db.add(log_entry)
        db.commit()
