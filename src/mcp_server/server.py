"""
HireWise MCP Server (SSE, port 8001)
====================================

Phơi các năng lực tuyển dụng THẬT của HireWise ra cho client MCP ngoài (vd Claude
Desktop). Mỗi tool bọc lại hàm trong app.services.ai_agent.agent_tools — cùng một
lớp tool mà AI Copilot trong web dùng ("viết 1 lần, expose 2 nơi").

Chạy trong container `mcp` (build từ image backend, mount ./src/backend vào /app,
PYTHONPATH=/app) nên import được app.*. Kết nối DB qua DATABASE_URL trong .env.
"""

from mcp.server.fastmcp import FastMCP

from app.database import SessionLocal
from app import models
from app.services.ai_agent import agent_tools as T
from app.services.logging import write_tool_log

mcp = FastMCP("HireWise MCP Server", host="0.0.0.0", port=8001)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _default_user_id(db) -> str | None:
    """MCP không có phiên đăng nhập -> dùng 1 tài khoản HR/admin làm chủ thể thao tác."""
    u = (
        db.query(models.User)
        .filter(models.User.role.in_(("admin", "hr_staff")))
        .order_by(models.User.role)
        .first()
    )
    return str(u.id) if u else None


def _run(fn, *args, user_bound: bool = False, acting_user_id: str = "", **kwargs):
    """
    Mở 1 session DB, gọi tool, ghi audit trail vào agent_tool_logs, đóng session.

    `acting_user_id`: do MCP CLIENT (backend) tiêm — chính là HR đang đăng nhập. LLM
    không nhìn thấy tham số này (backend lọc khỏi schema trước khi đưa cho model).
    Không có thì rơi về user mặc định (client ngoài như Claude Desktop).
    """
    db = SessionLocal()
    actor = None
    try:
        actor = acting_user_id or _default_user_id(db)
        if user_bound:
            kwargs.setdefault("created_by", actor)
        result = fn(db, *args, **kwargs)
    except Exception as e:  # noqa: BLE001 - trả lỗi có cấu trúc cho client MCP
        result = {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()

    failed = isinstance(result, dict) and "error" in result
    write_tool_log(
        tool_name=fn.__name__,
        input_params={"args": list(args), **kwargs},
        result=result,
        status="error" if failed else "success",
        user_id=actor,
    )
    return result


# --------------------------------------------------------------------------- #
# Tools: đọc / tra cứu
# --------------------------------------------------------------------------- #
@mcp.tool()
def health() -> str:
    """Kiểm tra MCP server + kết nối DB. Trả về số vị trí tuyển dụng đang có."""
    db = SessionLocal()
    try:
        n = db.query(models.JobDescription).count()
        return f"HireWise MCP OK — {n} job description(s) in DB."
    finally:
        db.close()


@mcp.tool()
def list_jds(status: str = "active", acting_user_id: str = "") -> list[dict]:
    """Liệt kê vị trí tuyển dụng ('active' | 'closed' | 'all')."""
    return _run(T.list_jds, status=status, acting_user_id=acting_user_id)


@mcp.tool()
def get_jd(jd_id: str, acting_user_id: str = "") -> dict:
    """Chi tiết 1 JD (UUID hoặc tên vị trí)."""
    return _run(T.get_jd, jd_id, acting_user_id=acting_user_id)


@mcp.tool()
def search_candidates(
    jd_id: str = "",
    min_score: float = 0.0,
    skill: str = "",
    limit: int = 20,
    acting_user_id: str = "",
) -> dict:
    """
    Tìm ứng viên đã chấm điểm, lọc theo kỹ năng và/hoặc điểm tối thiểu (thang 0-100).
    jd_id TUỲ CHỌN: bỏ trống -> tìm xuyên MỌI vị trí (khi HR chỉ nói "tìm người biết
    Python" mà không nhắc vị trí). TUYỆT ĐỐI không hỏi HR jd_id.
    """
    return _run(
        T.search_candidates,
        jd_id=jd_id or None,
        min_score=min_score,
        skill=skill or None,
        limit=limit,
        acting_user_id=acting_user_id,
    )


@mcp.tool()
def get_candidate(candidate_id: str, acting_user_id: str = "") -> dict:
    """Chi tiết 1 ứng viên (UUID hoặc tên): điểm, giải thích, kỹ năng, dự án."""
    return _run(T.get_candidate, candidate_id, acting_user_id=acting_user_id)


# --------------------------------------------------------------------------- #
# Tools: hành động
# --------------------------------------------------------------------------- #
@mcp.tool()
def create_jd(raw_text: str, acting_user_id: str = "") -> dict:
    """Chuẩn hóa 1 JD ngôn ngữ tự nhiên bằng AI rồi lưu vào hệ thống."""
    return _run(T.create_jd, raw_text, user_bound=True, acting_user_id=acting_user_id)


@mcp.tool()
def compare_candidates(
    candidate_ids: list[str] | None = None,
    jd_id: str = "",
    top_n: int = 0,
    aspect: str = "",
    acting_user_id: str = "",
) -> dict:
    """
    So sánh 2+ ứng viên cùng 1 vị trí. Nếu HR nói 'so sánh top N' thì ĐỪNG tự liệt kê
    id — truyền jd_id + top_n, tool tự lấy N người điểm cao nhất. Chỉ dùng
    candidate_ids khi HR gọi đích danh (nhận UUID hoặc tên).
    """
    return _run(
        T.compare_candidates,
        candidate_ids=candidate_ids or None,
        jd_id=jd_id or None,
        top_n=top_n or None,
        aspect=aspect,
        acting_user_id=acting_user_id,
    )


@mcp.tool()
def generate_interview_questions(
    candidate_id: str, aspect: str = "", acting_user_id: str = ""
) -> dict:
    """
    Sinh bộ câu hỏi phỏng vấn bám CV + JD cho 1 ứng viên VÀ LƯU vào buổi phỏng vấn
    của họ (HR xem/đánh giá được sau đó). Nhận UUID hoặc tên ứng viên.
    """
    return _run(
        T.generate_interview_questions,
        candidate_id,
        aspect=aspect,
        acting_user_id=acting_user_id,
    )


@mcp.tool()
def create_shortlist(jd_id: str, name: str, acting_user_id: str = "") -> dict:
    """Tạo 1 shortlist mới (rỗng) cho 1 vị trí."""
    return _run(T.create_shortlist, jd_id, name, user_bound=True, acting_user_id=acting_user_id)


@mcp.tool()
def list_shortlists(jd_id: str, acting_user_id: str = "") -> dict:
    """Liệt kê các shortlist của 1 vị trí kèm số ứng viên."""
    return _run(T.list_shortlists, jd_id, acting_user_id=acting_user_id)


@mcp.tool()
def add_to_shortlist(
    candidate_id: str, shortlist_name: str = "AI Shortlist", acting_user_id: str = ""
) -> dict:
    """
    Đưa 1 ứng viên vào shortlist của vị trí họ ứng tuyển (tự tạo shortlist nếu chưa
    có, chống trùng). Nhận UUID hoặc tên ứng viên.
    """
    return _run(
        T.add_to_shortlist,
        candidate_id,
        shortlist_name=shortlist_name,
        user_bound=True,
        acting_user_id=acting_user_id,
    )


# --------------------------------------------------------------------------- #
# Tools điều hướng GIAO DIỆN (chỉ có ý nghĩa khi client là web Copilot của HireWise;
# trả 'ui_action' để frontend nhảy trang / tô sáng).
# --------------------------------------------------------------------------- #
@mcp.tool()
def open_jd(jd_id: str, acting_user_id: str = "") -> dict:
    """Mở trang chi tiết 1 vị trí trên giao diện HireWise. Nhận UUID hoặc tên vị trí."""
    return _run(T.open_jd, jd_id, acting_user_id=acting_user_id)


@mcp.tool()
def open_dashboard(acting_user_id: str = "") -> dict:
    """Mở màn hình Dashboard (danh sách vị trí tuyển dụng)."""
    return _run(T.open_dashboard, acting_user_id=acting_user_id)


@mcp.tool()
def open_shortlisting(acting_user_id: str = "") -> dict:
    """Mở màn hình Shortlisting."""
    return _run(T.open_shortlisting, acting_user_id=acting_user_id)


if __name__ == "__main__":
    mcp.run(transport="sse")
