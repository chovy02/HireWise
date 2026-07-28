import json

from app.services.ai_agent.exceptions import LLMBudgetExhausted
from app.services.ai_agent.gemini_client import generate_text
from app.services.ai_agent.prompt_utils import clean_json_response

# KHÔNG CÒN NẰM TRONG LUỒNG UPLOAD. Việc tìm bằng chứng đã được gộp vào scorer.py
# để bớt 1 lượt gọi API và bớt 1 lần gửi full text CV cho mỗi ứng viên — đó là thay
# đổi then chốt giúp upload ZIP nhiều CV không đụng rate limit của Groq free tier.
# Giữ lại module này cho các script/test gọi trực tiếp.

EVIDENCE_MODEL = "gemini-2.5-flash"

EVIDENCE_PROMPT = """Bạn là công cụ tìm bằng chứng. Dựa vào CV gốc, tìm đoạn văn bản NGUYÊN VĂN trong CV làm căn cứ cho từng nhận định.
Trả về DUY NHẤT một object JSON, không kèm giải thích, không markdown.

CV gốc:
---
{cv_text}
---

Các nhận định cần tìm bằng chứng:
Điểm mạnh: {strengths}
Điểm yếu: {weaknesses}

Schema JSON cần trả về:
{
  "strengths_evidence": {
    "tên nhận định": "câu trích NGUYÊN VĂN từ CV, hoặc null nếu không tìm thấy"
  },
  "weaknesses_evidence": {
    "tên nhận định": "câu trích NGUYÊN VĂN từ CV, hoặc null nếu không tìm thấy"
  }
}

Quy tắc:
- CHỈ trích nguyên văn từ CV, tuyệt đối không bịa hay diễn giải.
- Nếu không tìm được bằng chứng, để giá trị null.
- Giữ nguyên key là tên nhận định gốc."""


def generate_evidence(cv_text: str, score_result: dict) -> dict:
    if not cv_text or not cv_text.strip():
        return {"evidence_error": "CV rỗng, không có text để tìm bằng chứng."}
    if score_result.get("score_error"):
        return {"evidence_error": "Kết quả chấm điểm không hợp lệ."}
    strengths = score_result.get("strengths", [])
    weaknesses = score_result.get("weaknesses", [])
    try:
        prompt = EVIDENCE_PROMPT.replace(
            "{cv_text}", cv_text
        ).replace(
            "{strengths}", json.dumps(strengths, ensure_ascii=False)
        ).replace(
            "{weaknesses}", json.dumps(weaknesses, ensure_ascii=False)
        )
        response_text = clean_json_response(
            generate_text(EVIDENCE_MODEL, prompt, agent_name="evidence")
        )
        return json.loads(response_text)
    except LLMBudgetExhausted:
        raise
    except json.JSONDecodeError as e:
        return {"evidence_error": f"Không parse được JSON từ response: {e}"}
    except Exception as e:
        return {"evidence_error": f"Lỗi gọi API: {e}"}