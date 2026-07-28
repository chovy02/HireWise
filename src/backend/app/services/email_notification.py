import smtplib
from email.message import EmailMessage
import os
from typing import List, Optional

# Cấu hình SMTP.
#
# Ưu tiên SMTP_*, nhưng LÙI VỀ MAIL_* nếu không có: cả dự án (app/services/email.py,
# file .env) vốn đã dùng bộ tên MAIL_*. Bắt khai báo thêm một bộ tên thứ hai cho
# CÙNG một tài khoản Gmail chỉ tạo ra hai chỗ phải sửa mỗi lần đổi mật khẩu ứng dụng.
SMTP_HOST = os.getenv("SMTP_HOST") or os.getenv("MAIL_SERVER") or "smtp.gmail.com"
SMTP_PORT = int(os.getenv("SMTP_PORT") or os.getenv("MAIL_PORT") or 587)
SMTP_USER = os.getenv("SMTP_USER") or os.getenv("MAIL_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") or os.getenv("MAIL_PASSWORD")

# CỐ Ý KHÔNG raise ở tầng module.
#
# Trước đây thiếu cấu hình mail là ném ValueError ngay lúc import, mà module này nằm
# trong chuỗi import của app -> uvicorn chết ở bước khởi động, container restart vô
# hạn, và người dùng chỉ thấy "Backend not reachable" ở màn đăng nhập. Một tính năng
# phụ (gửi mail báo kết quả) chưa cấu hình KHÔNG được phép làm sập đăng nhập, upload
# CV và bảng xếp hạng. Thiếu cấu hình thì báo lỗi đúng lúc gửi, ở dưới.
SMTP_CONFIGURED = bool(SMTP_USER and SMTP_PASSWORD)

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
    # Kiểm tra cấu hình TẠI ĐÂY chứ không phải lúc import: chưa cấu hình thì chỉ
    # riêng việc gửi mail hỏng, phần còn lại của hệ thống vẫn chạy bình thường.
    if not SMTP_CONFIGURED:
        print(
            "[ERROR] Chưa cấu hình SMTP (cần SMTP_USER/SMTP_PASSWORD hoặc "
            f"MAIL_USERNAME/MAIL_PASSWORD trong .env) — không gửi được mail tới {to_email}."
        )
        return False

    subject, body = get_email_content(status, candidate_name, jd_title, hr_name, custom_template)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"HireWise ATS <{SMTP_USER}>"
    msg["To"] = to_email
    msg["Reply-To"] = f"{hr_name} <{hr_email}>"
    msg.set_content(body)

    try:
        # Cổng 465 dùng SSL ngay từ đầu kết nối; 587 mới là kết nối thường rồi nâng
        # cấp bằng STARTTLS. Bản cũ mặc định mọi cổng đều STARTTLS, nên với
        # MAIL_PORT=465 trong .env thì kết nối treo/lỗi giao thức.
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        return True
    except Exception as e:
        print(f"[ERROR] Lỗi gửi mail tới {to_email}: {str(e)}")
        return False