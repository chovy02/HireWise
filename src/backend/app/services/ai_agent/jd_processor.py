import os
import json
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

JD_MODEL = "gemini-2.0-flash"

JD_PROMPT = """Bạn là chuyên gia tuyển dụng. HR sẽ nhập yêu cầu tuyển dụng bằng ngôn ngữ tự nhiên.
Nhiệm vụ của bạn là phân tích và chuẩn hóa thành JSON có cấu trúc để hệ thống dùng cho việc chấm điểm CV.
Trả về DUY NHẤT một object JSON, không kèm giải thích, không markdown.

Yêu cầu tuyển dụng (HR nhập):
---
{jd_text}
---

Schema JSON cần trả về:
{
  "title": "string chức danh vị trí tuyển dụng",
  "level": "string cấp bậc: intern/fresher/junior/middle/senior hoặc null",
  "required_skills": ["string các kỹ năng BẮT BUỘC phải có"],
  "preferred_skills": ["string các kỹ năng ưu tiên, không bắt buộc"],
  "experience_years": 0,
  "education": "string yêu cầu học vấn hoặc null",
  "languages": ["string yêu cầu ngoại ngữ nếu có"],
  "responsibilities": ["string các trách nhiệm công việc nếu HR có nêu"],
  "description": "string mô tả ngắn gọn vị trí (1-2 câu)"
}

Quy tắc:
- required_skills: kỹ năng HR nói rõ là PHẢI có.
- preferred_skills: kỹ năng ưu tiên, là lợi thế, biết thêm thì tốt.
- experience_years: số nguyên, để 0 nếu intern hoặc không yêu cầu kinh nghiệm.
- Nếu HR không nêu thông tin nào, để null (field đơn) hoặc [] (mảng).
- KHÔNG bịa thêm yêu cầu mà HR không nói.

Nếu yêu cầu quá thiếu thông tin (không có chức danh lẫn kỹ năng), trả về:
{"jd_error": "Yêu cầu tuyển dụng thiếu thông tin tối thiểu (cần ít nhất chức danh hoặc kỹ năng)."}"""


def _clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def process_jd(jd_text: str) -> dict:
    if not jd_text or not jd_text.strip():
        return {"jd_error": "JD rỗng, không có nội dung để xử lý."}
    try:
        prompt = JD_PROMPT.replace("{jd_text}", jd_text)
        model = genai.GenerativeModel(JD_MODEL)
        response = model.generate_content(prompt)
        response_text = _clean_json_response(response.text)
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        return {"jd_error": f"Không parse được JSON từ response: {e}"}
    except Exception as e:
        return {"jd_error": f"Lỗi gọi API: {e}"}