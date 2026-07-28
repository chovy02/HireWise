import json
import os

from app.services.ai_agent.exceptions import LLMBudgetExhausted
from app.services.ai_agent.gemini_client import generate_text
from app.services.ai_agent.prompt_utils import clean_json_response

SCORER_MODEL = "gemini-2.5-flash"

# Bằng chứng được tìm NGAY TRONG lượt chấm điểm, thay vì thêm một lượt gọi riêng.
#
# VÌ SAO GỘP: bản cũ gọi API 3 lần/CV và gửi full text CV tới 2 lần (parse + evidence).
# Với trần 12k token/phút của Groq free tier, riêng khoản đó đã ngốn ~40% ngân sách
# mỗi CV, khiến upload 15 CV chắc chắn đụng rate limit. Gộp lại còn 2 lượt/CV, và
# lượt này chỉ nhận thông tin ĐÃ TRÍCH (gọn hơn CV gốc nhiều lần).
#
# Đặt LLM_EVIDENCE_FROM_CV=1 nếu cần trích dẫn đúng nguyên văn CV gốc: chính xác
# hơn nhưng tốn thêm ~2-3k token/CV.
EVIDENCE_FROM_CV = os.getenv("LLM_EVIDENCE_FROM_CV", "0") == "1"

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
{cv_section}
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
  },
  "strengths_evidence": {
    "tên điểm mạnh": "câu trích từ dữ liệu ứng viên làm căn cứ, hoặc null"
  },
  "weaknesses_evidence": {
    "tên điểm yếu": "câu trích làm căn cứ, hoặc null nếu là do THIẾU thông tin"
  }
}

Quy tắc:
- score và các trường trong score_breakdown là số nguyên từ 0 đến 100.
- Cân nhắc kỹ năng tương đương (vd: Jira và Trello đều là công cụ quản lý Agile).
- Xem xét cả certifications và awards khi đánh giá.
- Nếu ứng viên thiếu thông tin cho một tiêu chí, ghi nhận trong weaknesses thay vì tự suy diễn.
- Không bịa thông tin không có trong CV.
- strengths_evidence / weaknesses_evidence: key phải TRÙNG KHỚP từng phần tử trong
  strengths / weaknesses ở trên. Giá trị chỉ được trích từ dữ liệu đã cho, tuyệt đối
  không bịa. Không tìm được căn cứ thì để null."""

_CV_SECTION = """
Nội dung CV gốc (dùng để trích dẫn nguyên văn làm bằng chứng):
---
{cv_text}
---
"""

# Các key thuộc về "bằng chứng", tách khỏi kết quả chấm điểm sau khi model trả lời.
_EVIDENCE_KEYS = ("strengths_evidence", "weaknesses_evidence")


def _split_evidence(result: dict) -> dict:
    """Tách phần bằng chứng ra khỏi dict điểm số (2 phần lưu ở 2 cột DB khác nhau)."""
    return {k: result.pop(k) for k in _EVIDENCE_KEYS if k in result}


def score_cv(candidate_info: dict, jd_requirements: dict, raw_text: str = None) -> dict:
    """
    Chấm điểm ứng viên so với JD, đồng thời sinh luôn bằng chứng cho từng nhận định.

    Kết quả trả về có thêm key "evidence" (dict) so với bản cũ — pipeline lấy key này
    thay cho lượt gọi generate_evidence() riêng.

    Raises:
        LLMBudgetExhausted: hết quota Groq — để Celery hẹn giờ chấm lại, không đánh
        CV thành FAILED.
    """
    if not candidate_info or candidate_info.get("parse_error"):
        return {"score_error": "Thông tin ứng viên không hợp lệ để chấm điểm."}
    try:
        cv_section = ""
        if EVIDENCE_FROM_CV and raw_text and raw_text.strip():
            cv_section = _CV_SECTION.replace("{cv_text}", raw_text)

        prompt = SCORE_PROMPT.replace(
            "{jd_requirements}",
            # separators gọn (không indent): JSON lồng nhau của JD/CV mà format đẹp
            # thì riêng dấu cách và xuống dòng đã ngốn cả trăm token mỗi lượt gọi.
            json.dumps(jd_requirements, ensure_ascii=False, separators=(",", ":")),
        ).replace(
            "{candidate_info}",
            json.dumps(candidate_info, ensure_ascii=False, separators=(",", ":")),
        ).replace("{cv_section}", cv_section)

        response_text = clean_json_response(
            generate_text(SCORER_MODEL, prompt, agent_name="cv_scorer")
        )
        result = json.loads(response_text)
        result["evidence"] = _split_evidence(result)
        return result
    except LLMBudgetExhausted:
        raise
    except json.JSONDecodeError as e:
        return {"score_error": f"Không parse được JSON từ response: {e}"}
    except Exception as e:
        return {"score_error": f"Lỗi gọi API: {e}"}
