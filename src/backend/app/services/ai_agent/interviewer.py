import json
from app.services.ai_agent.gemini_client import generate_text

INTERVIEW_MODEL = "gemini-2.5-flash"

GENERATE_QUESTIONS_PROMPT = """Bạn là một Chuyên gia Phỏng vấn Kỹ thuật cấp cao.
Nhiệm vụ của bạn là soạn ra một bộ gồm 5 câu hỏi phỏng vấn sắc bén dựa trên Yêu cầu công việc và toàn bộ nội dung hồ sơ của ứng viên.

Trọng tâm HR yêu cầu (Nếu có): {aspect}
Yêu cầu công việc (JD): {jd_requirements}
Hồ sơ và các điểm yếu của ứng viên: {candidate_info}

YÊU CẦU BẮT BUỘC:
1. KHÔNG hỏi lý thuyết suông. Bắt buộc trích xuất trực tiếp tên các dự án ứng viên đã làm trong CV để đặt câu hỏi tình huống thực tế.
2. Tạo ít nhất 1-2 câu hỏi xoáy thẳng vào điểm yếu hoặc những công nghệ ứng viên ghi chung chung để xác thực.
3. Trả về DUY NHẤT một mảng JSON. Không bọc markdown.

Schema JSON bắt buộc (Lưu ý: Phải trả về Object chứa mảng 'questions'):
{
  "questions": [
    {
      "question": "Nội dung câu hỏi tình huống sắc bén",
      "expected_answer": "Gợi ý các từ khóa/hướng tư duy đúng để người phỏng vấn đối chiếu",
      "category": "chuyên môn / kỹ năng mềm / xử lý tình huống"
    }
  ]
}
"""

EVALUATE_ANSWER_PROMPT = """Bạn là Chuyên gia Đánh giá Phỏng vấn.
Phân tích câu trả lời của ứng viên so với đáp án kỳ vọng, chỉ ra lỗ hổng tư duy và đề xuất một câu hỏi phụ để đào sâu hơn nếu ứng viên trả lời quá hời hợt.

Câu hỏi đã hỏi: {question}
Đáp án kỳ vọng của hệ thống: {expected_answer}
Câu trả lời thực tế của ứng viên (do HR tóm tắt): {answer_text}

Schema JSON bắt buộc (Không bọc markdown):
{
  "evaluation": "Nhận xét ngắn gọn độ chính xác. Chỉ ra điểm ứng viên đang hiểu sai hoặc vòng vo.",
  "score": 8.0, // Điểm số thực từ 1 đến 10
  "follow_up_question": "Một câu hỏi phụ sắc bén để truy vấn tiếp vào lỗ hổng. Nếu ứng viên trả lời quá hoàn hảo, để chuỗi rỗng ''."
}
"""

SUMMARIZE_INTERVIEW_PROMPT = """Bạn là Giám đốc Nhân sự.
Hãy đọc biên bản buổi phỏng vấn dưới đây (gồm các câu hỏi và tóm tắt câu trả lời của ứng viên) và đưa ra một đoạn nhận xét tổng quan ngắn gọn về năng lực thực tế của ứng viên.

Biên bản phỏng vấn:
{interview_transcript}

Trả về DUY NHẤT một Object JSON. Không bọc markdown.
{
  "summary": "Đoạn văn 3-4 câu đánh giá tổng quan ưu/nhược điểm lộ ra trong lúc phỏng vấn."
}
"""

def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"): text = text[4:]
        text = text.strip()
    return text

def generate_interview_questions_ai(jd_reqs: dict, candidate_info: dict, aspect: str = "") -> list:
    prompt = GENERATE_QUESTIONS_PROMPT.replace("{aspect}", aspect or "Phỏng vấn toàn diện")\
                                      .replace("{jd_requirements}", json.dumps(jd_reqs, ensure_ascii=False))\
                                      .replace("{candidate_info}", json.dumps(candidate_info, ensure_ascii=False))
    try:
        parsed_data = json.loads(_clean_json(generate_text(INTERVIEW_MODEL, prompt, agent_name="interview_questions")))
        return parsed_data.get("questions", [])
    except Exception as e:
        return []

def evaluate_interview_answer_ai(question: str, expected: str, answer: str) -> dict:
    prompt = EVALUATE_ANSWER_PROMPT.replace("{question}", question)\
                                   .replace("{expected_answer}", expected or "")\
                                   .replace("{answer_text}", answer)
    try:
        return json.loads(_clean_json(generate_text(INTERVIEW_MODEL, prompt, agent_name="interview_evaluate")))
    except Exception as e:
        return {"evaluation": "Lỗi phân tích AI", "score": 0, "follow_up_question": ""}
    
def summarize_interview_ai(transcript: str) -> str:
    prompt = SUMMARIZE_INTERVIEW_PROMPT.replace("{interview_transcript}", transcript)
    try:
        parsed_data = json.loads(_clean_json(generate_text(INTERVIEW_MODEL, prompt, agent_name="interview_summary")))
        return parsed_data.get("summary", "Buổi phỏng vấn đã hoàn tất.")
    except Exception:
        return "Lỗi khi tạo tổng kết tự động."