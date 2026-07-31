import html
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
import os
from typing import List, Optional

from app.services.email_attachment_storage import read_attachment

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


# ────────────────────────────────────────────────────────────
# Kết quả gửi mail
# ────────────────────────────────────────────────────────────
# Trước đây hàm gửi chỉ trả True/False, nên người gọi không thể phân biệt "email trong
# CV sai định dạng" với "Gmail chặn mật khẩu ứng dụng" hay "mạng của server chết" — cả
# ba đều thành một dấu lặng giống nhau trên UI, và HR không biết phải sửa gì để gửi
# lại. Mỗi mã lỗi dưới đây trả lời đúng một câu hỏi: LỖI Ở ĐÂU, VÀ AI SỬA ĐƯỢC.
ERR_SMTP_NOT_CONFIGURED = "smtp_not_configured"  # thiếu .env -> admin sửa
ERR_NO_EMAIL = "no_email"                        # CV không có email -> không gửi được
ERR_INVALID_EMAIL = "invalid_email"              # sai định dạng -> phải sửa dữ liệu
ERR_RECIPIENT_REFUSED = "recipient_refused"      # máy chủ nhận từ chối địa chỉ này
ERR_SENDER_REFUSED = "sender_refused"            # máy chủ từ chối địa chỉ gửi
ERR_AUTH_FAILED = "auth_failed"                  # sai user/mật khẩu ứng dụng
ERR_CONNECTION_FAILED = "connection_failed"      # không nối được / timeout
ERR_SMTP_ERROR = "smtp_error"                    # lỗi giao thức khác
ERR_BUILD_FAILED = "build_failed"                # mẫu mail/đính kèm dựng không nổi
ERR_UNKNOWN = "unknown"


@dataclass(frozen=True)
class EmailSendResult:
    """Kết quả một lượt gửi: thành công, hoặc thất bại KÈM lý do đọc được."""
    ok: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    # Giữ tương thích với lối viết cũ `if send_shortlist_email(...):` — dataclass
    # thường luôn truthy, nên không có __bool__ thì mọi lần gửi thất bại đều bị hiểu
    # thành thành công.
    def __bool__(self) -> bool:
        return self.ok


# Kiểm tra định dạng email ở mức "đủ dùng", KHÔNG theo RFC 5322 đầy đủ.
#
# Địa chỉ ở đây do AI trích từ CV nên hay dính rác: thiếu phần sau @, nuốt luôn dòng
# kế tiếp ("an@gmail.comSĐT: 09..."), hay lẫn dấu phẩy khi CV ghi hai email. Chặn
# trước khi mở kết nối SMTP thì HR biết ngay là dữ liệu sai, thay vì đợi máy chủ mail
# trả về một mã 5xx khó hiểu vài giây sau.
_EMAIL_RE = re.compile(r"^[^@\s,;:<>()\[\]\\\"]+@[^@\s,;:<>()\[\]\\\"]+\.[A-Za-z]{2,}$")


def is_valid_email(email: Optional[str]) -> bool:
    return bool(email and _EMAIL_RE.match(email.strip()))


def _describe_smtp_error(exc: Exception) -> tuple[str, str]:
    """Đổi một exception của smtplib thành (mã lỗi, câu giải thích cho HR).

    THỨ TỰ QUAN TRỌNG: các lớp con phải được kiểm tra trước lớp cha
    (SMTPAuthenticationError/SMTPConnectError đều là con của SMTPException), nếu không
    mọi lỗi đều rơi vào nhánh chung và mã lỗi mất hết ý nghĩa.
    """
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        detail = "; ".join(
            f"{addr}: {msg.decode(errors='replace') if isinstance(msg, bytes) else msg}"
            for addr, (_code, msg) in (exc.recipients or {}).items()
        )
        return (
            ERR_RECIPIENT_REFUSED,
            "Máy chủ mail từ chối địa chỉ người nhận (địa chỉ không tồn tại hoặc bị "
            f"khoá). {detail}".strip(),
        )
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return (
            ERR_AUTH_FAILED,
            "Máy chủ mail từ chối đăng nhập: sai MAIL_USERNAME/MAIL_PASSWORD, hoặc mật "
            "khẩu ứng dụng Gmail đã bị thu hồi. Cần cập nhật cấu hình rồi gửi lại.",
        )
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return (
            ERR_SENDER_REFUSED,
            f"Máy chủ mail từ chối địa chỉ gửi ({exc.sender}). Kiểm tra lại tài khoản "
            "SMTP của hệ thống.",
        )
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return (
            ERR_SMTP_ERROR,
            f"Máy chủ mail không hỗ trợ thao tác cần thiết: {exc}",
        )
    if isinstance(exc, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return (
            ERR_CONNECTION_FAILED,
            f"Không giữ được kết nối tới máy chủ mail ({SMTP_HOST}:{SMTP_PORT}): {exc}. "
            "Thường là lỗi tạm thời — thử lại được.",
        )
    if isinstance(exc, smtplib.SMTPException):
        return (ERR_SMTP_ERROR, f"Lỗi giao thức SMTP: {exc}")
    # socket.timeout, socket.gaierror, ConnectionRefusedError… đều là OSError. Đây là
    # nhóm lỗi mạng/DNS: gửi lại sau thường thành công.
    if isinstance(exc, OSError):
        return (
            ERR_CONNECTION_FAILED,
            f"Không kết nối được tới máy chủ mail ({SMTP_HOST}:{SMTP_PORT}): {exc}. "
            "Thường là lỗi tạm thời — thử lại được.",
        )
    return (ERR_UNKNOWN, f"Lỗi không xác định khi gửi mail: {exc}")


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

# Thay biến bằng regex thay vì str.format_map().
#
# format_map NỔ với ValueError("Single '{' encountered") nếu nội dung có một dấu ngoặc
# nhọn lẻ — mà HR gõ "lương {thoả thuận}" hay dán CSS vào trình soạn thảo là đủ để
# sinh ra nó. Chỗ gọi nằm NGOÀI khối try của send_shortlist_email, nên một mẫu lỗi
# từng đủ sức làm đổ cả lô gửi. Regex chỉ chạm vào đúng {ten_bien} hợp lệ và không
# bao giờ raise; biến lạ vẫn giữ nguyên văn như SafeDict trước đây.
_TOKEN_RE = re.compile(r"\{(\w+)\}")


def _fill_tokens(template: str, data: dict) -> str:
    return _TOKEN_RE.sub(lambda m: str(data.get(m.group(1), m.group(0))), template or "")


def html_to_plaintext(raw_html: str) -> str:
    """Dựng bản chữ thường từ nội dung HTML, dùng làm phần text/plain của mail.

    Mail HTML BẮT BUỘC phải kèm bản chữ thường: thiếu nó, các bộ lọc spam chấm điểm
    xấu hẳn, và người đọc bằng thiết bị chỉ hiện text (hoặc tắt HTML) nhận được mail
    trắng. Đây không phải bộ chuyển đổi hoàn hảo — chỉ cần đọc hiểu được.
    """
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", raw_html or "")
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    # </li> KHÔNG nằm trong danh sách này: <li> ở trên đã xuống dòng trước mỗi mục, xử
    # lý cả thẻ đóng nữa thì giữa hai gạch đầu dòng lại có một dòng trắng.
    text = re.sub(r"(?i)</(p|div|tr|h[1-6]|ul|ol)>", "\n", text)
    # Ảnh chèn giữa bài không có nghĩa gì ở bản chữ thường; giữ alt nếu có.
    text = re.sub(r"(?is)<img[^>]*alt=\"([^\"]*)\"[^>]*>", r"[\1]", text)
    text = re.sub(r"(?is)<img[^>]*>", "", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = html.unescape(text)
    # Thẻ đóng lồng nhau (</p></div>) sinh ra một loạt dòng trắng liền nhau.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_email_content(
    status: str,
    candidate_name: str,
    jd_title: str,
    hr_name: str,
    custom_template: Optional[object] = None
) -> tuple[str, str, str]:
    """Render tiêu đề, nội dung và ĐỊNH DẠNG nội dung ("text" | "html").

    Ưu tiên template riêng của HR nếu có và đang active.
    """
    # 1. Nếu HR có template riêng và đang bật -> Dùng template riêng
    if custom_template and getattr(custom_template, "is_active", False):
        subject_tpl = custom_template.subject
        body_tpl = custom_template.body_template
        # Mẫu lưu trước khi có trình soạn thảo không có cột này -> coi là chữ thường.
        body_format = getattr(custom_template, "body_format", None) or "text"
    else:
        default_tpl = DEFAULT_EMAIL_TEMPLATES.get(status, DEFAULT_EMAIL_TEMPLATES["rejected"])
        subject_tpl = default_tpl["subject"]
        body_tpl = default_tpl["body_template"]
        body_format = "text"

    # Nạp dữ liệu thực tế vào các biến placeholder
    data = {
        "candidate_name": candidate_name or "Ứng viên",
        "jd_title": jd_title,
        "hr_name": hr_name,
    }

    # Tiêu đề mail LUÔN là chữ thường (giao thức không cho HTML ở Subject).
    return _fill_tokens(subject_tpl, data), _fill_tokens(body_tpl, data), body_format

def _split_mime_type(content_type: str, fallback: tuple[str, str]) -> tuple[str, str]:
    """Tách "image/png" -> ("image", "png"); trả fallback nếu chuỗi không dùng được.

    add_attachment() ném lỗi nếu maintype/subtype rỗng, và content_type là dữ liệu
    trình duyệt gửi lên nên không được tin tuyệt đối.
    """
    main, _, sub = (content_type or "").partition("/")
    main = main.strip().lower()
    sub = sub.strip().lower()
    if not main or not sub:
        return fallback
    return main, sub


def _build_message(
    subject: str,
    body: str,
    body_format: str,
    to_email: str,
    hr_email: str,
    hr_name: str,
    attachments: Optional[List[object]] = None,
) -> EmailMessage:
    """Dựng mail hoàn chỉnh: chữ thường, hoặc HTML kèm ảnh chèn giữa bài + file.

    Tách riêng khỏi send_shortlist_email để kiểm tra được cấu trúc MIME mà không cần
    kết nối SMTP thật.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"HireWise ATS <{SMTP_USER}>"
    msg["To"] = to_email
    msg["Reply-To"] = f"{hr_name} <{hr_email}>"

    attachments = attachments or []
    inline = [a for a in attachments if getattr(a, "is_inline", False) and getattr(a, "content_id", None)]
    regular = [a for a in attachments if not getattr(a, "is_inline", False)]

    if body_format == "html":
        # THỨ TỰ QUAN TRỌNG: set_content trước (thành text/plain), rồi add_alternative
        # để mail thành multipart/alternative với bản chữ thường ĐỨNG TRƯỚC bản HTML.
        # Ứng dụng mail hiển thị phần cuối cùng nó hiểu được, nên HTML phải nằm sau.
        msg.set_content(html_to_plaintext(body))
        msg.add_alternative(body, subtype="html")

        if inline:
            # Ảnh phải được gắn vào chính PHẦN HTML (biến nó thành multipart/related),
            # không phải vào mail gốc — gắn sai chỗ thì Gmail coi chúng là file đính
            # kèm rời và chỗ ảnh trong bài chỉ còn ô trống.
            html_part = msg.get_payload()[-1]
            for att in inline:
                data = read_attachment(att.file_path)
                if data is None:
                    # File biến mất khỏi đĩa: vẫn gửi mail, chỉ thiếu ảnh. Chặn cả mail
                    # vì một ảnh lỗi là thiệt cho ứng viên đang đợi kết quả.
                    print(f"[WARN] Thiếu file ảnh inline {att.filename} — gửi mail mà không có ảnh này.")
                    continue
                maintype, subtype = _split_mime_type(att.content_type, ("image", "png"))
                html_part.add_related(
                    data,
                    maintype=maintype,
                    subtype=subtype,
                    cid=f"<{att.content_id}>",
                    filename=att.filename,
                    # disposition="inline" là BẮT BUỘC. Chỉ truyền filename thôi thì
                    # Python đặt Content-Disposition: attachment, và ứng viên vừa thấy
                    # ảnh trong bài vừa thấy "logo.png" nằm ở danh sách file tải về —
                    # ảnh chữ ký hiện thành file đính kèm trông như gửi nhầm.
                    disposition="inline",
                )
    else:
        msg.set_content(body)

    for att in regular:
        data = read_attachment(att.file_path)
        if data is None:
            print(f"[WARN] Thiếu file đính kèm {att.filename} — gửi mail mà không có file này.")
            continue
        maintype, subtype = _split_mime_type(att.content_type, ("application", "octet-stream"))
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=att.filename)

    return msg


def send_shortlist_email(
    to_email: str,
    hr_email: str,
    hr_name: str,
    candidate_name: str,
    jd_title: str,
    status: str,
    custom_template: Optional[object] = None, # Thêm tham số nhận template
    attachments: Optional[List[object]] = None, # File/ảnh HR gắn vào mẫu
) -> EmailSendResult:
    """Gửi email qua SMTP hệ thống, set Reply-To về mail HR và dùng custom template.

    Trả về EmailSendResult: thành công, hoặc thất bại kèm mã lỗi + câu giải thích để
    người gọi lưu lại và hiển thị cho HR (xem shortlist_items.notify_error).
    """
    # Kiểm tra cấu hình TẠI ĐÂY chứ không phải lúc import: chưa cấu hình thì chỉ
    # riêng việc gửi mail hỏng, phần còn lại của hệ thống vẫn chạy bình thường.
    if not SMTP_CONFIGURED:
        message = (
            "Hệ thống chưa cấu hình SMTP (cần SMTP_USER/SMTP_PASSWORD hoặc "
            "MAIL_USERNAME/MAIL_PASSWORD trong .env) — không gửi được mail nào."
        )
        print(f"[ERROR] {message} Người nhận bị bỏ qua: {to_email}.")
        return EmailSendResult(False, ERR_SMTP_NOT_CONFIGURED, message)

    # Chặn địa chỉ rác NGAY: không mở kết nối SMTP cho một địa chỉ chắc chắn sai.
    if not (to_email or "").strip():
        return EmailSendResult(
            False, ERR_NO_EMAIL,
            "CV không trích được địa chỉ email nên không thể gửi thông báo.",
        )
    if not is_valid_email(to_email):
        return EmailSendResult(
            False, ERR_INVALID_EMAIL,
            f"Địa chỉ email “{to_email.strip()}” không đúng định dạng nên không gửi được. "
            "Hãy sửa email của ứng viên rồi thử lại.",
        )

    subject, body, body_format = get_email_content(
        status, candidate_name, jd_title, hr_name, custom_template
    )

    # Mẫu mặc định của hệ thống không có file gắn kèm; chỉ mẫu HR tự lưu mới có.
    if custom_template is None or not getattr(custom_template, "is_active", False):
        attachments = None

    # Dựng mail cũng có thể nổ (content_type rác, tên file lạ trong mẫu của HR). Bọc
    # riêng để lỗi mẫu mail không bị ghi thành "lỗi SMTP" — hai bên sửa khác nhau.
    try:
        msg = _build_message(
            subject=subject,
            body=body,
            body_format=body_format,
            to_email=to_email,
            hr_email=hr_email,
            hr_name=hr_name,
            attachments=attachments,
        )
    except Exception as e:
        message = f"Không dựng được nội dung mail (mẫu email hoặc file đính kèm lỗi): {e}"
        print(f"[ERROR] {message}")
        return EmailSendResult(False, ERR_BUILD_FAILED, message)

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
        return EmailSendResult(True)
    except Exception as e:
        code, message = _describe_smtp_error(e)
        print(f"[ERROR] Lỗi gửi mail tới {to_email} [{code}]: {e}")
        return EmailSendResult(False, code, message)