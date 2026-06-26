import zipfile
import io
import hashlib
from app.services.cv_processing.extractor import extract_text_from_pdf


def ingest_zip(zip_bytes: bytes) -> list[dict]:
    """
    Nhận bytes của file ZIP chứa nhiều CV (PDF), giải nén và trích text từng file.

    Returns:
        list các dict, mỗi dict gồm:
        filename, content, file_hash, raw_text, char_count, error
    """
    results = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if name.endswith("/") or not name.lower().endswith(".pdf"):
                continue

            try:
                file_bytes = zf.read(name)
                raw_text = extract_text_from_pdf(file_bytes)
                results.append({
                    "filename": name,
                    "content": file_bytes,                          # giữ file gốc để lưu storage
                    "file_hash": hashlib.sha256(file_bytes).hexdigest(),  # check trùng
                    "raw_text": raw_text,
                    "char_count": len(raw_text),
                    "error": None,
                })
            except Exception as e:
                results.append({
                    "filename": name,
                    "content": None,
                    "file_hash": None,
                    "raw_text": "",
                    "char_count": 0,
                    "error": str(e),
                })

    return results