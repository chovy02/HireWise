import os
import json
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

PARSER_MODEL = "gemini-2.0-flash"

PARSE_PROMPT = """Bạn là công cụ trích xuất thông tin CV. Đọc nội dung CV dưới đây và trả về DUY NHẤT một object JSON, không kèm giải thích, không markdown.

Schema JSON cần trả về:
{
  "full_name": "string hoặc null",
  "email": "string hoặc null",
  "phone": "string hoặc null",
  "date_of_birth": "string hoặc null",
  "gender": "string hoặc null",
  "address": "string hoặc null",
  "linkedin_url": "string hoặc null",
  "github_url": "string hoặc null",
  "portfolio_url": "string hoặc null",
  "current_position": "string chức danh/vị trí HIỆN TẠI của ứng viên (vị trí đang làm hoặc gần nhất), KHÔNG phải vị trí ứng tuyển, hoặc null",
  "years_of_experience": 0,
  "summary": "string tóm tắt ngắn gọn về ứng viên hoặc null",
  "skills": {
    "technical": ["string kỹ năng kỹ thuật: ngôn ngữ lập trình, framework, database, cloud..."],
    "soft": ["string kỹ năng mềm: giao tiếp, teamwork, lãnh đạo..."],
    "languages": ["string ngoại ngữ, vd: English (IELTS 7.0)"],
    "tools": ["string công cụ: Git, Jira, Docker, Figma..."]
  },
  "education": [
    {
      "school": "string",
      "degree": "string bằng cấp",
      "major": "string chuyên ngành hoặc null",
      "gpa": "string điểm GPA hoặc null",
      "start_year": "string hoặc null",
      "end_year": "string hoặc null"
    }
  ],
  "experience": [
    {
      "company": "string",
      "position": "string",
      "start_date": "string hoặc null",
      "end_date": "string hoặc null",
      "duration": "string tổng thời gian hoặc null",
      "responsibilities": ["string các công việc/trách nhiệm đã làm"],
      "achievements": ["string thành tựu cụ thể, có số liệu nếu có"],
      "tech_used": ["string công nghệ dùng trong công việc này"]
    }
  ],
  "projects": [
    {
      "name": "string",
      "description": "string mô tả dự án hoặc null",
      "role": "string vai trò hoặc null",
      "tech": ["string công nghệ sử dụng"],
      "github_url": "string link GitHub hoặc null",
      "demo_url": "string link demo hoặc null"
    }
  ],
  "certifications": [
    {
      "name": "string tên chứng chỉ",
      "issuer": "string nơi cấp hoặc null",
      "year": "string năm hoặc null"
    }
  ],
  "awards": ["string các giải thưởng/thành tích nổi bật"]
}

Quy tắc:
- Nếu không tìm thấy thông tin, để null (field đơn) hoặc [] (mảng).
- years_of_experience: ước lượng tổng số năm kinh nghiệm, để số nguyên, không rõ thì để 0.
- skills.technical: kỹ năng kỹ thuật cụ thể (ngôn ngữ, framework, database, cloud...).
- skills.soft: kỹ năng mềm (giao tiếp, teamwork, lãnh đạo...).
- responsibilities: việc làm thường xuyên. achievements: kết quả cụ thể đo lường được.
- certifications: trích đầy đủ tên chứng chỉ, nơi cấp, năm nếu có.
- awards: giải thưởng, danh hiệu, thành tích nổi bật.
- KHÔNG bịa thông tin không có trong CV. Thà để null hơn đoán sai.

Nội dung CV:
---
{cv_text}
---"""


def _clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def parse_cv(raw_text: str) -> dict:
    if not raw_text or not raw_text.strip():
        return {"parse_error": "CV rỗng, không có text để parse."}
    try:
        prompt = PARSE_PROMPT.replace("{cv_text}", raw_text)
        model = genai.GenerativeModel(PARSER_MODEL)
        response = model.generate_content(prompt)
        response_text = _clean_json_response(response.text)
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        return {"parse_error": f"Không parse được JSON từ response: {e}"}
    except Exception as e:
        return {"parse_error": f"Lỗi gọi API: {e}"}