import smtplib
from email.message import EmailMessage
import os
from typing import List, Optional

# Các biến môi trường SMTP hệ thống HireWise
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

if not SMTP_USER or not SMTP_PASSWORD:
    raise ValueError("Lỗi cấu hình: Chưa khai báo SMTP_USER hoặc SMTP_PASSWORD trong file .env")

DEFAULT_EMAIL_TEMPLATES = {
    "accepted": {
        "subject": "[HireWise] Chúc mừng! Thư mời phỏng vấn vị trí {jd_title}",
        "body_template": (
            "Chào {candidate_name},\n\n"
            "Chúng tôi rất vui mừng thông báo hồ sơ của bạn cho vị trí {jd_title} đã qua vòng đánh giá ban đầu.\n"
            "Bộ phận Nhân sự ({hr_name}) sẽ sớm liên hệ với bạn để sắp xếp lịch phỏng vấn tiếp theo.\n\n"
            "Trân trọng,\n{hr_name} - Bộ phận Tuyển dụng."
        ),
        "is_active": True,
    },
    "rejected": {
        "subject": "[HireWise] Thông báo kết quả ứng tuyển vị trí {jd_title}",
        "body_template": (
            "Chào {candidate_name},\n\n"
            "Cảm ơn bạn đã ứng tuyển vào vị trí {jd_title}.\n"
            "Sau khi xem xét kỹ lưỡng, chúng tôi rất tiếc phải thông báo rằng hồ sơ của bạn chưa phù hợp với yêu cầu hiện tại.\n"
            "Chúng tôi đã lưu hồ sơ của bạn và sẽ liên hệ lại khi có cơ hội phù hợp hơn trong tương lai.\n\n"
            "Trân trọng,\n{hr_name} - Bộ phận Tuyển dụng."
        ),
        "is_active": True,
    }
}

class SafeDict(dict):
    """Giúp .format_map() không bị crash nếu HR gõ sai tên biến (VD: {wrong_var})."""
    def __missing__(self, key):
        return f"{{{key}}}"

def get_email_content(
    status: str, 
    candidate_name: str, 
    jd_title: str, 
    hr_name: str, 
    custom_template: Optional[object] = None
) -> tuple[str, str]:
    """Render tiêu đề và nội dung: Ưu tiên template riêng của HR nếu có và đang active."""
    
    # 1. Nếu HR có template riêng và đang bật -> Dùng template riêng
    if custom_template and getattr(custom_template, "is_active", False):
        subject_tpl = custom_template.subject
        body_tpl = custom_template.body_template
    else:
        default_tpl = DEFAULT_EMAIL_TEMPLATES.get(status, DEFAULT_EMAIL_TEMPLATES["rejected"])
        subject_tpl = default_tpl["subject"]
        body_tpl = default_tpl["body_template"]

    # Nạp dữ liệu thực tế vào các biến placeholder
    data = SafeDict({
        "candidate_name": candidate_name or "Ứng viên",
        "jd_title": jd_title,
        "hr_name": hr_name
    })

    return subject_tpl.format_map(data), body_tpl.format_map(data)

def send_shortlist_email(
    to_email: str, 
    hr_email: str, 
    hr_name: str, 
    candidate_name: str, 
    jd_title: str, 
    status: str,
    custom_template: Optional[object] = None # Thêm tham số nhận template
):
    """Gửi email qua SMTP hệ thống, set Reply-To về mail HR và dùng custom template."""
    subject, body = get_email_content(status, candidate_name, jd_title, hr_name, custom_template)
    
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"HireWise ATS <{SMTP_USER}>"
    msg["To"] = to_email
    msg["Reply-To"] = f"{hr_name} <{hr_email}>" 
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[ERROR] Lỗi gửi mail tới {to_email}: {str(e)}")
        return False