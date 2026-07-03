import os
import re
import time

import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Số lần thử tối đa cho 1 lời gọi Gemini trước khi bỏ cuộc (override bằng env khi cần).
MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "5"))
# Trần thời gian chờ mỗi lần retry (giây), tránh treo worker quá lâu.
MAX_WAIT = float(os.getenv("GEMINI_MAX_WAIT", "60"))

_RETRY_HINT_RE = re.compile(r"retry in ([\d.]+)s", re.IGNORECASE)


def _is_retryable(err: Exception) -> bool:
    """429 (hết RPM/quota tạm thời) và 503 là lỗi TẠM THỜI -> nên thử lại,
    khác với lỗi nội dung/bad request là fail thật."""
    msg = str(err).lower()
    return any(k in msg for k in ("429", "resource_exhausted", "quota", "503", "unavailable"))


def generate_text(model_name: str, prompt: str) -> str:
    """
    Gọi Gemini và trả về response.text, tự retry với exponential backoff khi bị
    rate limit (429) hoặc service tạm lỗi (503).

    Free tier giới hạn vài request/phút; upload 1 batch CV bắn nhiều lời gọi cùng lúc
    rất dễ dính 429. Nếu message có gợi ý "retry in Xs" thì chờ đúng khoảng đó, nếu
    không thì backoff 5s, 10s, 20s... Vượt quá MAX_RETRIES mới ném lỗi ra ngoài.
    """
    model = genai.GenerativeModel(model_name)
    backoff = 5.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return model.generate_content(prompt).text
        except Exception as e:  # noqa: BLE001 - phân loại lại qua _is_retryable
            if attempt == MAX_RETRIES or not _is_retryable(e):
                raise
            hint = _RETRY_HINT_RE.search(str(e))
            wait = float(hint.group(1)) + 1 if hint else backoff
            time.sleep(min(wait, MAX_WAIT))
            backoff *= 2
