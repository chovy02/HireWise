import os
import time
from sqlalchemy.orm import Session
from app.models import AILog
from app.database import SessionLocal

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


def _record_ai_log(agent_name, prompt, completion, total_tokens, latency_ms, is_error, error_message):
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


def generate_text(model_name: str, prompt: str, agent_name: str = None) -> str:
    """
    Gọi Groq và trả về text kết quả, tự retry với exponential backoff khi bị rate
    limit (429) hoặc service tạm lỗi (5xx).

    `model_name` (tên model Gemini cũ mà các module truyền vào) được BỎ QUA; model
    thật lấy từ GROQ_MODEL. Bật JSON mode vì mọi prompt trong pipeline đều yêu cầu
    trả về JSON thuần -> đảm bảo output parse được, khỏi cần strip markdown.

    `agent_name`: nhãn agent để hiển thị ở trang Giám sát AI (vd: cv_parser, scorer).
    Mọi lượt gọi (thành công/lỗi) đều được ghi vào bảng ai_logs kèm token & độ trễ.
    """
    label = agent_name or model_name
    backoff = 5.0
    start_time = time.time()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = _client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
            total_tokens = getattr(getattr(resp, "usage", None), "total_tokens", 0) or 0
            _record_ai_log(
                agent_name=label, prompt=prompt, completion=content,
                total_tokens=total_tokens,
                latency_ms=(time.time() - start_time) * 1000,
                is_error=False, error_message=None,
            )
            return content
        except Exception as e:  # noqa: BLE001 - phân loại lại qua _is_retryable
            if attempt == MAX_RETRIES or not _is_retryable(e):
                _record_ai_log(
                    agent_name=label, prompt=prompt, completion=None,
                    total_tokens=0,
                    latency_ms=(time.time() - start_time) * 1000,
                    is_error=True, error_message=str(e),
                )
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