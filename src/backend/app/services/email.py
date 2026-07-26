import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
    MAIL_FROM=os.getenv("MAIL_FROM", ""),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 465)),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_STARTTLS=False,
    MAIL_SSL_TLS=True,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

async def send_verification_email(email_to: EmailStr, token: str):
    """Hàm soạn và gửi email chứa mã xác minh"""
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #2c3e50;">Xác minh tài khoản hệ thống</h2>
        <p>Cảm ơn bạn đã đăng ký tài khoản. Vui lòng sao chép toàn bộ mã xác minh dưới đây để kích hoạt tài khoản của bạn:</p>
        <div style="background-color: #f1f4f9; padding: 15px; word-break: break-all; border-radius: 5px; font-family: monospace;">
            <strong>{token}</strong>
        </div>
        <p style="color: #e74c3c; margin-top: 20px;">* Lưu ý: Mã này sẽ hết hạn trong vòng 15 phút.</p>
    </div>
    """

    message = MessageSchema(
        subject="[Quan trọng] Mã xác minh tài khoản của bạn",
        recipients=[email_to],
        body=html_content,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    await fm.send_message(message)


def _support_address() -> str:
    """Địa chỉ để người dùng khiếu nại — chính là hòm thư hệ thống đang gửi đi,
    nhờ vậy họ chỉ cần bấm Reply."""
    return os.getenv("MAIL_FROM", "") or "bộ phận quản trị"


async def send_account_locked_email(email_to: EmailStr, name: str | None = None):
    """Báo cho người dùng biết tài khoản vừa bị admin khóa, kèm đường khiếu nại.

    Khóa tài khoản mà không báo thì người dùng chỉ thấy đăng nhập thất bại và không
    hiểu vì sao — email này cho họ biết chuyện gì xảy ra và cách phản hồi lại.
    """
    greeting = name or email_to

    html_content = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #c0392b;">Tài khoản của bạn đã bị khóa</h2>
        <p>Kính gửi {greeting},</p>
        <p>
            Tài khoản <strong>{email_to}</strong> trên hệ thống HireWise đã được quản trị viên
            tạm khóa. Kể từ lúc này bạn sẽ không thể đăng nhập vào hệ thống.
        </p>
        <div style="background-color: #fdf2f2; border-left: 4px solid #e74c3c; padding: 12px 15px; border-radius: 4px;">
            <p style="margin: 0;">
                Nếu bạn cho rằng đây là nhầm lẫn, vui lòng <strong>phản hồi lại email này</strong>
                để gửi khiếu nại. Quản trị viên sẽ xem xét và mở khóa nếu hợp lệ.
            </p>
        </div>
        <p style="color: #7f8c8d; margin-top: 20px; font-size: 13px;">
            Email liên hệ: {_support_address()}
        </p>
    </div>
    """

    message = MessageSchema(
        subject="[HireWise] Tài khoản của bạn đã bị khóa",
        recipients=[email_to],
        body=html_content,
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    await fm.send_message(message)


async def send_account_unlocked_email(email_to: EmailStr, name: str | None = None):
    """Báo cho người dùng biết tài khoản đã được mở khóa và dùng lại được."""
    greeting = name or email_to

    html_content = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #27ae60;">Tài khoản của bạn đã được mở khóa</h2>
        <p>Kính gửi {greeting},</p>
        <p>
            Tài khoản <strong>{email_to}</strong> trên hệ thống HireWise đã được quản trị viên
            mở khóa. Bạn có thể đăng nhập và sử dụng lại bình thường.
        </p>
        <p style="color: #7f8c8d; margin-top: 20px; font-size: 13px;">
            Nếu cần hỗ trợ thêm, vui lòng phản hồi email này. Email liên hệ: {_support_address()}
        </p>
    </div>
    """

    message = MessageSchema(
        subject="[HireWise] Tài khoản của bạn đã được mở khóa",
        recipients=[email_to],
        body=html_content,
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    await fm.send_message(message)


async def send_interview_email(email_to: EmailStr, name: str, when: str, location: str):
    """Soạn và gửi email MỜI PHỎNG VẤN cho ứng viên (dùng bởi AI Agent tool)."""

    html_content = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #2c3e50;">Thư mời phỏng vấn</h2>
        <p>Kính gửi {name},</p>
        <p>Chúng tôi trân trọng mời bạn tham gia buổi phỏng vấn:</p>
        <ul>
            <li><strong>Thời gian:</strong> {when}</li>
            <li><strong>Hình thức / Địa điểm:</strong> {location}</li>
        </ul>
        <p>Vui lòng phản hồi email này để xác nhận sự tham gia của bạn. Trân trọng.</p>
    </div>
    """

    message = MessageSchema(
        subject="[HireWise] Thư mời phỏng vấn",
        recipients=[email_to],
        body=html_content,
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    await fm.send_message(message)