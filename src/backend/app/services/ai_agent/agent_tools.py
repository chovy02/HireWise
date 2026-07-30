"""
Bộ TOOL dùng chung cho AI Agent (kiến trúc B).

Mỗi hàm bọc lại một service đã có sẵn (pipeline / comparator / interviewer / email)
và trả về dict JSON-serializable để nhét thẳng vào hội thoại với LLM.

- TOOLS      : mô tả tool dạng JSON schema (OpenAI/Groq function-calling) cho LLM đọc.
- TOOL_FUNCS : ánh xạ tên tool -> hàm Python thật.
- USER_BOUND : các tool cần user_id của HR đang đăng nhập (agent loop tự tiêm vào,
               KHÔNG để LLM tự bịa).

Tất cả hàm nhận `db` là tham số đầu tiên (Session), phần còn lại là tham số do LLM điền.
"""

import asyncio
import uuid

from sqlalchemy.orm import Session

from app import models
from app.services.ai_agent.pipeline import create_jd_from_text
from app.services.ai_agent.comparator import compare_candidates_ai
from app.services.ai_agent.evaluation_view import evaluation_for_agent, weakness_context
from app.services.ai_agent.interviewer import generate_interview_questions_ai


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _uuid(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"ID không hợp lệ: {value!r}")


def _owner_filter(q, owner_id):
    """Giới hạn query JD về đúng người đang thao tác, và bỏ JD trong thùng rác.

    `owner_id` do agent loop / MCP tiêm vào (chính là HR đang đăng nhập), LLM không
    điền được. Thiếu bộ lọc này thì Copilot đọc và thao tác được trên project của
    MỌI tài khoản — cùng lỗ hổng như REST API trước đây.

    Lọc `deleted_at` ở ĐÂY vì đây là chỗ duy nhất mọi tool chạm tới JD đi qua. Không
    có nó thì HR xoá dự án xong, giao diện sạch bong nhưng Copilot vẫn liệt kê và
    thao tác được trên dự án đó — vô lý với người dùng. Lọc cả khi owner_id là None:
    dự án đã xoá thì không ai được thấy, không phụ thuộc chuyện của ai.
    """
    q = q.filter(models.JobDescription.deleted_at.is_(None))
    if owner_id is None:
        return q
    return q.filter(models.JobDescription.created_by == _uuid(owner_id))


def _resolve_jd(db: Session, ref, owner_id=None) -> models.JobDescription | None:
    """
    Tìm JD từ `ref` là UUID HOẶC tên vị trí. Model đôi khi truyền tên thay vì id;
    resolve theo tên giúp khỏi crash và đỡ 1 lượt gọi list_jds (tiết kiệm token).
    Nếu trùng tên, ưu tiên JD có NHIỀU ứng viên nhất (thường là cái HR đang test).
    Luôn chỉ nhìn trong phạm vi JD của `owner_id`.
    """
    base = _owner_filter(db.query(models.JobDescription), owner_id)

    try:
        jd = base.filter(models.JobDescription.id == uuid.UUID(str(ref))).first()
        if jd is not None:
            return jd
    except (ValueError, AttributeError, TypeError):
        pass

    matches = base.filter(
        models.JobDescription.title.ilike(f"%{str(ref).strip()}%")
    ).all()
    if not matches:
        return None
    return max(matches, key=lambda j: len(j.cvs))


def _resolve_candidate(db: Session, ref, owner_id=None) -> models.Candidate | None:
    """Tìm ứng viên từ UUID HOẶC tên, chỉ trong các JD thuộc `owner_id`."""
    base = _owner_filter(
        db.query(models.Candidate).join(
            models.JobDescription,
            models.Candidate.jd_id == models.JobDescription.id,
        ),
        owner_id,
    )
    try:
        c = base.filter(models.Candidate.id == uuid.UUID(str(ref))).first()
        if c is not None:
            return c
    except (ValueError, AttributeError, TypeError):
        pass
    return (
        base.filter(models.Candidate.name.ilike(f"%{str(ref).strip()}%"))
        .order_by(models.Candidate.created_at.desc())
        .first()
    )


def _candidate_brief(c: models.Candidate) -> dict:
    ev = c.evaluation
    return {
        "candidate_id": str(c.id),
        "name": c.name,
        "email": c.email,
        "status": c.status,
        "score": ev.score if ev else None,
        "skills": [s.skill_name for s in c.skills],
        # Ứng viên thuộc vị trí nào (cần khi tìm xuyên nhiều JD).
        "jd_title": c.jd.title if c.jd else None,
    }


# --------------------------------------------------------------------------- #
# TOOLS (read-only)
# --------------------------------------------------------------------------- #
def list_jds(db: Session, status: str = "active", owner_id=None) -> list[dict]:
    q = _owner_filter(db.query(models.JobDescription), owner_id)
    if status != "all":
        q = q.filter(models.JobDescription.status == status)
    rows = q.order_by(models.JobDescription.created_at.desc()).all()
    return [{"jd_id": str(j.id), "title": j.title, "status": j.status} for j in rows]


def get_jd(db: Session, jd_id: str, owner_id=None) -> dict:
    jd = _resolve_jd(db, jd_id, owner_id)
    if jd is None:
        return {"error": "Không tìm thấy JD."}
    return {
        "jd_id": str(jd.id),
        "title": jd.title,
        "requirements": jd.requirements,
        "jd_markdown": jd.jd_markdown,
        "status": jd.status,
    }


def search_candidates(
    db: Session,
    jd_id: str | None = None,
    min_score: float = 0.0,
    skill: str | None = None,
    limit: int = 20,
    owner_id=None,
) -> dict:
    """
    Tìm ứng viên đã được chấm điểm.

    `jd_id` là TUỲ CHỌN: bỏ trống -> tìm XUYÊN MỌI vị trí (dùng khi HR chỉ hỏi kiểu
    "tìm người biết Python" mà không nhắc vị trí nào). Có jd_id -> chỉ trong vị trí đó.
    """
    jd = None
    if jd_id:
        jd = _resolve_jd(db, jd_id, owner_id)
        if jd is None:
            return {"error": f"Không tìm thấy vị trí: {jd_id}"}

    # Không có jd_id -> tìm xuyên MỌI vị trí, nhưng vẫn phải chỉ trong vị trí của
    # chính người đang hỏi, nếu không Copilot sẽ trả ứng viên của tài khoản khác.
    q = _owner_filter(
        db.query(models.Candidate)
        .join(models.Evaluation, models.Evaluation.cv_id == models.Candidate.id)
        .join(
            models.JobDescription,
            models.Candidate.jd_id == models.JobDescription.id,
        )
        .filter(models.Evaluation.score >= min_score),
        owner_id,
    )
    if jd is not None:
        q = q.filter(models.Candidate.jd_id == jd.id)
    if skill:
        q = q.join(
            models.CandidateSkill, models.CandidateSkill.cv_id == models.Candidate.id
        ).filter(models.CandidateSkill.normalized_name.ilike(f"%{skill.strip().lower()}%"))

    rows = q.order_by(models.Evaluation.score.desc()).limit(min(limit, 50)).all()
    briefs = [_candidate_brief(c) for c in rows]

    result = {
        "scope": jd.title if jd else "tất cả vị trí",
        "count": len(briefs),
        "candidates": briefs,
    }

    # Tô sáng trên UI chỉ có nghĩa khi mọi kết quả thuộc CÙNG 1 vị trí (1 trang project).
    if briefs:
        jd_ids = {c.jd_id for c in rows}
        if len(jd_ids) == 1:
            target = jd.id if jd else next(iter(jd_ids))
            ids = ",".join(b["candidate_id"] for b in briefs)
            result["ui_action"] = {
                "type": "navigate",
                "path": f"/projects/{target}?highlight={ids}",
            }
    return result


def get_candidate(db: Session, candidate_id: str, owner_id=None) -> dict:
    c = _resolve_candidate(db, candidate_id, owner_id)
    if c is None:
        return {"error": "Không tìm thấy ứng viên."}
    ev = c.evaluation
    return {
        **_candidate_brief(c),
        "phone": c.phone,
        "evaluation": None if ev is None else evaluation_for_agent(ev),
        # Không có "projects": model Candidate chưa bao giờ có quan hệ đó (chỉ có
        # skills / evaluation / interview), nên `c.projects` ném AttributeError và
        # tool này hỏng ở MỌI lượt gọi. Kỹ năng đã nằm trong _candidate_brief.
        # LC1: mở popup chi tiết đánh giá ứng viên này trên app (query ?open=).
        "ui_action": {"type": "navigate", "path": f"/projects/{c.jd_id}?open={c.id}"},
    }


# --------------------------------------------------------------------------- #
# TOOLS (hành động / gọi AI)
# --------------------------------------------------------------------------- #
def create_jd(db: Session, raw_text: str, created_by: str, owner_id=None) -> dict:
    """created_by do agent loop tiêm vào (user đang đăng nhập), LLM không điền.
    `owner_id` nhận cho đồng nhất với các tool khác — ở đây chính là created_by."""
    jd = create_jd_from_text(db, raw_text, _uuid(created_by))
    return {"jd_id": str(jd.id), "title": jd.title, "status": jd.status}


def compare_candidates(
    db: Session,
    candidate_ids: list[str] | None = None,
    jd_id: str | None = None,
    top_n: int | None = None,
    aspect: str = "",
    owner_id=None,
) -> dict:
    """
    So sánh ứng viên. Hai cách dùng:
      1) HR chỉ đích danh  -> truyền candidate_ids (UUID HOẶC tên).
      2) HR nói "top N"    -> truyền jd_id + top_n, TOOL tự lấy N người điểm cao nhất
         từ DB (không bắt LLM phải nhớ/đọc ra từng UUID -> hết cảnh "bảo 3 mà so 2").
    Thiếu người thì BÁO RÕ, không âm thầm bỏ qua.
    """
    cands: list[models.Candidate] = []
    missing: list[str] = []

    if candidate_ids:
        for cid in candidate_ids:
            c = _resolve_candidate(db, cid, owner_id)
            if c is None:
                missing.append(str(cid))
            else:
                cands.append(c)
        # Khử trùng (LLM có thể truyền cùng 1 người 2 lần dưới 2 dạng tên/id).
        seen, uniq = set(), []
        for c in cands:
            if c.id not in seen:
                seen.add(c.id)
                uniq.append(c)
        cands = uniq
    elif jd_id and top_n:
        jd = _resolve_jd(db, jd_id, owner_id)
        if jd is None:
            return {"error": f"Không tìm thấy vị trí: {jd_id}"}
        cands = (
            db.query(models.Candidate)
            .join(models.Evaluation, models.Evaluation.cv_id == models.Candidate.id)
            .filter(models.Candidate.jd_id == jd.id)
            .order_by(models.Evaluation.score.desc())
            .limit(max(2, int(top_n)))
            .all()
        )
    else:
        return {"error": "Cần truyền candidate_ids, hoặc jd_id + top_n."}

    if len(cands) < 2:
        return {
            "error": "Không đủ ứng viên hợp lệ để so sánh (cần ít nhất 2).",
            "found": [c.name for c in cands],
            "not_found": missing,
        }

    jd_ref = cands[0].jd_id
    if any(c.jd_id != jd_ref for c in cands):
        return {"error": "Các ứng viên phải cùng một vị trí (JD) mới so sánh được."}

    jd = _owner_filter(
        db.query(models.JobDescription).filter(models.JobDescription.id == jd_ref),
        owner_id,
    ).first()
    candidates_info = [
        {"name": c.name or str(c.id), "full_cv_text": c.raw_text} for c in cands
    ]
    result = compare_candidates_ai(jd.requirements, candidates_info, aspect or None)

    # Cho LLM biết chính xác đã so ai, và ai không tìm thấy -> nó phải nói ra cho HR.
    result["compared"] = [c.name for c in cands]
    result["compared_count"] = len(cands)
    if missing:
        result["not_found"] = missing
        result["warning"] = (
            f"Chỉ so sánh được {len(cands)} người; không tìm thấy: {', '.join(missing)}. "
            "PHẢI báo điều này cho HR."
        )
    return result


def generate_interview_questions(
    db: Session, candidate_id: str, aspect: str = "", owner_id=None
) -> dict:
    """
    Sinh bộ câu hỏi phỏng vấn bám CV + JD và LƯU vào DB (tạo Interview +
    InterviewQuestion) đúng như luồng /interviews/.../generate, để HR thấy được
    trong màn hình phỏng vấn. Nếu ứng viên đã có buổi phỏng vấn thì tạo lại.
    """
    c = _resolve_candidate(db, candidate_id, owner_id)
    if c is None:
        return {"error": "Không tìm thấy ứng viên."}
    if c.evaluation is None:
        return {"error": f"Ứng viên {c.name or c.id} chưa được chấm điểm nên chưa thể tạo phỏng vấn."}

    jd = db.get(models.JobDescription, c.jd_id)

    # Tạo lại: xoá buổi phỏng vấn cũ (nếu có) để tránh trùng.
    old = db.query(models.Interview).filter(models.Interview.cv_id == c.id).first()
    if old is not None:
        db.delete(old)
        db.commit()

    candidate_context = {
        "full_cv": c.raw_text,
        "ai_identified_weaknesses": weakness_context(c.evaluation),
    }
    ai_questions = generate_interview_questions_ai(
        jd.requirements if jd else {}, candidate_context, aspect
    )
    if not ai_questions:
        return {"error": "AI không sinh được câu hỏi phỏng vấn."}

    interview = models.Interview(cv_id=c.id, status="pending")
    db.add(interview)
    db.commit()
    db.refresh(interview)

    saved = []
    for idx, q in enumerate(ai_questions):
        if not isinstance(q, dict):
            continue
        db.add(models.InterviewQuestion(
            interview_id=interview.id,
            question=q.get("question", "Câu hỏi chưa xác định"),
            expected_answer=q.get("expected_answer", ""),
            category=q.get("category", "Chung"),
            order_index=idx * 10,
        ))
        saved.append({"question": q.get("question"), "category": q.get("category")})
    db.commit()

    return {
        "status": "created",
        "interview_id": str(interview.id),
        "candidate": c.name,
        "count": len(saved),
        "questions": saved,
    }


# --------------------------------------------------------------------------- #
# TOOLS Shortlist
# --------------------------------------------------------------------------- #
def create_shortlist(
    db: Session, jd_id: str, name: str, created_by: str, owner_id=None
) -> dict:
    """Tạo 1 shortlist mới cho 1 vị trí."""
    jd = _resolve_jd(db, jd_id, owner_id)
    if jd is None:
        return {"error": "Không tìm thấy vị trí."}
    sl = models.Shortlist(jd_id=jd.id, name=name.strip(), created_by=_uuid(created_by))
    db.add(sl)
    db.commit()
    db.refresh(sl)
    return {"status": "created", "shortlist_id": str(sl.id), "name": sl.name, "jd": jd.title}


def list_shortlists(db: Session, jd_id: str, owner_id=None) -> dict:
    """Liệt kê các shortlist của 1 vị trí (kèm số ứng viên)."""
    jd = _resolve_jd(db, jd_id, owner_id)
    if jd is None:
        return {"error": "Không tìm thấy vị trí."}
    return {
        "jd": jd.title,
        "shortlists": [
            {"shortlist_id": str(s.id), "name": s.name, "count": len(s.items)}
            for s in jd.shortlists
        ],
    }


def add_to_shortlist(
    db: Session,
    candidate_id: str,
    created_by: str,
    shortlist_name: str = "AI Shortlist",
    owner_id=None,
) -> dict:
    """
    Đưa 1 ứng viên vào shortlist. Tự tìm shortlist tên `shortlist_name` trong JD của
    ứng viên; nếu chưa có thì tạo. Chống thêm trùng. Đây là tool 'một phát ăn ngay'
    cho yêu cầu "đưa ứng viên X vào shortlisting".
    """
    c = _resolve_candidate(db, candidate_id, owner_id)
    if c is None:
        return {"error": "Không tìm thấy ứng viên."}

    sl = (
        db.query(models.Shortlist)
        .filter(
            models.Shortlist.jd_id == c.jd_id,
            models.Shortlist.name == shortlist_name,
        )
        .first()
    )
    if sl is None:
        sl = models.Shortlist(jd_id=c.jd_id, name=shortlist_name, created_by=_uuid(created_by))
        db.add(sl)
        db.commit()
        db.refresh(sl)

    existing = (
        db.query(models.ShortlistItem)
        .filter(
            models.ShortlistItem.shortlist_id == sl.id,
            models.ShortlistItem.cv_id == c.id,
        )
        .first()
    )
    if existing:
        return {"status": "already_in", "shortlist": sl.name, "candidate": c.name}

    db.add(models.ShortlistItem(shortlist_id=sl.id, cv_id=c.id))
    db.commit()
    return {
        "status": "added",
        "shortlist": sl.name,
        "shortlist_id": str(sl.id),
        "candidate": c.name,
    }


def send_interview_invite(
    db: Session,
    candidate_id: str,
    when: str,
    location: str = "Google Meet (link gửi sau)",
    confirm: bool = False,
    owner_id=None,
) -> dict:
    """
    Gửi email mời phỏng vấn. AN TOÀN KHI TEST: mặc định confirm=False -> chỉ trả về
    BẢN XEM TRƯỚC, KHÔNG gửi thật. Chỉ khi HR xác nhận rõ ràng, agent mới đặt
    confirm=true để gửi.
    """
    c = _resolve_candidate(db, candidate_id, owner_id)
    if c is None or not c.email:
        return {"error": "Ứng viên không tồn tại hoặc chưa có email."}

    preview = {
        "to": c.email,
        "name": c.name or "Ứng viên",
        "when": when,
        "location": location,
    }
    if not confirm:
        return {
            "status": "preview",
            "note": "Chưa gửi. Hãy hỏi HR xác nhận, rồi gọi lại với confirm=true.",
            "email_preview": preview,
        }

    # Gửi thật qua hàm chuẩn trong services/email.py (fastapi_mail là async).
    from app.services.email import send_interview_email

    asyncio.run(send_interview_email(c.email, preview["name"], when, location))
    return {"status": "sent", **preview}


# --------------------------------------------------------------------------- #
# TOOLS điều hướng GIAO DIỆN (không đổi dữ liệu; trả 'ui_action' để FE nhảy trang)
# --------------------------------------------------------------------------- #
def open_jd(db: Session, jd_id: str, owner_id=None) -> dict:
    """Mở trang chi tiết 1 vị trí (project) ở phần giao diện bên phải."""
    jd = _resolve_jd(db, jd_id, owner_id)
    if jd is None:
        return {"error": "Không tìm thấy JD."}
    return {
        "opened": jd.title,
        "ui_action": {"type": "navigate", "path": f"/projects/{jd.id}"},
    }


def open_dashboard(db: Session, owner_id=None) -> dict:
    """Mở màn hình Dashboard (danh sách vị trí tuyển dụng)."""
    return {"ui_action": {"type": "navigate", "path": "/"}}


def open_shortlisting(db: Session, owner_id=None) -> dict:
    """Mở màn hình Shortlisting (danh sách rút gọn ứng viên)."""
    return {"ui_action": {"type": "navigate", "path": "/shortlisting"}}


# --------------------------------------------------------------------------- #
# Đăng ký tool cho LLM
# --------------------------------------------------------------------------- #
TOOL_FUNCS = {
    "list_jds": list_jds,
    "get_jd": get_jd,
    "search_candidates": search_candidates,
    "get_candidate": get_candidate,
    "create_jd": create_jd,
    "compare_candidates": compare_candidates,
    "generate_interview_questions": generate_interview_questions,
    "create_shortlist": create_shortlist,
    "list_shortlists": list_shortlists,
    "add_to_shortlist": add_to_shortlist,
    "send_interview_invite": send_interview_invite,
    "open_jd": open_jd,
    "open_dashboard": open_dashboard,
    "open_shortlisting": open_shortlisting,
}

# Tool cần user_id của HR đăng nhập -> agent loop tiêm, không đưa vào schema.
USER_BOUND = {
    "create_jd": "created_by",
    "create_shortlist": "created_by",
    "add_to_shortlist": "created_by",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_jds",
            "description": "Liệt kê các vị trí tuyển dụng (Job Description).",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["active", "closed", "all"],
                        "description": "Lọc theo trạng thái, mặc định 'active'.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_jd",
            "description": "Xem chi tiết 1 JD (yêu cầu đã cấu trúc + markdown).",
            "parameters": {
                "type": "object",
                "properties": {"jd_id": {"type": "string", "description": "UUID của JD HOẶC tên vị trí, vd 'Backend Developer'."}},
                "required": ["jd_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_candidates",
            "description": (
                "Tìm ứng viên đã chấm điểm, lọc theo kỹ năng và/hoặc điểm tối thiểu. "
                "jd_id là TUỲ CHỌN: nếu HR chỉ nói 'tìm người biết Python' mà KHÔNG nhắc vị trí nào "
                "thì BỎ TRỐNG jd_id để tìm xuyên mọi vị trí — TUYỆT ĐỐI không hỏi HR jd_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "jd_id": {"type": "string", "description": "TUỲ CHỌN. UUID hoặc TÊN vị trí, chỉ điền khi HR có nêu vị trí."},
                    "min_score": {"type": "number", "description": "Điểm tối thiểu (thang 0-100)."},
                    "skill": {"type": "string", "description": "Kỹ năng cần có, vd 'python'."},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_candidate",
            "description": "Chi tiết 1 ứng viên: thông tin, điểm, giải thích, bằng chứng, kỹ năng, dự án.",
            "parameters": {
                "type": "object",
                "properties": {"candidate_id": {"type": "string", "description": "UUID HOẶC tên ứng viên, vd 'Nguyễn Minh Khoa'."}},
                "required": ["candidate_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_jd",
            "description": "Chuẩn hóa 1 JD ngôn ngữ tự nhiên bằng AI rồi LƯU vào hệ thống.",
            "parameters": {
                "type": "object",
                "properties": {
                    "raw_text": {"type": "string", "description": "Nội dung JD thô do HR mô tả."}
                },
                "required": ["raw_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_candidates",
            "description": (
                "So sánh 2+ ứng viên cùng 1 vị trí. QUAN TRỌNG: nếu HR nói kiểu 'so sánh top 3' "
                "thì ĐỪNG tự liệt kê id — hãy truyền jd_id + top_n=3, tool sẽ tự lấy đúng N người "
                "điểm cao nhất. Chỉ dùng candidate_ids khi HR gọi đích danh từng người."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "jd_id": {"type": "string", "description": "UUID hoặc tên vị trí (dùng kèm top_n)."},
                    "top_n": {"type": "integer", "description": "So sánh N ứng viên điểm cao nhất của vị trí đó."},
                    "candidate_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "UUID HOẶC tên từng ứng viên (chỉ khi HR gọi đích danh).",
                    },
                    "aspect": {"type": "string", "description": "Khía cạnh trọng tâm, vd 'Python và hạ tầng'."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_interview_questions",
            "description": "Sinh bộ câu hỏi phỏng vấn bám CV + JD cho 1 ứng viên VÀ LƯU vào buổi phỏng vấn của họ (HR xem được trong màn hình phỏng vấn).",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "UUID HOẶC tên ứng viên."},
                    "aspect": {"type": "string", "description": "Trọng tâm phỏng vấn (tùy chọn)."},
                },
                "required": ["candidate_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_shortlist",
            "description": "Đưa 1 ứng viên vào shortlist của vị trí họ ứng tuyển (tự tạo shortlist nếu chưa có). Dùng khi HR muốn 'đưa/thêm ứng viên vào shortlisting'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "UUID HOẶC tên ứng viên."},
                    "shortlist_name": {"type": "string", "description": "Tên shortlist, mặc định 'AI Shortlist'."},
                },
                "required": ["candidate_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_shortlist",
            "description": "Tạo 1 shortlist mới (rỗng) cho 1 vị trí.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jd_id": {"type": "string", "description": "UUID hoặc tên vị trí."},
                    "name": {"type": "string"},
                },
                "required": ["jd_id", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_shortlists",
            "description": "Liệt kê các shortlist của 1 vị trí kèm số ứng viên.",
            "parameters": {
                "type": "object",
                "properties": {"jd_id": {"type": "string", "description": "UUID hoặc tên vị trí."}},
                "required": ["jd_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_interview_invite",
            "description": "Gửi email mời phỏng vấn. HÀNH ĐỘNG KHÔNG ĐẢO NGƯỢC: chỉ đặt confirm=true SAU KHI HR đã xác nhận rõ ràng; nếu chưa, gọi với confirm=false để xem trước.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "when": {"type": "string", "description": "Thời gian phỏng vấn, vd '10h00 thứ Ba 14/07'."},
                    "location": {"type": "string", "description": "Nơi/link phỏng vấn."},
                    "confirm": {"type": "boolean", "description": "true = gửi thật; false = chỉ xem trước."},
                },
                "required": ["candidate_id", "when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_jd",
            "description": "Điều hướng GIAO DIỆN bên phải sang trang chi tiết của 1 vị trí (project). Dùng khi HR muốn 'mở/xem/vào' một vị trí cụ thể.",
            "parameters": {
                "type": "object",
                "properties": {"jd_id": {"type": "string", "description": "UUID của JD HOẶC tên vị trí, vd 'Backend Developer'."}},
                "required": ["jd_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_dashboard",
            "description": "Điều hướng giao diện về màn hình Dashboard (danh sách các vị trí tuyển dụng).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_shortlisting",
            "description": "Điều hướng giao diện sang màn hình Shortlisting.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
