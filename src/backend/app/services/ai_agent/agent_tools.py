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
from app.services.ai_agent.interviewer import generate_interview_questions_ai


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _uuid(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"ID không hợp lệ: {value!r}")


def _candidate_brief(c: models.Candidate) -> dict:
    ev = c.evaluation
    return {
        "candidate_id": str(c.id),
        "name": c.name,
        "email": c.email,
        "status": c.status,
        "score": ev.score if ev else None,
        "skills": [s.skill_name for s in c.skills],
    }


# --------------------------------------------------------------------------- #
# TOOLS (read-only)
# --------------------------------------------------------------------------- #
def list_jds(db: Session, status: str = "active") -> list[dict]:
    q = db.query(models.JobDescription)
    if status != "all":
        q = q.filter(models.JobDescription.status == status)
    rows = q.order_by(models.JobDescription.created_at.desc()).all()
    return [{"jd_id": str(j.id), "title": j.title, "status": j.status} for j in rows]


def get_jd(db: Session, jd_id: str) -> dict:
    jd = db.get(models.JobDescription, _uuid(jd_id))
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
    jd_id: str,
    min_score: float = 0.0,
    skill: str | None = None,
    limit: int = 20,
) -> list[dict]:
    q = (
        db.query(models.Candidate)
        .join(models.Evaluation, models.Evaluation.cv_id == models.Candidate.id)
        .filter(models.Candidate.jd_id == _uuid(jd_id))
        .filter(models.Evaluation.score >= min_score)
    )
    if skill:
        q = q.join(
            models.CandidateSkill, models.CandidateSkill.cv_id == models.Candidate.id
        ).filter(models.CandidateSkill.normalized_name == skill.strip().lower())
    rows = q.order_by(models.Evaluation.score.desc()).limit(min(limit, 50)).all()
    return [_candidate_brief(c) for c in rows]


def get_candidate(db: Session, candidate_id: str) -> dict:
    c = db.get(models.Candidate, _uuid(candidate_id))
    if c is None:
        return {"error": "Không tìm thấy ứng viên."}
    ev = c.evaluation
    return {
        **_candidate_brief(c),
        "phone": c.phone,
        "evaluation": None if ev is None else {
            "score": ev.score,
            "score_breakdown": ev.score_breakdown,
            "explanation": ev.explanation,
            "evidence": ev.evidence,
        },
        "projects": [
            {"name": p.name, "tech_stack": p.tech_stack, "github_url": p.github_url}
            for p in c.projects
        ],
    }


# --------------------------------------------------------------------------- #
# TOOLS (hành động / gọi AI)
# --------------------------------------------------------------------------- #
def create_jd(db: Session, raw_text: str, created_by: str) -> dict:
    """created_by do agent loop tiêm vào (user đang đăng nhập), LLM không điền."""
    jd = create_jd_from_text(db, raw_text, _uuid(created_by))
    return {"jd_id": str(jd.id), "title": jd.title, "status": jd.status}


def compare_candidates(db: Session, candidate_ids: list[str], aspect: str = "") -> dict:
    cands = [db.get(models.Candidate, _uuid(cid)) for cid in candidate_ids]
    cands = [c for c in cands if c is not None]
    if len(cands) < 2:
        return {"error": "Cần ít nhất 2 ứng viên hợp lệ để so sánh."}

    jd_id = cands[0].jd_id
    if any(c.jd_id != jd_id for c in cands):
        return {"error": "Các ứng viên phải cùng một vị trí (JD) mới so sánh được."}

    jd = db.get(models.JobDescription, jd_id)
    candidates_info = [
        {"name": c.name or str(c.id), "full_cv_text": c.raw_text} for c in cands
    ]
    return compare_candidates_ai(jd.requirements, candidates_info, aspect or None)


def generate_interview_questions(db: Session, candidate_id: str, aspect: str = "") -> dict:
    c = db.get(models.Candidate, _uuid(candidate_id))
    if c is None:
        return {"error": "Không tìm thấy ứng viên."}
    jd = db.get(models.JobDescription, c.jd_id)
    candidate_info = {
        "name": c.name,
        "cv_content": c.raw_text,
        "weaknesses": (c.evaluation.evidence if c.evaluation else None),
    }
    questions = generate_interview_questions_ai(
        jd.requirements if jd else {}, candidate_info, aspect
    )
    return {"candidate_id": candidate_id, "questions": questions}


def send_interview_invite(
    db: Session,
    candidate_id: str,
    when: str,
    location: str = "Google Meet (link gửi sau)",
    confirm: bool = False,
) -> dict:
    """
    Gửi email mời phỏng vấn. AN TOÀN KHI TEST: mặc định confirm=False -> chỉ trả về
    BẢN XEM TRƯỚC, KHÔNG gửi thật. Chỉ khi HR xác nhận rõ ràng, agent mới đặt
    confirm=true để gửi.
    """
    c = db.get(models.Candidate, _uuid(candidate_id))
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

    # Gửi thật (fastapi_mail là async -> chạy trong event loop tạm)
    from fastapi_mail import FastMail, MessageSchema, MessageType
    from app.services.email import conf

    html = (
        f"<div style='font-family:Arial,sans-serif;padding:20px'>"
        f"<h2 style='color:#2c3e50'>Thư mời phỏng vấn</h2>"
        f"<p>Kính gửi {preview['name']},</p>"
        f"<p>Chúng tôi trân trọng mời bạn tham gia buổi phỏng vấn:</p>"
        f"<ul><li><b>Thời gian:</b> {when}</li>"
        f"<li><b>Hình thức:</b> {location}</li></ul>"
        f"<p>Vui lòng phản hồi email này để xác nhận. Trân trọng.</p></div>"
    )
    message = MessageSchema(
        subject="[HireWise] Thư mời phỏng vấn",
        recipients=[c.email],
        body=html,
        subtype=MessageType.html,
    )
    asyncio.run(FastMail(conf).send_message(message))
    return {"status": "sent", **preview}


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
    "send_interview_invite": send_interview_invite,
}

# Tool cần user_id của HR đăng nhập -> agent loop tiêm, không đưa vào schema.
USER_BOUND = {"create_jd": "created_by"}

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
                "properties": {"jd_id": {"type": "string"}},
                "required": ["jd_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_candidates",
            "description": "Tìm ứng viên của 1 JD, lọc theo điểm tối thiểu và (tùy chọn) 1 kỹ năng. Kết quả xếp theo điểm giảm dần.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jd_id": {"type": "string"},
                    "min_score": {"type": "number", "description": "Điểm tối thiểu 0-10."},
                    "skill": {"type": "string", "description": "Tên 1 kỹ năng cần có, vd 'python'."},
                    "limit": {"type": "integer"},
                },
                "required": ["jd_id"],
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
                "properties": {"candidate_id": {"type": "string"}},
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
            "description": "So sánh trực diện 2+ ứng viên (phải cùng 1 JD) theo một khía cạnh.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Danh sách candidate_id cần so sánh.",
                    },
                    "aspect": {"type": "string", "description": "Khía cạnh trọng tâm, vd 'Python và hạ tầng'."},
                },
                "required": ["candidate_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_interview_questions",
            "description": "Sinh bộ câu hỏi phỏng vấn bám sát CV + JD cho 1 ứng viên.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "aspect": {"type": "string", "description": "Trọng tâm phỏng vấn (tùy chọn)."},
                },
                "required": ["candidate_id"],
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
]
