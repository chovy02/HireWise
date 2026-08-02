"""
Bộ điều tiết nhịp gọi Groq, dùng chung cho MỌI tiến trình (api / worker / mcp).

VÌ SAO CẦN: giới hạn của Groq tính theo TÀI KHOẢN chứ không theo tiến trình. Trước
đây mỗi worker Celery cứ thấy task là gọi thẳng API, nên upload 1 ZIP 15 CV = 45
lời gọi bắn ra gần như cùng lúc -> 429 hàng loạt, retry mù rồi CV bị đánh FAILED.

CÁCH LÀM: đếm số request + số token đã tiêu trong cửa sổ phút/ngày trên Redis
(Redis là nơi duy nhất mọi container nhìn thấy chung). Trước mỗi lời gọi phải ĐẶT
CHỖ trước phần token ước tính; hết ngân sách thì chờ tới lúc cửa sổ mở lại thay vì
cứ bắn rồi ăn 429.

Cửa sổ cố định (fixed window) chứ không phải trượt (sliding) — đơn giản hơn nhiều
và vẫn an toàn vì ta chỉ dùng SAFETY_RATIO (mặc định 85%) ngân sách thật.
"""

import os
import threading
import time
from datetime import datetime, timezone

import redis

# ────────────────────────────────────────────────────────────
# Cấu hình
# ────────────────────────────────────────────────────────────

REDIS_URL = os.getenv(
    "RATE_LIMIT_REDIS_URL",
    os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0").rsplit("/", 1)[0] + "/2",
)

# Chỉ tiêu thụ một phần hạn mức công bố, chừa chỗ cho sai số ước tính token và cho
# các luồng khác (agent chat, MCP) dùng chung tài khoản.
SAFETY_RATIO = float(os.getenv("LLM_SAFETY_RATIO", "0.85"))

# Hạn mức free tier Groq (https://console.groq.com/docs/rate-limits).
# Ghi đè bằng env khi nâng lên Developer tier — KHÔNG cần sửa code.
_DEFAULT_LIMITS = {
    "llama-3.3-70b-versatile": {"rpm": 30, "tpm": 12_000, "rpd": 1_000, "tpd": 100_000},
    "llama-3.1-8b-instant": {"rpm": 30, "tpm": 6_000, "rpd": 14_400, "tpd": 500_000},
    # Model dự phòng cùng đẳng cấp (xem BACKUP_MODEL trong gemini_client). rpm/tpm lấy
    # từ chính header `x-ratelimit-limit-*` của Groq; tpd để mức thận trọng vì header
    # không nói gì về trần ngày — ước thấp thì cùng lắm là chờ sớm hơn cần thiết, ước
    # cao thì đâm thẳng vào 429 và ăn cooldown.
    "openai/gpt-oss-120b": {"rpm": 30, "tpm": 8_000, "rpd": 1_000, "tpd": 100_000},
    "openai/gpt-oss-20b": {"rpm": 30, "tpm": 8_000, "rpd": 1_000, "tpd": 100_000},
}

# Hạn mức cho model lạ (không có trong bảng trên): lấy mức thấp nhất cho an toàn.
_FALLBACK_LIMIT = {"rpm": 30, "tpm": 6_000, "rpd": 1_000, "tpd": 100_000}


def _limits_for(model: str) -> dict:
    """Hạn mức của 1 model, ưu tiên biến môi trường.

    Quy ước env: LLM_LIMIT_<MODEL>_TPM với <MODEL> viết hoa, '-' và '.' -> '_'.
    Ví dụ: LLM_LIMIT_LLAMA_3_3_70B_VERSATILE_TPM=600000
    """
    base = dict(_DEFAULT_LIMITS.get(model, _FALLBACK_LIMIT))
    slug = model.upper().replace("-", "_").replace(".", "_").replace("/", "_")
    for field in ("rpm", "tpm", "rpd", "tpd"):
        raw = os.getenv(f"LLM_LIMIT_{slug}_{field.upper()}")
        if raw:
            base[field] = int(raw)
    return base


# ────────────────────────────────────────────────────────────
# Kết nối Redis (lazy, và KHÔNG được làm sập luồng chính nếu Redis chết)
# ────────────────────────────────────────────────────────────

_redis_client = None
_redis_lock = threading.Lock()


def _get_redis():
    global _redis_client
    if _redis_client is None:
        with _redis_lock:
            if _redis_client is None:
                _redis_client = redis.Redis.from_url(
                    REDIS_URL, socket_timeout=3, socket_connect_timeout=3
                )
    return _redis_client


# Script Lua: kiểm tra 4 hạn mức rồi đặt chỗ, TẤT CẢ trong 1 thao tác nguyên tử.
# Không dùng Lua thì 2 worker cùng đọc "còn 500 token" rồi cùng đặt chỗ -> vượt trần.
_RESERVE_LUA = """
local rpm = tonumber(redis.call('GET', KEYS[1]) or '0')
local tpm = tonumber(redis.call('GET', KEYS[2]) or '0')
local rpd = tonumber(redis.call('GET', KEYS[3]) or '0')
local tpd = tonumber(redis.call('GET', KEYS[4]) or '0')

-- CỬA SỔ TRƯỢT: cộng thêm phần phút TRƯỚC theo trọng số.
--
-- Cửa sổ cố định thuần có lỗ hổng ở mốc giao phút: tiêu sạch ngân sách lúc 10:00:59
-- rồi tiêu sạch lần nữa lúc 10:01:01 là đã bắn gấp đôi hạn mức trong 2 giây, trong
-- khi bộ đếm vẫn thấy "mỗi phút chỉ dùng đúng 1 lần ngân sách". Groq đo theo cửa sổ
-- trượt nên nó thấy hết và trả 429 — đây chính là chỗ rò rỉ 429 đo được khi chạy thử.
local weight = tonumber(ARGV[8])
rpm = rpm + math.floor(tonumber(redis.call('GET', KEYS[6]) or '0') * weight)
tpm = tpm + math.floor(tonumber(redis.call('GET', KEYS[7]) or '0') * weight)

local rpm_max = tonumber(ARGV[1])
local tpm_max = tonumber(ARGV[2])
local rpd_max = tonumber(ARGV[3])
local tpd_max = tonumber(ARGV[4])
local est     = tonumber(ARGV[5])
local minute_left = tonumber(ARGV[6])
local day_left    = tonumber(ARGV[7])

-- Có cooldown do server trả 429 thì nghỉ đúng khoảng nó bảo, không cãi.
local cooldown = redis.call('PTTL', KEYS[5])
if cooldown > 0 then
  return {0, math.ceil(cooldown / 1000), 'cooldown'}
end

-- Trần NGÀY: hết là hết, chờ tới nửa đêm UTC. Trả về để caller quyết định đổi
-- key/model khác thay vì ngồi chờ vô nghĩa.
if rpd + 1 > rpd_max or tpd + est > tpd_max then
  return {0, day_left, 'daily'}
end

-- Trần PHÚT: chờ sang phút mới là dùng tiếp được.
if rpm + 1 > rpm_max or tpm + est > tpm_max then
  return {0, minute_left, 'minute'}
end

redis.call('INCRBY', KEYS[1], 1);   redis.call('EXPIRE', KEYS[1], 120)
redis.call('INCRBY', KEYS[2], est); redis.call('EXPIRE', KEYS[2], 120)
redis.call('INCRBY', KEYS[3], 1);   redis.call('EXPIRE', KEYS[3], 172800)
redis.call('INCRBY', KEYS[4], est); redis.call('EXPIRE', KEYS[4], 172800)
return {1, 0, 'ok'}
"""

_reserve_script = None


def _get_script():
    global _reserve_script
    if _reserve_script is None:
        _reserve_script = _get_redis().register_script(_RESERVE_LUA)
    return _reserve_script


# ────────────────────────────────────────────────────────────
# Dự phòng khi Redis không dùng được
# ────────────────────────────────────────────────────────────

_local_lock = threading.Lock()
_local_last_call = 0.0
# Giãn cách tối thiểu giữa 2 lời gọi khi mất Redis. Không chính xác bằng token
# bucket nhưng vẫn chặn được kiểu bắn dồn dập gây 429.
_LOCAL_MIN_INTERVAL = float(os.getenv("LLM_LOCAL_MIN_INTERVAL", "4"))


def _local_throttle():
    global _local_last_call
    with _local_lock:
        wait = _LOCAL_MIN_INTERVAL - (time.time() - _local_last_call)
        if wait > 0:
            time.sleep(wait)
        _local_last_call = time.time()


# ────────────────────────────────────────────────────────────
# API chính
# ────────────────────────────────────────────────────────────


def _keys(key_id: str, model: str) -> list[str]:
    now = time.time()
    minute = int(now // 60)
    # CỐ Ý DÙNG UTC, KHÔNG ĐỔI SANG UTC+7: đây là sổ đếm ngân sách token/ngày của
    # Groq, và hạn mức phía Groq reset vào NỬA ĐÊM UTC. Đổi mốc ngày sang giờ Việt
    # Nam sẽ khiến cửa sổ đếm của ta lệch 7 tiếng so với cửa sổ thật của nhà cung
    # cấp — hệ quả là có lúc tưởng còn quota nhưng đã bị 429, có lúc tự chặn oan.
    # (Mọi mốc thời gian HIỂN THỊ cho người dùng thì mới quy sang UTC+7.)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"groqrl:{key_id}:{model}"
    return [
        f"{prefix}:req:m:{minute}",
        f"{prefix}:tok:m:{minute}",
        f"{prefix}:req:d:{day}",
        f"{prefix}:tok:d:{day}",
        f"{prefix}:cooldown",
        # Phút trước, dùng cho phần cửa sổ trượt trong script Lua.
        f"{prefix}:req:m:{minute - 1}",
        f"{prefix}:tok:m:{minute - 1}",
    ]


def _prev_minute_weight() -> float:
    """Tỉ lệ phút TRƯỚC còn nằm trong cửa sổ 60 giây tính tới lúc này.

    Đầu phút (giây thứ 0) thì phút trước còn nguyên giá trị (1.0); cuối phút (giây
    thứ 59) thì gần như đã trôi hết (0.017).
    """
    return (60 - (time.time() % 60)) / 60


def _seconds_left_in_minute() -> int:
    return max(1, 60 - int(time.time() % 60))


def _seconds_left_in_day() -> int:
    now = datetime.now(timezone.utc)
    return max(
        1,
        int(86400 - (now.hour * 3600 + now.minute * 60 + now.second)),
    )


def try_reserve(key_id: str, model: str, est_tokens: int) -> tuple[bool, int, str]:
    """
    Thử đặt chỗ `est_tokens` token cho cặp (key_id, model).

    Returns:
        (ok, wait_seconds, reason) — ok=True nghĩa là được phép gọi API ngay.
        reason: 'ok' | 'minute' | 'daily' | 'cooldown' | 'no_redis'.
        Khi ok=False, `wait_seconds` là thời gian tối thiểu phải chờ.
    """
    limits = _limits_for(model)
    rpm = max(1, int(limits["rpm"] * SAFETY_RATIO))
    tpm = max(1, int(limits["tpm"] * SAFETY_RATIO))
    rpd = max(1, int(limits["rpd"] * SAFETY_RATIO))
    tpd = max(1, int(limits["tpd"] * SAFETY_RATIO))

    # Prompt to hơn cả trần TPM thì đặt chỗ kiểu gì cũng trượt vĩnh viễn -> kẹp lại
    # và để lời gọi đi qua; nếu thật sự quá dài thì Groq trả lỗi content, không phải 429.
    est = max(1, min(int(est_tokens), tpm))

    try:
        ok, wait, reason = _get_script()(
            keys=_keys(key_id, model),
            args=[rpm, tpm, rpd, tpd, est, _seconds_left_in_minute(),
                  _seconds_left_in_day(), _prev_minute_weight()],
        )
        reason = reason.decode() if isinstance(reason, bytes) else str(reason)
        return bool(ok), int(wait), reason
    except Exception:  # noqa: BLE001 - Redis hỏng KHÔNG được chặn việc chấm CV
        _local_throttle()
        return True, 0, "no_redis"


def reconcile(key_id: str, model: str, est_tokens: int, actual_tokens: int) -> None:
    """
    Chỉnh lại sổ sách sau khi có số token THẬT từ response.

    Ước tính theo độ dài chuỗi luôn lệch (nhất là tiếng Việt có dấu tốn token hơn),
    nên phải cộng/trừ phần chênh, không thì hoặc là vượt trần thật, hoặc là phí
    quota do đặt chỗ dư.
    """
    delta = int(actual_tokens) - int(est_tokens)
    if delta == 0:
        return
    try:
        keys = _keys(key_id, model)
        pipe = _get_redis().pipeline()
        pipe.incrby(keys[1], delta)
        pipe.expire(keys[1], 120)
        pipe.incrby(keys[3], delta)
        pipe.expire(keys[3], 172800)
        pipe.execute()
    except Exception:  # noqa: BLE001 - sai lệch sổ sách không đáng để hỏng luồng chính
        pass


def cooldown(key_id: str, model: str, seconds: float) -> None:
    """
    Đóng băng cặp (key_id, model) trong `seconds` giây sau khi ăn 429 thật.

    Groq trả header `retry-after` cho biết chính xác lúc nào được gọi lại; tôn trọng
    con số đó tốt hơn nhiều so với đoán mò bằng exponential backoff.
    """
    seconds = max(1.0, float(seconds))
    try:
        _get_redis().set(_keys(key_id, model)[4], "1", px=int(seconds * 1000))
    except Exception:  # noqa: BLE001
        pass


def release_reservation(key_id: str, model: str, est_tokens: int) -> None:
    """Trả lại chỗ đã đặt khi lời gọi hỏng trước lúc tiêu token (vd: lỗi mạng)."""
    reconcile(key_id, model, est_tokens, 0)


def estimate_tokens(prompt: str, expected_output: int = 800) -> int:
    """
    Ước tính token cho 1 lời gọi = prompt + phần output dự kiến.

    ~3 ký tự/token là mức bảo thủ cho văn bản Việt–Anh lẫn lộn của CV (tiếng Anh
    thuần khoảng 4). Thà ước tính dư còn hơn vượt trần rồi ăn 429.
    """
    return int(len(prompt or "") / 3) + int(expected_output)
