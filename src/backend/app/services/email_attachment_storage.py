import os
import uuid

# Thư mục lưu file HR gắn vào mẫu mail. Cùng cách làm với CV (xem
# services/cv_processing/storage.py): volume Docker riêng để file không mất khi
# rebuild container.
EMAIL_ATTACHMENT_DIR = os.getenv("EMAIL_ATTACHMENT_DIR", "/data/email_attachments")

# Chặn ở tầng lưu trữ luôn, không chỉ ở router: hộp thư Gmail từ chối mail quá 25MB,
# mà một mẫu còn có thể gắn nhiều file. Giới hạn từng file cho gọn và dễ giải thích.
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024

# Ảnh chèn giữa nội dung: chỉ nhận định dạng mà mọi ứng dụng mail đều hiển thị được.
# SVG bị loại có lý do — nó là XML chạy được script, và phần lớn client mail chặn.
ALLOWED_INLINE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def save_attachment(attachment_id: uuid.UUID, original_name: str, content: bytes) -> str:
    """Ghi file ra đĩa, đặt tên theo attachment_id. Trả về đường dẫn."""
    os.makedirs(EMAIL_ATTACHMENT_DIR, exist_ok=True)
    # Đặt tên file theo id, KHÔNG theo tên gốc người dùng tải lên: tên gốc có thể chứa
    # "../" hoặc ký tự lạ và ghi đè file ngoài thư mục. Tên gốc chỉ lưu ở DB để hiện
    # lại cho HR và đặt tên khi đính kèm vào mail.
    _, ext = os.path.splitext(original_name or "")
    ext = ext[:12] if ext.isprintable() else ""
    path = os.path.join(EMAIL_ATTACHMENT_DIR, f"{attachment_id}{ext}")
    with open(path, "wb") as f:
        f.write(content)
    return path


def read_attachment(path: str) -> bytes | None:
    """Đọc bytes của file. Trả None nếu file đã biến mất khỏi đĩa (volume bị xoá,
    khôi phục DB từ bản sao lưu...) — nơi gọi phải tự quyết định bỏ qua hay báo lỗi,
    chứ không được để cả lô mail đổ vì một file thiếu."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def delete_attachment(path: str) -> None:
    """Xoá file khỏi đĩa; im lặng nếu vốn đã không còn."""
    try:
        os.remove(path)
    except OSError:
        pass
