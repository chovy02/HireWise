import json
from app.services.ai_agent.gemini_client import generate_text

INTERVIEW_MODEL = "gemini-2.5-flash"

GENERATE_QUESTIONS_PROMPT = """Bạn là một Chuyên gia Phỏng vấn Kỹ thuật cấp cao.
Nhiệm vụ của bạn là soạn ra một bộ câu hỏi phỏng vấn sắc bén dựa trên Yêu cầu công việc (JD) và toàn bộ nội dung hồ sơ của ứng viên.

Trọng tâm HR yêu cầu (Nếu có): {aspect}
Yêu cầu công việc (JD): {jd_requirements}
Hồ sơ và các điểm yếu của ứng viên: {candidate_info}

YÊU CẦU BẮT BUỘC VỀ SỐ LƯỢNG VÀ NỘI DUNG:
{count_requirement}
2. KHÔNG hỏi lý thuyết suông. Bắt buộc trích xuất trực tiếp tên các dự án ứng viên đã làm trong CV để đặt câu hỏi tình huống thực tế.
3. Tạo ít nhất 1-2 câu hỏi xoáy thẳng vào điểm yếu hoặc những công nghệ ứng viên ghi chung chung để xác thực.
4. Trả về DUY NHẤT một mảng JSON. Không bọc markdown.

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
Phân tích câu trả lời của ứng viên so với đáp án kỳ vọng, chỉ ra lỗ hổng tư duy và đánh giá điểm số.

Câu hỏi đã hỏi: {question}
Đáp án kỳ vọng của hệ thống: {expected_answer}
Câu trả lời thực tế của ứng viên (do HR tóm tắt): {answer_text}

QUY TẮC TẠO CÂU HỎI PHỤ (FOLLOW-UP QUESTION):
{follow_up_guidance}

Schema JSON bắt buộc (Không bọc markdown):
{
  "evaluation": "Nhận xét ngắn gọn độ chính xác. Chỉ ra điểm ứng viên đang hiểu sai hoặc vòng vo.",
  "score": 8.0, // Điểm số thực từ 1 đến 10
  "follow_up_question": "Câu hỏi phụ sắc bén để truy vấn tiếp vào lỗ hổng (hoặc để chuỗi rỗng '' nếu không cần thiết)."
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

# Mặc định: để AI tự cân số câu theo độ dày của CV.
_COUNT_FLEXIBLE = """1. SỐ LƯỢNG LINH HOẠT (Từ 5 đến 10 câu):
   - Nếu CV ứng viên dày dặn kinh nghiệm, tham gia nhiều dự án phức tạp hoặc JD có nhiều tiêu chí khắt khe -> Hãy tạo từ 8 đến 10 câu hỏi để kiểm tra toàn diện.
   - Nếu CV đơn giản, ít thực chiến (thực tập sinh, Fresher) hoặc ít dự án -> Chỉ tạo từ 5 đến 6 câu hỏi trọng tâm nhất."""


def generate_interview_questions_ai(
    jd_reqs: dict, candidate_info: dict, aspect: str = "", num_questions: int = 0
) -> list:
    """`num_questions` > 0 -> chốt cứng số câu hỏi.

    Có tham số này vì HR hay yêu cầu rất cụ thể ("tạo cho mỗi người 3 câu hỏi"), mà
    prompt mặc định lại ép khoảng 5-10 câu — nên yêu cầu đó trước đây bị bỏ qua im
    lặng và HR nhận về số câu khác hẳn thứ mình vừa nói.
    """
    if num_questions and num_questions > 0:
        count_requirement = (
            f"1. SỐ LƯỢNG CỐ ĐỊNH: Tạo CHÍNH XÁC {num_questions} câu hỏi, không nhiều hơn, "
            f"không ít hơn. Hãy chọn đúng {num_questions} câu ĐẮT GIÁ NHẤT."
        )
    else:
        count_requirement = _COUNT_FLEXIBLE

    prompt = GENERATE_QUESTIONS_PROMPT.replace("{aspect}", aspect or "Phỏng vấn toàn diện")\
                                      .replace("{count_requirement}", count_requirement)\
                                      .replace("{jd_requirements}", json.dumps(jd_reqs, ensure_ascii=False))\
                                      .replace("{candidate_info}", json.dumps(candidate_info, ensure_ascii=False))
    try:
        parsed_data = json.loads(_clean_json(generate_text(INTERVIEW_MODEL, prompt, agent_name="interview_questions")))
        return parsed_data.get("questions", [])
    except Exception as e:
        return []

# Câu hỏi HR tự soạn thường không kèm đáp án kỳ vọng. Nhét chuỗi rỗng vào prompt thì AI
# coi như "không có gì để đối chiếu" và chấm rất tùy hứng — nên nói rõ để nó tự dựng chuẩn.
_NO_EXPECTED_ANSWER = (
    "(Không có sẵn đáp án kỳ vọng — đây là câu hỏi do chính người phỏng vấn soạn. "
    "Hãy tự xác định đâu là một câu trả lời tốt cho câu hỏi này ở mức chuyên môn tương ứng, "
    "rồi chấm câu trả lời của ứng viên theo chuẩn đó.)"
)


# Dấu hiệu "lượt chấm này KHÔNG có kết quả thật".
#
# Hàm dưới đây nuốt mọi lỗi và trả về một dict trông y như kết quả bình thường, chỉ
# khác ở chỗ evaluation là câu này và score là 0. Người gọi PHẢI kiểm tra dấu hiệu này
# trước khi lưu: 0 điểm vì AI hết quota mà ghi vào DB thì về sau không ai phân biệt
# được với 0 điểm vì ứng viên trả lời sai — và ứng viên có thể bị loại vì một con số
# chưa từng được chấm.
EVAL_FAILED = "Lỗi phân tích AI"


def eval_failed(result: dict) -> bool:
    """Kết quả chấm này có phải là bản giữ chỗ do AI hỏng không?"""
    return not result or result.get("evaluation") == EVAL_FAILED


def evaluate_interview_answer_ai(question: str, expected: str, answer: str, allow_follow_up: bool = True) -> dict:
    if not allow_follow_up:
        guidance = "- LƯU Ý HỆ THỐNG: Đã đạt giới hạn tối đa số câu hỏi phụ cho chủ đề này. BẮT BUỘC để follow_up_question là chuỗi rỗng \"\"."
    else:
        guidance = (
            "- CHỈ TẠO câu hỏi phụ khi câu trả lời của ứng viên chung chung, né tránh, thiếu ý nghiêm trọng hoặc lộ lỗ hổng kiến thức cần đào sâu.\n"
            "- NẾU ứng viên trả lời đã rõ ràng, đúng trọng tâm, chấp nhận được hoặc đủ ý -> KHÔNG ĐƯỢC tạo câu hỏi phụ (BẮT BUỘC để follow_up_question là chuỗi rỗng \"\")."
        )

    prompt = EVALUATE_ANSWER_PROMPT.replace("{question}", question)\
                                   .replace("{expected_answer}", (expected or "").strip() or _NO_EXPECTED_ANSWER)\
                                   .replace("{answer_text}", answer)\
                                   .replace("{follow_up_guidance}", guidance)
    try:
        return json.loads(_clean_json(generate_text(INTERVIEW_MODEL, prompt, agent_name="interview_evaluate")))
    except Exception as e:
        return {"evaluation": EVAL_FAILED, "score": 0, "follow_up_question": "", "error": str(e)}
    
def summarize_interview_ai(transcript: str) -> str:
    prompt = SUMMARIZE_INTERVIEW_PROMPT.replace("{interview_transcript}", transcript)
    try:
        parsed_data = json.loads(_clean_json(generate_text(INTERVIEW_MODEL, prompt, agent_name="interview_summary")))
        return parsed_data.get("summary", "Buổi phỏng vấn đã hoàn tất.")
    except Exception:
        return "Lỗi khi tạo tổng kết tự động."