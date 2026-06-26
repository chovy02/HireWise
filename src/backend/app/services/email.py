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