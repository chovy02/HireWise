import json

from app.services.ai_agent.gemini_client import generate_text

SCORER_MODEL = "gemini-2.5-flash"

SCORE_PROMPT = """Bạn là chuyên gia tuyển dụng. Đánh giá mức độ phù hợp của ứng viên với yêu cầu công việc.
Trả về DUY NHẤT một object JSON, không kèm giải thích, không markdown.

Yêu cầu công việc (JD):
---
{jd_requirements}
---

Thông tin ứng viên (đã trích xuất từ CV):
---
{candidate_info}
---

Schema JSON cần trả về:
{
  "score": 0,
  "explanation": "string giải thích ngắn gọn lý do điểm số (2-3 câu)",
  "strengths": ["string các điểm mạnh phù hợp với JD"],
  "weaknesses": ["string các điểm còn thiếu so với JD"],
  "score_breakdown": {
    "skills_match": 0,
    "experience_match": 0,
    "education_match": 0
  }
}

Quy tắc:
- score và các trường trong score_breakdown là số nguyên từ 0 đến 100.
- Cân nhắc kỹ năng tương đương (vd: Jira và Trello đều là công cụ quản lý Agile).
- Xem xét cả certifications và awards khi đánh giá.
- Nếu ứng viên thiếu thông tin cho một tiêu chí, ghi nhận trong weaknesses thay vì tự suy diễn.
- Không bịa thông tin không có trong CV."""


def _clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def score_cv(candidate_info: dict, jd_requirements: dict) -> dict:
    if not candidate_info or candidate_info.get("parse_error"):
        return {"score_error": "Thông tin ứng viên không hợp lệ để chấm điểm."}
    try:
        prompt = SCORE_PROMPT.replace(
            "{jd_requirements}",
            json.dumps(jd_requirements, ensure_ascii=False, indent=2),
        ).replace(
            "{candidate_info}",
            json.dumps(candidate_info, ensure_ascii=False, indent=2),
        )
        response_text = _clean_json_response(generate_text(SCORER_MODEL, prompt))
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        return {"score_error": f"Không parse được JSON từ response: {e}"}
    except Exception as e:
        return {"score_error": f"Lỗi gọi API: {e}"}