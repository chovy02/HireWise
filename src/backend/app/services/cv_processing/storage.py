import os

# Thư mục lưu file CV gốc (PDF). Mặc định là volume /data/cv_storage trong Docker
# để file không mất khi container rebuild; override bằng env khi cần.
CV_STORAGE_DIR = os.getenv("CV_STORAGE_DIR", "/data/cv_storage")


def save_cv_pdf(candidate_id, content: bytes) -> str:
    """Ghi bytes PDF gốc của 1 CV ra đĩa, đặt tên theo candidate_id. Trả về đường dẫn."""
    os.makedirs(CV_STORAGE_DIR, exist_ok=True)
    path = os.path.join(CV_STORAGE_DIR, f"{candidate_id}.pdf")
    with open(path, "wb") as f:
        f.write(content)
    return path
