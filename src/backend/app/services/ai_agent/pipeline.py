import re
import uuid

from sqlalchemy.orm import Session

from app import models
from app.services.cv_processing.extractor import extract_text_from_pdf
from app.services.cv_processing.storage import save_cv_pdf
from app.services.data_ingestion.ingestion import ingest_zip
from app.services.ai_agent.parser import parse_cv
from app.services.ai_agent.scorer import score_cv
from app.services.ai_agent.evidence import generate_evidence
from app.services.ai_agent.jd_processor import process_jd


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
    KHÔNG lưu DB — chỉ trả dict, dùng cho test hoặc xử lý tạm thời.
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
    """Pipeline xử lý 1 CV từ PDF bytes: đọc text -> process_cv_from_text. KHÔNG lưu DB."""
    raw_text = extract_text_from_pdf(file_bytes)
    return process_cv_from_text(raw_text, jd_requirements)


def process_zip_pipeline(zip_bytes: bytes, jd_requirements: dict) -> list[dict]:
    """Pipeline xử lý cả ZIP nhiều CV, trả list dict."""
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


def _build_jd_markdown(jd_data: dict) -> str:
    """
    Dựng bản JD đầy đủ dạng markdown để hiển thị cho HR xem/duyệt (UC U001).
    """
    lines = [f"# {jd_data.get('title') or 'Vị trí tuyển dụng'}"]

    if jd_data.get("level"):
        lines.append(f"**Cấp bậc:** {jd_data['level']}")

    if jd_data.get("description"):
        lines.append("")
        lines.append(jd_data["description"])

    if jd_data.get("required_skills"):
        lines.append("\n## Kỹ năng bắt buộc")
        lines += [f"- {s}" for s in jd_data["required_skills"]]

    if jd_data.get("preferred_skills"):
        lines.append("\n## Kỹ năng ưu tiên")
        lines += [f"- {s}" for s in jd_data["preferred_skills"]]

    if jd_data.get("experience_years") is not None:
        lines.append(f"\n**Kinh nghiệm tối thiểu:** {jd_data['experience_years']} năm")

    if jd_data.get("education"):
        lines.append(f"**Học vấn:** {jd_data['education']}")

    if jd_data.get("languages"):
        lines.append(f"**Ngoại ngữ:** {', '.join(jd_data['languages'])}")

    if jd_data.get("responsibilities"):
        lines.append("\n## Trách nhiệm công việc")
        lines += [f"- {r}" for r in jd_data["responsibilities"]]

    return "\n".join(lines)


# Nguyên âm (kể cả tiếng Việt có dấu) để phân biệt chữ thật với chuỗi gõ phím
# lung tung ("hkbvnmbmn"). Chuỗi phụ âm liền không dấu gần như chắc chắn là rác.
_VOWELS = set("aeiouy" "àáảãạăằắẳẵặâấầẩẫậ" "èéẻẽẹêềếểễệ" "ìíỉĩị"
              "òóỏõọôồốổỗộơờớởỡợ" "ùúủũụưừứửữự" "ỳýỷỹỵ")


def _looks_like_junk(raw_text: str) -> bool:
    """
    Chặn rác do người dùng spam ("hkbvnmbmn", "hgjhbhnm jhjhbnm") trước khi tốn
    một lượt gọi AI và tạo JD vô nghĩa. Heuristic bảo thủ (chỉ chặn khi gần như
    chắc chắn là rác), phần "thông minh" thật sự do agent/LLM đảm nhiệm.

    Coi là rác nếu KHÔNG có đủ token "giống chữ" — token dài >=2 và chứa nguyên âm.
    """
    text = (raw_text or "").strip()
    if len(text) < 3:
        return True
    tokens = re.findall(r"[^\W\d_]+", text, flags=re.UNICODE)
    wordlike = [t for t in tokens if len(t) >= 2 and any(c.lower() in _VOWELS for c in t)]
    if not wordlike:
        return True
    # Chỉ đúng 1 token giống chữ và tổng nội dung quá ngắn -> vẫn coi là chưa đủ.
    return len(wordlike) < 2 and len(text) < 6


def create_jd_from_text(db: Session, raw_text: str, created_by) -> models.JobDescription:
    """
    UC U001 - Process & Structure JD.
    Nhận JD ngôn ngữ tự nhiên từ HR, dùng Gemini chuẩn hóa, lưu vào bảng job_descriptions.

    Raises:
        ValueError: nếu nội dung là rác/spam hoặc JD quá thiếu thông tin để xử lý.
    """
    if _looks_like_junk(raw_text):
        raise ValueError(
            "Nội dung chưa giống một yêu cầu tuyển dụng. "
            "Hãy mô tả vị trí cần tuyển (chức danh, kỹ năng, kinh nghiệm...)."
        )

    jd_data = process_jd(raw_text)
    if jd_data.get("jd_error"):
        raise ValueError(jd_data["jd_error"])

    jd = models.JobDescription(
        title=jd_data.get("title") or "Vị trí chưa đặt tên",
        raw_text=raw_text,
        jd_markdown=_build_jd_markdown(jd_data),
        requirements=jd_data,
        status="active",
        created_by=created_by,
    )
    db.add(jd)
    db.commit()
    db.refresh(jd)
    return jd


def stage_cvs(
    db: Session, jd: models.JobDescription, zip_bytes: bytes
) -> list[dict]:
    """
    PHA 1 (đồng bộ, nhanh, KHÔNG gọi AI): giải nén ZIP, trích text, check trùng,
    và tạo bản ghi Candidate ở trạng thái PENDING cho từng CV hợp lệ. Trả về ngay
    để endpoint không phải chờ phần chấm điểm AI (do Celery worker làm ở PHA 2).

    Trả về list item {filename, status, candidate_id, score, error}, với status:
      - "pending"    : đã tạo Candidate, đang chờ worker chấm điểm.
      - "duplicated" : CV đã nộp trước đó cho JD này.
      - "failed"     : không đọc được text (file hỏng / scan ảnh).
    """
    cvs = ingest_zip(zip_bytes)
    staged: list[dict] = []

    for cv in cvs:
        item = {
            "filename": cv["filename"],
            "status": None,
            "candidate_id": None,
            "score": None,
            "error": None,
        }

        # CV lỗi đọc (file hỏng / scan ảnh không có text)
        if cv["error"] or not cv["raw_text"]:
            item["status"] = "failed"
            item["error"] = cv["error"] or "Không đọc được text từ PDF (có thể là file scan/ảnh)."
            staged.append(item)
            continue

        # Kiểm tra trùng lặp CV (FR-3.3 - SHA-256 hash)
        existing = (
            db.query(models.Candidate)
            .filter(
                models.Candidate.jd_id == jd.id,
                models.Candidate.file_hash == cv["file_hash"],
            )
            .first()
        )
        if existing:
            item["status"] = "duplicated"
            item["candidate_id"] = existing.id
            item["error"] = "CV đã được nộp trước đó cho vị trí này."
            staged.append(item)
            continue

        # Tạo bản ghi Candidate (PENDING) - phần AI để worker xử lý sau.
        candidate = models.Candidate(
            jd_id=jd.id,
            raw_text=cv["raw_text"],
            file_hash=cv["file_hash"],
            source="web_upload",
            status="PENDING",
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)

        # Lưu file PDF gốc ra đĩa (đặt tên theo candidate.id) để hiển thị lại cho HR.
        if cv.get("content"):
            candidate.file_path = save_cv_pdf(candidate.id, cv["content"])
            db.commit()

        item["status"] = "pending"
        item["candidate_id"] = candidate.id
        staged.append(item)

    return staged


def evaluate_candidate(db: Session, candidate_id) -> dict:
    """
    PHA 2 (chạy trong Celery worker): chấm điểm 1 Candidate đang PENDING.
    parse -> lưu skills/projects -> score -> evidence -> lưu Evaluation, rồi cập
    nhật status COMPLETED/FAILED. Tự commit. Nhận candidate_id (UUID hoặc str vì
    Celery serialize sang JSON).

    Mỗi CV commit riêng để 1 CV lỗi không làm hỏng các CV khác trong batch.
    """
    if isinstance(candidate_id, str):
        candidate_id = uuid.UUID(candidate_id)

    item = {"candidate_id": candidate_id, "status": None, "score": None, "error": None}

    candidate = (
        db.query(models.Candidate)
        .filter(models.Candidate.id == candidate_id)
        .first()
    )
    if candidate is None:
        item["status"] = "failed"
        item["error"] = "Không tìm thấy candidate."
        return item

    jd = (
        db.query(models.JobDescription)
        .filter(models.JobDescription.id == candidate.jd_id)
        .first()
    )

    # Dọn kết quả của lần chạy TRƯỚC để hàm này chạy lại được nhiều lần (nút "Thử
    # lại" của HR). Lần lỗi trước có thể đã commit một phần skills/projects — không
    # xóa thì mỗi lần thử lại sẽ nhân đôi chúng.
    db.query(models.CandidateSkill).filter(
        models.CandidateSkill.cv_id == candidate.id
    ).delete(synchronize_session=False)
    db.query(models.CandidateProject).filter(
        models.CandidateProject.candidate_id == candidate.id
    ).delete(synchronize_session=False)
    candidate.error_message = None
    db.commit()

    try:
        # Parse thông tin ứng viên (UC U003 - Extract Raw Text, Standardize & Parse Skills)
        parsed = parse_cv(candidate.raw_text)
        if parsed.get("parse_error"):
            candidate.status = "FAILED"
            candidate.error_message = parsed["parse_error"]
            db.commit()
            item["status"] = "failed"
            item["error"] = parsed["parse_error"]
            return item

        candidate.name = parsed.get("full_name")
        candidate.email = parsed.get("email")
        candidate.phone = parsed.get("phone")

        # Lưu skills (gộp cả 4 nhóm technical/soft/languages/tools vào candidate_skills,
        # vì model hiện tại chưa có cột phân loại category)
        skills_data = parsed.get("skills") or {}
        for category in ("technical", "soft", "languages", "tools"):
            for skill_name in skills_data.get(category, []) or []:
                db.add(models.CandidateSkill(
                    cv_id=candidate.id,
                    skill_name=skill_name,
                    normalized_name=skill_name.strip().lower(),
                ))

        # Chấm điểm (UC U003 - Score Suitability)
        score_result = score_cv(parsed, jd.requirements)
        if score_result.get("score_error"):
            candidate.status = "FAILED"
            candidate.error_message = score_result["score_error"]
            db.commit()
            item["status"] = "failed"
            item["error"] = score_result["score_error"]
            return item

        # Sinh bằng chứng (UC U003 - Generate Evaluation Evidence)
        evidence = generate_evidence(candidate.raw_text, score_result)

        evaluation = models.Evaluation(
            cv_id=candidate.id,
            jd_id=candidate.jd_id,
            score=score_result.get("score", 0),
            score_breakdown=score_result.get("score_breakdown") or {},
            explanation=score_result.get("explanation"),
            evidence=evidence,
        )
        db.add(evaluation)

        candidate.status = "COMPLETED"
        candidate.error_message = None  # xóa dấu vết lần lỗi trước nếu đây là lần thử lại
        db.commit()

        item["status"] = "completed"
        item["score"] = evaluation.score
        return item

    except Exception as e:
        db.rollback()
        message = f"Lỗi xử lý không xác định: {type(e).__name__}: {e}"
        candidate.status = "FAILED"
        candidate.error_message = message
        db.commit()
        item["status"] = "failed"
        item["error"] = message
        return item


def process_zip_pipeline_and_save(
    db: Session, jd: models.JobDescription, zip_bytes: bytes
) -> list[dict]:
    """
    Phiên bản ĐỒNG BỘ (stage + chấm điểm ngay trong 1 lời gọi). Giữ lại cho test
    và các luồng không dùng Celery. Luồng upload thực tế dùng stage_cvs + Celery
    task (xem routers/cv.py) để không chặn request.
    """
    staged = stage_cvs(db, jd, zip_bytes)
    results: list[dict] = []
    for s in staged:
        if s["status"] == "pending":
            r = evaluate_candidate(db, s["candidate_id"])
            r["filename"] = s["filename"]
            results.append(r)
        else:
            results.append(s)
    return results