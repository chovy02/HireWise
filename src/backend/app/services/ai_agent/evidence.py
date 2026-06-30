import os
import json
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

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


def _clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


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
        model = genai.GenerativeModel(EVIDENCE_MODEL)
        response = model.generate_content(prompt)
        response_text = _clean_json_response(response.text)
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        return {"evidence_error": f"Không parse được JSON từ response: {e}"}
    except Exception as e:
        return {"evidence_error": f"Lỗi gọi API: {e}"}