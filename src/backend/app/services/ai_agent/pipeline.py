from sqlalchemy.orm import Session

from app import models
from app.services.cv_processing.extractor import extract_text_from_pdf
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


def create_jd_from_text(db: Session, raw_text: str, created_by) -> models.JobDescription:
    """
    UC U001 - Process & Structure JD.
    Nhận JD ngôn ngữ tự nhiên từ HR, dùng Gemini chuẩn hóa, lưu vào bảng job_descriptions.

    Raises:
        ValueError: nếu JD quá thiếu thông tin để xử lý (jd_processor trả jd_error).
    """
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


def process_zip_pipeline_and_save(
    db: Session, jd: models.JobDescription, zip_bytes: bytes
) -> list[dict]:
    """
    UC U002 + U003 - Nhận ZIP nhiều CV, giải nén, trích xuất, parse, chấm điểm,
    sinh bằng chứng, và LƯU TOÀN BỘ vào database (Candidate, CandidateSkill,
    CandidateProject, Evaluation). Mỗi CV được commit riêng để 1 CV lỗi không
    làm hỏng cả batch.

    Returns:
        list dict, mỗi phần tử gồm: filename, status, candidate_id, score, error.
    """
    cvs = ingest_zip(zip_bytes)
    results: list[dict] = []

    for cv in cvs:
        item = {
            "filename": cv["filename"],
            "status": None,
            "candidate_id": None,
            "score": None,
            "error": None,
        }

        # Bước 1: CV lỗi đọc (file hỏng / scan ảnh không có text)
        if cv["error"] or not cv["raw_text"]:
            item["status"] = "failed"
            item["error"] = cv["error"] or "Không đọc được text từ PDF (có thể là file scan/ảnh)."
            results.append(item)
            continue

        # Bước 2: Kiểm tra trùng lặp CV (FR-3.3 - SHA-256 hash)
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
            results.append(item)
            continue

        # Bước 3: Tạo bản ghi Candidate (trạng thái PENDING)
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

        try:
            # Bước 4: Parse thông tin ứng viên (UC U003 - Extract Raw Text, Standardize & Parse Skills)
            parsed = parse_cv(cv["raw_text"])
            if parsed.get("parse_error"):
                candidate.status = "FAILED"
                db.commit()
                item["status"] = "failed"
                item["candidate_id"] = candidate.id
                item["error"] = parsed["parse_error"]
                results.append(item)
                continue

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

            # Lưu projects (kèm github_url để dùng cho ProjectEvaluation sau này)
            for proj in parsed.get("projects", []) or []:
                db.add(models.CandidateProject(
                    candidate_id=candidate.id,
                    name=proj.get("name") or "Untitled project",
                    description=proj.get("description"),
                    github_url=proj.get("github_url"),
                    tech_stack=proj.get("tech") or [],
                    source="from_cv",
                ))

            # Bước 5: Chấm điểm (UC U003 - Score Suitability)
            score_result = score_cv(parsed, jd.requirements)
            if score_result.get("score_error"):
                candidate.status = "FAILED"
                db.commit()
                item["status"] = "failed"
                item["candidate_id"] = candidate.id
                item["error"] = score_result["score_error"]
                results.append(item)
                continue

            # Bước 6: Sinh bằng chứng (UC U003 - Generate Evaluation Evidence)
            evidence = generate_evidence(cv["raw_text"], score_result)

            evaluation = models.Evaluation(
                cv_id=candidate.id,
                jd_id=jd.id,
                score=score_result.get("score", 0),
                score_breakdown=score_result.get("score_breakdown") or {},
                explanation=score_result.get("explanation"),
                evidence=evidence,
            )
            db.add(evaluation)

            candidate.status = "COMPLETED"
            db.commit()

            item["status"] = "completed"
            item["candidate_id"] = candidate.id
            item["score"] = evaluation.score
            results.append(item)

        except Exception as e:
            db.rollback()
            candidate.status = "FAILED"
            db.commit()
            item["status"] = "failed"
            item["candidate_id"] = candidate.id
            item["error"] = f"Lỗi xử lý không xác định: {e}"
            results.append(item)

    return results