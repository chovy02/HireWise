import os
import time
from sqlalchemy.orm import Session
from app.models import AILog

from groq import Groq

# LƯU Ý: file vẫn tên gemini_client vì lịch sử; hiện dùng Groq (OpenAI-compatible,
# free tier). Giữ nguyên hàm generate_text() nên parser/scorer/jd_processor/evidence
# KHÔNG cần sửa gì.

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Model Groq thực dùng; model_name (tên Gemini cũ) do các module truyền vào bị bỏ qua.
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Số lần thử tối đa cho 1 lời gọi trước khi bỏ cuộc (override bằng env khi cần).
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))
# Trần thời gian chờ mỗi lần retry (giây), tránh treo worker quá lâu.
MAX_WAIT = float(os.getenv("LLM_MAX_WAIT", "60"))


def _is_retryable(err: Exception) -> bool:
    """429 (rate limit) và 5xx là lỗi TẠM THỜI -> nên thử lại; khác với lỗi nội
    dung/bad request/auth là fail thật."""
    msg = str(err).lower()
    return any(
        k in msg
        for k in ("429", "rate", "quota", "resource_exhausted",
                  "500", "502", "503", "overloaded", "unavailable", "timeout")
    )


def generate_text(model_name: str, prompt: str) -> str:
    """
    Gọi Groq và trả về text kết quả, tự retry với exponential backoff khi bị rate
    limit (429) hoặc service tạm lỗi (5xx).

    `model_name` (tên model Gemini cũ mà các module truyền vào) được BỎ QUA; model
    thật lấy từ GROQ_MODEL. Bật JSON mode vì mọi prompt trong pipeline đều yêu cầu
    trả về JSON thuần -> đảm bảo output parse được, khỏi cần strip markdown.
    """
    backoff = 5.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = _client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content
        except Exception as e:  # noqa: BLE001 - phân loại lại qua _is_retryable
            if attempt == MAX_RETRIES or not _is_retryable(e):
                raise
            time.sleep(min(backoff, MAX_WAIT))
            backoff *= 2

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