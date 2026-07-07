"""
HireWise MCP Server
===================

Phơi các năng lực tuyển dụng của HireWise ra dưới dạng MCP tools, để một AI agent
(agent nội bộ, Claude Desktop, hay client MCP bất kỳ) có thể ĐIỀU PHỐI toàn bộ
luồng tuyển dụng bằng ngôn ngữ tự nhiên, thay vì HR bấm từng nút.

Đây là lớp "tools" trong kiến trúc "LLM as main program": mỗi tool bọc lại một
service đã có sẵn (jd_processor, pipeline, comparator, interviewer, email...) và
ghi log vào bảng agent_tool_logs để truy vết agent đã làm gì.

Chạy:
    pip install "mcp[cli]"
    # cần các biến môi trường sẵn có của backend: DATABASE_URL, GEMINI/Gemini key, MAIL_*
    python -m mcp_server            # stdio (Claude Desktop)
    # hoặc:  mcp run mcp_server.py

Khai báo trong Claude Desktop (claude_desktop_config.json):
    {
      "mcpServers": {
        "hirewise": {
          "command": "python",
          "args": ["-m", "mcp_server"],
          "cwd": "C:/Users/ASUS/Documents/GitHub/HireWise/src/backend",
          "env": { "DATABASE_URL": "postgresql://..." }
        }
      }
    }
"""

import functools
import json
import uuid
from typing import Optional

from mcp.server.fastmcp import FastMCP

from app.database import SessionLocal
from app import models
from app.services.ai_agent.pipeline import create_jd_from_text
from app.services.ai_agent.comparator import compare_candidates_ai
from app.services.ai_agent.interviewer import generate_interview_questions_ai
from app.services.email import conf  # tái dùng ConnectionConfig đã cấu hình

mcp = FastMCP("HireWise")


# --------------------------------------------------------------------------- #
# Hạ tầng: session DB + log mọi lần gọi tool vào agent_tool_logs
# --------------------------------------------------------------------------- #
def tool_logged(fn):
    """
    Decorator: mở 1 session DB cho tool, truyền vào qua kwarg `db`, và ghi lại
    input/result/status vào bảng agent_tool_logs (đã có sẵn trong models).
    Mỗi tool commit/rollback độc lập để 1 lỗi không kéo theo các tool khác.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        db = SessionLocal()
        log = models.AgentToolLog(
            tool_name=fn.__name__,
            input_params=_json_safe(kwargs or {}),
            status="success",
        )
        try:
            result = fn(*args, db=db, **kwargs)
            log.result = _json_safe(result)
            return result
        except Exception as e:  # noqa: BLE001 - trả lỗi có cấu trúc cho agent
            db.rollback()
            log.status = "error"
            log.result = {"error": str(e)}
            return {"error": f"{type(e).__name__}: {e}"}
        finally:
            try:
                db.add(log)
                db.commit()
            except Exception:
                db.rollback()
            db.close()

    return wrapper


def _json_safe(obj):
    """Ép về dạng JSON-serializable (UUID -> str) để nhét vào cột JSONB."""
    return json.loads(json.dumps(obj, default=str, ensure_ascii=False))


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        raise ValueError(f"ID không hợp lệ: {value!r}")


def _candidate_brief(c: models.Candidate) -> dict:
    """Tóm tắt 1 ứng viên kèm điểm đánh giá (nếu đã chấm)."""
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
# NHÓM ĐỌC / TRUY VẤN (read-only, an toàn để agent gọi tự do)
# --------------------------------------------------------------------------- #
@mcp.tool()
@tool_logged
def list_jds(status: str = "active", *, db) -> list[dict]:
    """Liệt kê các Job Description theo trạng thái ('active' | 'closed' | 'all')."""
    q = db.query(models.JobDescription)
    if status != "all":
        q = q.filter(models.JobDescription.status == status)
    return [
        {"jd_id": str(j.id), "title": j.title, "status": j.status}
        for j in q.order_by(models.JobDescription.created_at.desc()).all()
    ]


@mcp.tool()
@tool_logged
def get_jd(jd_id: str, *, db) -> dict:
    """Lấy chi tiết 1 JD: yêu cầu đã cấu trúc + bản markdown cho agent đọc ngữ cảnh."""
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


@mcp.tool()
@tool_logged
def search_candidates(
    jd_id: str,
    min_score: float = 0.0,
    skill: Optional[str] = None,
    limit: int = 20,
    *,
    db,
) -> list[dict]:
    """
    Tìm ứng viên của 1 JD, lọc theo điểm tối thiểu và (tùy chọn) 1 kỹ năng.
    Trả về danh sách xếp theo điểm giảm dần — dùng để agent chọn top N.
    """
    q = (
        db.query(models.Candidate)
        .filter(models.Candidate.jd_id == _uuid(jd_id))
        .join(models.Evaluation, models.Evaluation.cv_id == models.Candidate.id)
        .filter(models.Evaluation.score >= min_score)
    )
    if skill:
        q = q.join(models.CandidateSkill).filter(
            models.CandidateSkill.normalized_name == skill.strip().lower()
        )
    q = q.order_by(models.Evaluation.score.desc()).limit(limit)
    return [_candidate_brief(c) for c in q.all()]


@mcp.tool()
@tool_logged
def get_candidate(candidate_id: str, *, db) -> dict:
    """Chi tiết 1 ứng viên: thông tin, điểm, giải thích, bằng chứng, kỹ năng, dự án."""
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
# NHÓM HÀNH ĐỘNG / GỌI AI (có side-effect — agent nên xác nhận trước khi gọi)
# --------------------------------------------------------------------------- #
@mcp.tool()
@tool_logged
def create_jd(raw_text: str, created_by: str, *, db) -> dict:
    """
    UC U001: nhận JD ngôn ngữ tự nhiên, dùng AI chuẩn hóa và LƯU vào DB.
    `created_by` là user_id của HR đang thao tác.
    """
    jd = create_jd_from_text(db, raw_text, _uuid(created_by))
    return {"jd_id": str(jd.id), "title": jd.title, "status": jd.status}


@mcp.tool()
@tool_logged
def compare_candidates(
    jd_id: str, candidate_ids: list[str], aspect: str = "", *, db
) -> dict:
    """
    So sánh trực diện nhiều ứng viên trên 1 khía cạnh (vd 'Python và hạ tầng').
    Trả về recommendation + phân tích chi tiết dạng markdown.
    """
    jd = db.get(models.JobDescription, _uuid(jd_id))
    if jd is None:
        return {"error": "Không tìm thấy JD."}

    candidates_info = []
    for cid in candidate_ids:
        c = db.get(models.Candidate, _uuid(cid))
        if c is None:
            continue
        candidates_info.append({"name": c.name or str(c.id), "cv_content": c.raw_text})
    if len(candidates_info) < 2:
        return {"error": "Cần ít nhất 2 ứng viên hợp lệ để so sánh."}

    return compare_candidates_ai(jd.requirements, candidates_info, aspect or None)


@mcp.tool()
@tool_logged
def generate_interview_questions(
    candidate_id: str, aspect: str = "", *, db
) -> dict:
    """
    Sinh bộ câu hỏi phỏng vấn bám sát CV + JD cho 1 ứng viên (UC phỏng vấn).
    KHÔNG tự lưu — trả về để HR/agent duyệt trước khi ghi vào interview.
    """
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


@mcp.tool()
async def send_interview_invite(
    candidate_id: str, when: str, location: str = "Google Meet (link gửi sau)"
) -> dict:
    """
    Gửi email mời phỏng vấn cho ứng viên. HÀNH ĐỘNG RA BÊN NGOÀI, KHÔNG ĐẢO NGƯỢC
    ĐƯỢC — agent phải xác nhận với HR trước khi gọi tool này.
    `when`: mô tả thời gian (vd '10h00 thứ Ba 14/07'). `location`: nơi/link.
    """
    from fastapi_mail import FastMail, MessageSchema, MessageType

    db = SessionLocal()
    try:
        c = db.get(models.Candidate, _uuid(candidate_id))
        if c is None or not c.email:
            return {"error": "Ứng viên không tồn tại hoặc chưa có email."}
        to_email, name = c.email, (c.name or "Ứng viên")
    finally:
        db.close()

    html = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color:#2c3e50;">Thư mời phỏng vấn</h2>
        <p>Kính gửi {name},</p>
        <p>Chúng tôi trân trọng mời bạn tham gia buổi phỏng vấn:</p>
        <ul>
            <li><b>Thời gian:</b> {when}</li>
            <li><b>Hình thức:</b> {location}</li>
        </ul>
        <p>Vui lòng phản hồi email này để xác nhận. Trân trọng.</p>
    </div>
    """
    message = MessageSchema(
        subject="[HireWise] Thư mời phỏng vấn",
        recipients=[to_email],
        body=html,
        subtype=MessageType.html,
    )
    await FastMail(conf).send_message(message)
    return {"status": "sent", "to": to_email, "when": when}


if __name__ == "__main__":
    mcp.run()  # stdio transport
