import json
from app.services.ai_agent.gemini_client import generate_text

COMPARE_MODEL = "gemini-2.5-flash"

COMPARE_PROMPT = """Bạn là một Chuyên gia Đánh giá Nhân sự cấp cao.
Nhiệm vụ của bạn là đọc TOÀN BỘ văn bản CV gốc của các ứng viên, đối chiếu với Yêu cầu công việc (JD), và đưa ra bài phân tích cực kỳ sắc bén tập trung vào tiêu chí người dùng yêu cầu.

Tiêu chí / Khía cạnh phân tích trọng tâm:
---
{aspect}
---

Yêu cầu công việc (JD gốc):
---
{jd_requirements}
---

Toàn bộ nội dung CV gốc của các ứng viên:
---
{candidates_info}
---

YÊU CẦU BIỆN LUẬN TUYỆT ĐỐI TUÂN THỦ:
1. CẤM LIỆT KÊ CHUNG CHUNG: Không được phép trích xuất lại thông tin theo kiểu gạch đầu dòng (Ví dụ cấm viết: "Có kỹ năng Python, Docker, AWS"). Thay vào đó phải phân tích sâu: "Ứng viên A thể hiện năng lực Python mạnh mẽ qua việc áp dụng vào hệ thống AI nhận diện hình ảnh, kết hợp triển khai mượt mà trên AWS...".
2. BÁM SÁT KHÍA CẠNH ĐƯỢC HỎI: Nếu người dùng hỏi về "Python và hạ tầng", hãy phớt lờ hoàn toàn các kỹ năng thừa như Java, Power BI, hay kỹ năng giao tiếp nếu chúng không phục vụ mục đích phân tích khía cạnh này. Cấm chê ứng viên những điểm không liên quan đến câu hỏi.
3. BẮT BUỘC TRÍCH DẪN BẰNG CHỨNG: Phải lôi các tên dự án, công nghệ, hoặc thành tích cụ thể từ văn bản CV gốc ra để làm bằng chứng bảo vệ cho lập luận của bạn. 
4. SO SÁNH TRỰC DIỆN: Phải đặt ứng viên lên bàn cân (Ví dụ: "Mặc dù Khoa có 8 năm kinh nghiệm backend, nhưng Đạt lại vượt trội hơn hẳn ở mảng quản lý hạ tầng vì đã tự tay xây dựng cụm Kubernetes cho dự án X...").

Schema JSON bắt buộc trả về (Không bọc mã markdown bên ngoài):
{
  "recommendation": "Đề xuất trực tiếp 1 ứng viên xuất sắc nhất cho khía cạnh được hỏi, kèm 1 câu chốt hạ lý do.",
  "detailed_comparison": "Bài viết phân tích sâu dạng Markdown. Dùng các đoạn văn biện luận, in đậm để nhấn mạnh dẫn chứng. Không dùng lối viết liệt kê gạch đầu dòng khô khan."
}
"""

def _clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text

def compare_candidates_ai(jd_requirements: dict, candidates_info: list[dict], aspect: str = None) -> dict:
    aspect_text = aspect if aspect and aspect.strip() else "So sánh toàn diện (Kỹ năng, Kinh nghiệm, Điểm mạnh/Yếu)."
    
    prompt = COMPARE_PROMPT.replace(
        "{aspect}", aspect_text
    ).replace(
        "{jd_requirements}", json.dumps(jd_requirements, ensure_ascii=False, indent=2)
    ).replace(
        "{candidates_info}", json.dumps(candidates_info, ensure_ascii=False, indent=2)
    )

    try:
        response_text = _clean_json_response(generate_text(COMPARE_MODEL, prompt))
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        return {"error": f"Lỗi parse JSON từ mô hình AI: {e}"}
    except Exception as e:
        return {"error": f"Lỗi kết nối dịch vụ AI: {e}"}