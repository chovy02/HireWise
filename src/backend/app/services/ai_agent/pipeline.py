from app.services.cv_processing.extractor import extract_text_from_pdf
from app.services.data_ingestion.ingestion import ingest_zip
from app.services.ai_agent.parser import parse_cv
from app.services.ai_agent.scorer import score_cv
from app.services.ai_agent.evidence import generate_evidence


def _empty_result() -> dict:
    """Khung kết quả mặc định cho 1 CV."""
    return {
        "status": "processing",
        "error": None,
        "raw_text": None,
        "parsed_cv": None,
        "score": None,
        "explanation": None,
        "strengths": None,
        "weaknesses": None,
        "score_breakdown": None,
        "evidence": None,
    }


def process_cv_from_text(raw_text: str, jd_requirements: dict) -> dict:
    """
    Pipeline xử lý 1 CV bắt đầu từ TEXT đã trích sẵn (parse -> score -> evidence).
    Dùng khi đã có raw_text (vd: từ ingest_zip), tránh đọc PDF lại lần nữa.
    """
    result = _empty_result()
    result["raw_text"] = raw_text

    if not raw_text or not raw_text.strip():
        result["status"] = "failed"
        result["error"] = "Không có text để xử lý (có thể là file scan/ảnh)."
        return result

    # Bước 1: Parse thông tin ứng viên
    parsed_cv = parse_cv(raw_text)
    result["parsed_cv"] = parsed_cv
    if parsed_cv.get("parse_error"):
        result["status"] = "failed"
        result["error"] = parsed_cv["parse_error"]
        return result

    # Bước 2: Chấm điểm
    score_result = score_cv(parsed_cv, jd_requirements)
    if score_result.get("score_error"):
        result["status"] = "failed"
        result["error"] = score_result["score_error"]
        return result

    result["score"] = score_result.get("score")
    result["explanation"] = score_result.get("explanation")
    result["strengths"] = score_result.get("strengths")
    result["weaknesses"] = score_result.get("weaknesses")
    result["score_breakdown"] = score_result.get("score_breakdown")

    # Bước 3: Sinh bằng chứng (lỗi evidence không làm mất điểm số)
    result["evidence"] = generate_evidence(raw_text, score_result)

    result["status"] = "completed"
    return result


def process_cv_pipeline(file_bytes: bytes, jd_requirements: dict) -> dict:
    """
    Pipeline xử lý 1 CV từ PDF bytes: đọc text -> process_cv_from_text.
    """
    raw_text = extract_text_from_pdf(file_bytes)
    return process_cv_from_text(raw_text, jd_requirements)


def process_zip_pipeline(zip_bytes: bytes, jd_requirements: dict) -> list[dict]:
    """
    Pipeline xử lý cả ZIP nhiều CV: giải nén -> xử lý từng CV.
    Tái dùng raw_text từ ingest_zip, không đọc PDF lần 2.

    Returns:
        list kết quả, mỗi phần tử kèm filename + file_hash.
    """
    cvs = ingest_zip(zip_bytes)
    results = []

    for cv in cvs:
        if cv["error"] or not cv["raw_text"]:
            r = _empty_result()
            r["status"] = "failed"
            r["error"] = cv["error"] or "Không đọc được text từ PDF."
            r["raw_text"] = cv["raw_text"]
        else:
            r = process_cv_from_text(cv["raw_text"], jd_requirements)

        r["filename"] = cv["filename"]
        r["file_hash"] = cv["file_hash"]
        results.append(r)

    return results