"""
Bộ TOOL dùng chung cho AI Agent (kiến trúc B) — phần THỰC THI.

Mỗi hàm bọc lại một service đã có sẵn (pipeline / comparator / interviewer / email).
Đây thuần tuý là các hàm Python; phần MÔ TẢ tool cho LLM/MCP (tên, schema tham số,
annotation an toàn) nằm ở `tool_registry.py` — MỘT nguồn sự thật duy nhất, dùng
chung cho cả MCP server lẫn đường fallback.

HAI GIAO KÈO mà mọi tool ở đây phải giữ:

1. Chữ ký: `db` là tham số đầu tiên (Session); `owner_id` luôn có mặt và do tầng gọi
   TIÊM vào (LLM không điền được) để giới hạn phạm vi dữ liệu; các tool ghi nhận
   thêm `created_by`.
2. Kiểu trả về: LUÔN là `dict`. Không trả list/str trần. MCP (mcp>=1.10) sinh
   outputSchema từ annotation và VALIDATE kết quả — một tool khai `-> list[dict]`
   nhưng trả `{"error": ...}` lúc hỏng sẽ ném ToolError và LLM chỉ nhận được stack
   trace pydantic thay vì thông báo lỗi đọc được.

Tất cả hàm nhận `db` là tham số đầu tiên (Session), phần còn lại là tham số do LLM điền.
"""

import asyncio
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.services.ai_agent.pipeline import create_jd_from_text
from app.services.ai_agent.comparator import compare_candidates_ai
from app.services.ai_agent.evaluation_view import evaluation_for_agent, weakness_context
from app.services.ai_agent.interviewer import generate_interview_questions_ai

# Trần độ dài markdown JD nhét vào ngữ cảnh LLM. Một JD đầy đủ dài vài nghìn từ, mà
# nội dung đó được lặp lại ở MỌI bước còn lại của lượt agent -> đốt token vô ích.
_JD_MARKDOWN_MAX = 1500

# Trần số ứng viên cho MỘT lời gọi tool theo lô. Mỗi ứng viên là một lượt gọi Gemini
# chạy tuần tự, nên lô quá lớn sẽ chạm trần thời gian chờ của MCP client.
_MAX_BATCH = 8


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _run_async(coro):
    """Chạy 1 coroutine từ code ĐỒNG BỘ, kể cả khi đang nằm trong event loop.

    Agent loop là async và gọi tool đồng bộ ngay bên trong nó, nên `asyncio.run()`
    gọi thẳng ở đây ném RuntimeError("cannot be called from a running event loop").
    Đẩy sang một thread riêng (có loop riêng) thì chạy được ở CẢ hai đường — MCP
    (tool chạy trong worker thread) lẫn fallback (tool chạy trong loop).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # không có loop nào đang chạy -> chạy thẳng
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


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


def _norm(text) -> str:
    """Chuẩn hoá để so tên: bỏ dấu, hạ chữ, gộp khoảng trắng.

    LLM viết lại tên rất tuỳ tiện ("TRẦN THỊ BẢO NGỌC", "tran thi bao ngoc"), nên so
    thô sẽ trượt những trường hợp hoàn toàn hợp lệ.
    """
    s = unicodedata.normalize("NFD", str(text or "")).casefold()
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.replace("đ", "d").split())


def _tokens(text) -> list[str]:
    return _norm(text).split()


def _name_matches(ref: str, full_name) -> bool:
    """`ref` có chỉ đúng người/vị trí tên `full_name` không?

    QUY TẮC: MỌI token của `ref` phải là một token ĐẦY ĐỦ trong `full_name`.

    Đây là chỗ đã gây ra lỗi ghi sai dữ liệu. Bản trước so bằng `ILIKE %ref%`, nên khi
    LLM bịa ra tên mẫu "Trần Thị B" thì chuỗi đó lại là TIỀN TỐ của "Trần Thị Bảo
    Ngọc" -> tool ghi thẳng một người thật vào shortlist mà HR không hề nhắc tới. Với
    quy tắc token đầy đủ, "b" không phải là token nào của "tran thi bao ngoc" nên
    không khớp — đúng như mong đợi, vì "Nguyễn Văn A"/"Trần Thị B"/"Lê Văn C" là tên
    giữ chỗ chứ không phải người.

    Vẫn giữ được các cách gọi tắt hợp lệ: "Khoa" hay "Minh Khoa" đều khớp
    "Nguyễn Minh Khoa", vì mỗi token đều xuất hiện nguyên vẹn.
    """
    ref_tokens = _tokens(ref)
    if not ref_tokens:
        return False
    name_tokens = set(_tokens(full_name))
    return all(t in name_tokens for t in ref_tokens)


def _find_jd(db: Session, ref, owner_id=None) -> tuple[models.JobDescription | None, str | None]:
    """Tìm JD từ UUID HOẶC tên. Trả `(jd, lý_do_thất_bại)`.

    Thất bại thì KHÔNG trả None trơ trọi mà kèm lời giải thích có DỮ LIỆU THẬT (danh
    sách vị trí đang có). Đây là điểm khác biệt đáng giá nhất: LLM đoán sai tên vị trí
    ("Backend Developer" trong khi thật ra là "Backend Python") sẽ đọc được danh sách
    đúng ngay trong kết quả tool và tự gọi lại — thay vì bịa tiếp như đã xảy ra.
    """
    base = _owner_filter(db.query(models.JobDescription), owner_id)

    try:
        jd = base.filter(models.JobDescription.id == uuid.UUID(str(ref))).first()
        if jd is not None:
            return jd, None
    except (ValueError, AttributeError, TypeError):
        pass

    rows = base.all()
    if not rows:
        return None, "HR này chưa có vị trí tuyển dụng nào."

    def _co_the_chon(ds):
        # Cùng một tên nhưng nhiều JD (HR tạo trùng): chọn cái có nhiều ứng viên nhất.
        # Đây KHÔNG phải nhập nhằng cần hỏi lại — chính HR cũng không phân biệt được
        # hai vị trí trùng tên, và cái đang dùng thật gần như luôn là cái có hồ sơ.
        if len({_norm(j.title) for j in ds}) == 1:
            return max(ds, key=lambda j: len(j.cvs)), None
        ten = ", ".join(sorted({j.title for j in ds}))
        return None, f"Tên '{ref}' khớp nhiều vị trí: {ten}. Hãy nêu rõ một vị trí."

    chinh_xac = [j for j in rows if _norm(j.title) == _norm(ref)]
    if chinh_xac:
        return _co_the_chon(chinh_xac)

    gan_dung = [j for j in rows if _name_matches(ref, j.title)]
    if gan_dung:
        return _co_the_chon(gan_dung)

    dang_co = ", ".join(f"'{j.title}'" for j in rows[:10])
    return None, f"Không tìm thấy vị trí '{ref}'. Các vị trí đang có: {dang_co}."


def _find_candidate(db: Session, ref, owner_id=None) -> tuple[models.Candidate | None, str | None]:
    """Tìm ứng viên từ UUID HOẶC tên, chỉ trong JD của `owner_id`. Trả `(c, lý_do)`.

    NHẬP NHẰNG LÀ LỖI, KHÔNG PHẢI CHUYỆN TỰ QUYẾT. Bản trước lấy `.first()` theo
    `created_at` giảm dần, nên "Khoa" khớp ba người thì tool âm thầm chọn một —
    và HR không có cách nào biết mình vừa thao tác lên ai. Giờ trả lỗi kèm tên các
    ứng viên khớp để agent hỏi lại hoặc dùng candidate_id.
    """
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
            return c, None
        # Chuỗi ĐÚNG là UUID nhưng không có trong DB: đây là id bịa hoặc id của người
        # khác, không phải tên viết tắt -> đừng đem đi so tên.
        uuid.UUID(str(ref))
        return None, f"Không có ứng viên nào với id {ref}."
    except (ValueError, AttributeError, TypeError):
        pass

    rows = base.all()
    khop = [c for c in rows if _norm(c.name) == _norm(ref)] or [
        c for c in rows if _name_matches(ref, c.name)
    ]
    if not khop:
        return None, f"Không tìm thấy ứng viên '{ref}'."
    if len(khop) > 1:
        ds = ", ".join(f"{c.name} ({c.jd.title if c.jd else '?'})" for c in khop[:6])
        return None, (
            f"Tên '{ref}' khớp {len(khop)} hồ sơ: {ds}. Hãy dùng candidate_id từ "
            f"search_candidates thay vì tên."
        )
    return khop[0], None


def _resolve_refs(
    db: Session, refs: list[str], owner_id=None
) -> tuple[list[models.Candidate], list[str], list[str]]:
    """Resolve CẢ danh sách ứng viên TRƯỚC khi làm bất cứ việc gì.

    Trả `(ứng_viên_đã_khử_trùng, các_ref_hỏng, lý_do_từng_cái)`.

    Tách riêng khỏi vòng lặp xử lý để tool ghi có thể kiểm tra trọn danh sách rồi mới
    quyết định làm hay không — xem `_TU_CHOI_DANH_SACH_HONG`.
    """
    ok: list[models.Candidate] = []
    hong: list[str] = []
    ly_do: list[str] = []
    seen: set = set()
    for ref in refs:
        c, err = _find_candidate(db, ref, owner_id)
        if c is None:
            hong.append(str(ref))
            ly_do.append(err or f"Không tìm thấy '{ref}'.")
            continue
        if c.id in seen:  # LLM có thể truyền trùng dưới 2 dạng tên/id
            continue
        seen.add(c.id)
        ok.append(c)
    return ok, hong, ly_do


# Vì sao tool GHI từ chối cả lô khi có một ref không resolve được, thay vì làm phần
# tìm được rồi cảnh báo:
#
# Một ref không resolve được nghĩa là agent đang ĐOÁN — nó chưa tra cứu, hoặc tra rồi
# mà tự gõ lại tên. Đã xảy ra thật: `compare_candidates` lỗi vì sai tên vị trí, agent
# bèn tự nghĩ ra ["Nguyễn Văn A", "Trần Thị B", "Lê Văn C"] rồi gọi add_to_shortlist.
# Tool cũ thêm 1 người (khớp nhầm) và cảnh báo 2 người "không tìm thấy" — nhưng tác
# dụng phụ ĐÃ xảy ra và không rút lại được, còn HR thì nhận một câu trả lời vừa đúng
# vừa sai. Chặn cả lô thì agent buộc phải gọi search_candidates rồi làm lại cho đúng,
# và dữ liệu không hề bị đụng tới.
#
# Tool ĐỌC (compare_candidates) vẫn xử lý phần tìm được kèm cảnh báo: không có tác
# dụng phụ nào để mất, và một bản so sánh thiếu người vẫn hữu ích hơn là không có gì.
_TU_CHOI_DANH_SACH_HONG = (
    "Danh sách ứng viên không hợp lệ nên CHƯA thao tác gì cả. Hãy gọi search_candidates "
    "để lấy đúng candidate_ids rồi gọi lại tool này với mảng đó."
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
def list_jds(db: Session, status: str = "active", owner_id=None) -> dict:
    """Trả về ENVELOPE dict (không phải list trần) — xem giao kèo ở đầu module."""
    q = _owner_filter(db.query(models.JobDescription), owner_id)
    if status != "all":
        q = q.filter(models.JobDescription.status == status)
    rows = q.order_by(models.JobDescription.created_at.desc()).all()
    jds = [{"jd_id": str(j.id), "title": j.title, "status": j.status} for j in rows]
    return {"count": len(jds), "jds": jds}


def get_jd(db: Session, jd_id: str, owner_id=None) -> dict:
    jd, err = _find_jd(db, jd_id, owner_id)
    if jd is None:
        return {"error": err}
    md = jd.jd_markdown or ""
    truncated = len(md) > _JD_MARKDOWN_MAX
    return {
        "jd_id": str(jd.id),
        "title": jd.title,
        "requirements": jd.requirements,
        # Cắt bớt: `requirements` (đã cấu trúc) mới là thứ agent cần để lập luận;
        # markdown chỉ để trích dẫn, không đáng nhân bản vài nghìn token mỗi bước.
        "jd_markdown": md[:_JD_MARKDOWN_MAX],
        "jd_markdown_truncated": truncated,
        "status": jd.status,
    }


def search_candidates(
    db: Session,
    jd_id: str | None = None,
    min_score: float = 0.0,
    skill: str | None = None,
    limit: int = 20,
    order: str = "desc",
    owner_id=None,
) -> dict:
    """
    Tìm ứng viên đã được chấm điểm.

    `jd_id` là TUỲ CHỌN: bỏ trống -> tìm XUYÊN MỌI vị trí (dùng khi HR chỉ hỏi kiểu
    "tìm người biết Python" mà không nhắc vị trí nào). Có jd_id -> chỉ trong vị trí đó.

    `order="asc"` trả về người ĐIỂM THẤP NHẤT trước. Nghe như một tuỳ chọn phụ nhưng
    trước khi có nó thì "so sánh 3 người điểm thấp nhất" là việc KHÔNG LÀM ĐƯỢC: mọi
    đường đều sắp giảm dần, `limit` cắt từ trên xuống, nên nhóm cuối bảng không có cách
    nào lấy ra. Mà đó lại đúng là câu HR hỏi khi cần quyết định loại ai.
    """
    jd = None
    if jd_id:
        jd, err = _find_jd(db, jd_id, owner_id)
        if jd is None:
            return {"error": err}

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

    # Chốt phá hoà (created_at, id) — cùng thứ tự với bảng xếp hạng trên UI
    # (app/core/ranking.py). Chỉ ORDER BY score với một LIMIT là thứ tự giữa các ứng viên
    # TRÙNG ĐIỂM do Postgres tự quyết: agent hỏi lại y nguyên câu hỏi có thể nhận danh
    # sách khác, và ở mốc cắt limit thì thậm chí là người khác.
    tang_dan = str(order or "desc").strip().lower() == "asc"
    diem = models.Evaluation.score.asc() if tang_dan else models.Evaluation.score.desc()
    rows = (
        q.order_by(diem, models.Candidate.created_at, models.Candidate.id)
        .limit(min(limit, 50))
        .all()
    )
    briefs = [_candidate_brief(c) for c in rows]

    result = {
        "scope": jd.title if jd else "tất cả vị trí",
        # Nói rõ danh sách đang sắp theo chiều nào: cùng một mảng 3 người, hiểu nhầm
        # chiều là báo với HR "3 người giỏi nhất" trong khi đó là 3 người kém nhất.
        "sorted_by": "điểm tăng dần (thấp nhất trước)" if tang_dan
                     else "điểm giảm dần (cao nhất trước)",
        "count": len(briefs),
        # Danh sách id DỌN SẴN để truyền thẳng vào các tool theo lô (add_to_shortlist,
        # generate_interview_questions). Bắt LLM tự bới từng candidate_id ra khỏi mảng
        # `candidates` là chỗ model yếu hay trượt — có model đã bịa hẳn tên ứng viên
        # không tồn tại thay vì trích đúng id. Ở đây chép nguyên mảng này là xong.
        "candidate_ids": [b["candidate_id"] for b in briefs],
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
    c, err = _find_candidate(db, candidate_id, owner_id)
    if c is None:
        return {"error": err}
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
    ly_do: list[str] = []

    if candidate_ids:
        # Tool ĐỌC: so phần tìm được rồi cảnh báo, không chặn cả lô như tool ghi —
        # xem `_TU_CHOI_DANH_SACH_HONG`.
        cands, missing, ly_do = _resolve_refs(db, candidate_ids, owner_id)
    elif jd_id and top_n:
        jd, err = _find_jd(db, jd_id, owner_id)
        if jd is None:
            return {"error": err}
        cands = (
            db.query(models.Candidate)
            .join(models.Evaluation, models.Evaluation.cv_id == models.Candidate.id)
            .filter(models.Candidate.jd_id == jd.id)
            # Chốt phá hoà như ở find_top_candidates: "top 3" phải luôn ra cùng 3 người.
            .order_by(
                models.Evaluation.score.desc(),
                models.Candidate.created_at,
                models.Candidate.id,
            )
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
            "details": ly_do,
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
        result["details"] = ly_do
        result["warning"] = (
            f"Chỉ so sánh được {len(cands)} người; không tìm thấy: {', '.join(missing)}. "
            "PHẢI báo điều này cho HR."
        )
    return result


def _interview_has_human_work(interview: models.Interview) -> bool:
    """Buổi phỏng vấn này đã có CÔNG SỨC của HR chưa (đáp án, chấm điểm, nhận xét)?"""
    if interview.feedback or interview.feedback_summary:
        return True
    return any(
        q.answer_text or q.ai_evaluation or q.score is not None
        for q in interview.questions
    )


def _generate_questions_for(
    db: Session,
    c: models.Candidate,
    aspect: str,
    num_questions: int,
    replace: bool,
) -> dict:
    """Sinh + lưu bộ câu hỏi cho MỘT ứng viên đã resolve. Trả kết quả gọn cho batch."""
    if c.evaluation is None:
        return {"candidate": c.name, "status": "skipped",
                "reason": "Chưa được chấm điểm nên chưa thể tạo phỏng vấn."}

    interview = db.query(models.Interview).filter(models.Interview.cv_id == c.id).first()
    if interview is not None and _interview_has_human_work(interview) and not replace:
        return {"candidate": c.name, "status": "needs_confirmation",
                "reason": "Đã có buổi phỏng vấn với dữ liệu HR đã nhập; sinh lại sẽ ghi đè."}

    jd = db.get(models.JobDescription, c.jd_id)
    candidate_context = {
        "full_cv": c.raw_text,
        "ai_identified_weaknesses": weakness_context(c.evaluation),
    }
    # Gọi AI TRƯỚC khi đụng vào DB: AI hỏng thì bộ câu hỏi cũ vẫn còn nguyên.
    ai_questions = generate_interview_questions_ai(
        jd.requirements if jd else {}, candidate_context, aspect, num_questions
    )
    if not ai_questions:
        return {"candidate": c.name, "status": "failed", "reason": "AI không sinh được câu hỏi."}

    created = interview is None
    kept_questions: list[models.InterviewQuestion] = []
    if created:
        interview = models.Interview(cv_id=c.id, status="pending")
        db.add(interview)
        db.commit()
        db.refresh(interview)
    else:
        # `questions` có cascade delete-orphan -> bỏ khỏi danh sách là xoá khỏi DB, buổi
        # phỏng vấn (lịch hẹn, trạng thái, nhận xét) giữ nguyên. Chỉ thay phần AI: câu do
        # HR tự soạn là công sức tay, sinh lại bộ câu hỏi không được cuốn chúng đi theo.
        kept_questions = [q for q in interview.questions if not q.is_ai_generated]
        for q in list(interview.questions):
            if q.is_ai_generated:
                interview.questions.remove(q)
        db.flush()

    saved = 0
    next_index = 0
    for q in ai_questions:
        if not isinstance(q, dict):
            continue
        db.add(models.InterviewQuestion(
            interview_id=interview.id,
            question=q.get("question", "Câu hỏi chưa xác định"),
            expected_answer=q.get("expected_answer", ""),
            category=q.get("category", "Chung"),
            order_index=next_index,
        ))
        saved += 1
        next_index += 10

    # Đẩy câu HR tự soạn xuống cuối bộ mới, giữ đúng thứ tự tương đối cũ giữa chúng.
    for q in sorted(kept_questions, key=lambda x: x.order_index):
        q.order_index = next_index
        next_index += 10
    db.commit()

    return {
        "candidate": c.name,
        "status": "created" if created else "replaced",
        "count": saved,
    }


def generate_interview_questions(
    db: Session,
    candidate_ids: list[str],
    aspect: str = "",
    num_questions: int = 0,
    replace: bool = False,
    owner_id=None,
) -> dict:
    """
    Sinh bộ câu hỏi phỏng vấn bám CV + JD và LƯU vào DB cho MỘT HOẶC NHIỀU ứng viên,
    đúng như luồng /interviews/.../generate, để HR thấy trong màn hình phỏng vấn.

    NHẬN CẢ DANH SÁCH. HR hay yêu cầu theo lô ("tạo câu hỏi cho mỗi người trong nhóm
    trên 80 điểm"). Nếu tool chỉ nhận 1 người thì agent phải gọi lại N lần, mỗi lần
    gửi lại toàn bộ hội thoại cho LLM — tốn token theo cấp số nhân và dễ đụng trần số
    bước. Gộp thành 1 lời gọi thì chi phí gần như không đổi theo N.

    KHÔNG XOÁ BUỔI PHỎNG VẤN CŨ. Bản trước xoá thẳng `Interview` của ứng viên rồi tạo
    lại — kéo theo mọi câu trả lời, điểm chấm và nhận xét HR đã nhập biến mất, chỉ vì
    agent gọi lại tool lần hai. Giờ:
      - chưa có buổi phỏng vấn -> tạo mới;
      - có nhưng CHỈ gồm câu hỏi AI (HR chưa đụng vào) -> thay bộ câu hỏi, giữ nguyên
        buổi phỏng vấn (lịch hẹn, trạng thái);
      - có và HR ĐÃ làm việc trên đó -> BỎ QUA người đó và báo lại, trừ khi replace=True.
    """
    refs = [r for r in (candidate_ids or []) if str(r).strip()]
    if not refs:
        return {"error": "Cần ít nhất 1 ứng viên."}
    if len(refs) > _MAX_BATCH:
        return {
            "error": f"Mỗi lần chỉ xử lý tối đa {_MAX_BATCH} ứng viên (mỗi người là một "
                     f"lượt gọi AI). Hãy chia nhỏ danh sách rồi gọi lại.",
            "requested": len(refs),
        }

    # Resolve TRỌN danh sách trước khi gọi AI lần nào. Ngoài chuyện không ghi dữ liệu
    # trên một danh sách đoán (xem `_TU_CHOI_DANH_SACH_HONG`), việc này còn tiết kiệm
    # thật: mỗi ứng viên là một lượt gọi Gemini, chặn sớm thì không đốt hạn mức cho
    # một lô sai.
    cands, not_found, ly_do = _resolve_refs(db, refs, owner_id)
    if not_found:
        return {
            "error": _TU_CHOI_DANH_SACH_HONG,
            "not_found": not_found,
            "details": ly_do,
            "resolved": [c.name for c in cands],
        }

    results = [
        _generate_questions_for(db, c, aspect, num_questions, replace) for c in cands
    ]

    cho_xac_nhan = [r["candidate"] for r in results if r["status"] == "needs_confirmation"]
    out = {
        "processed": len(results),
        "results": results,
        "summary": {
            "created": sum(1 for r in results if r["status"] == "created"),
            "replaced": sum(1 for r in results if r["status"] == "replaced"),
            "skipped": sum(1 for r in results if r["status"] in ("skipped", "failed")),
        },
    }
    if cho_xac_nhan:
        out["needs_confirmation"] = cho_xac_nhan
        out["how_to_proceed"] = (
            "Những người này đã có dữ liệu phỏng vấn HR nhập. Hỏi HR xác nhận, nếu đồng "
            "ý thì gọi lại CHỈ với các tên đó kèm replace=true. PHẢI báo cho HR biết."
        )
    return out


# --------------------------------------------------------------------------- #
# TOOLS Shortlist
# --------------------------------------------------------------------------- #
def create_shortlist(
    db: Session, jd_id: str, name: str, created_by: str, owner_id=None
) -> dict:
    """Tạo 1 shortlist mới cho 1 vị trí."""
    jd, err = _find_jd(db, jd_id, owner_id)
    if jd is None:
        return {"error": err}
    sl = models.Shortlist(jd_id=jd.id, name=name.strip(), created_by=_uuid(created_by))
    db.add(sl)
    db.commit()
    db.refresh(sl)
    return {"status": "created", "shortlist_id": str(sl.id), "name": sl.name, "jd": jd.title}


def list_shortlists(db: Session, jd_id: str, owner_id=None) -> dict:
    """Liệt kê các shortlist của 1 vị trí (kèm số ứng viên)."""
    jd, err = _find_jd(db, jd_id, owner_id)
    if jd is None:
        return {"error": err}
    return {
        "jd": jd.title,
        "shortlists": [
            {"shortlist_id": str(s.id), "name": s.name, "count": len(s.items)}
            for s in jd.shortlists
        ],
    }


def _shortlist_for(db: Session, jd_id, name: str, created_by: str) -> models.Shortlist:
    """Lấy shortlist tên `name` của một vị trí, chưa có thì tạo.

    So tên KHÔNG PHÂN BIỆT HOA/THƯỜNG: HR gõ "điểm cao" nhưng LLM hay viết hoa lại
    thành "Điểm cao", và khớp chính xác sẽ đẻ ra hai shortlist khác nhau cho cùng một
    ý định — HR mở màn hình lên thấy danh sách bị xé đôi mà không hiểu vì sao.
    """
    sl = (
        db.query(models.Shortlist)
        .filter(models.Shortlist.jd_id == jd_id, func.lower(models.Shortlist.name) == name.lower())
        .first()
    )
    if sl is None:
        sl = models.Shortlist(jd_id=jd_id, name=name, created_by=_uuid(created_by))
        db.add(sl)
        db.commit()
        db.refresh(sl)
    return sl


def add_to_shortlist(
    db: Session,
    candidate_ids: list[str],
    created_by: str,
    shortlist_name: str = "AI Shortlist",
    allow_multiple_jds: bool = False,
    owner_id=None,
) -> dict:
    """
    Đưa MỘT HOẶC NHIỀU ứng viên vào shortlist. Tự tìm shortlist tên `shortlist_name`
    trong JD của từng ứng viên; chưa có thì tạo. Chống thêm trùng.

    NHẬN CẢ DANH SÁCH vì HR gần như luôn thao tác theo nhóm ("cho tất cả người trên 80
    điểm vào shortlist X"). Bản chỉ nhận 1 người bắt agent gọi lại N lần, mỗi lần gửi
    lại toàn bộ hội thoại cho LLM — vừa đốt token vừa dễ chạm trần số bước của agent.

    LƯU Ý NGHIỆP VỤ: shortlist thuộc về VỊ TRÍ. Nhóm ứng viên trải trên nhiều vị trí sẽ
    vào NHIỀU shortlist cùng tên, mỗi vị trí một cái — nên nhóm trải nhiều vị trí phải
    được HR xác nhận trước, xem `allow_multiple_jds`.
    """
    refs = [r for r in (candidate_ids or []) if str(r).strip()]
    if not refs:
        return {"error": "Cần ít nhất 1 ứng viên."}

    name = (shortlist_name or "AI Shortlist").strip() or "AI Shortlist"

    # Resolve TRỌN danh sách trước, chưa ghi gì. Đây là tool đã từng thêm nhầm một
    # người thật vào shortlist vì LLM bịa tên "Trần Thị B" — xem `_TU_CHOI_DANH_SACH_HONG`
    # và `_name_matches`. Chặn ở đây thì cả shortlist lẫn dữ liệu đều không bị đụng.
    cands, not_found, ly_do = _resolve_refs(db, refs, owner_id)
    if not_found:
        return {
            "error": _TU_CHOI_DANH_SACH_HONG,
            "not_found": not_found,
            "details": ly_do,
            "resolved": [c.name for c in cands],
        }


    jd_ids = {c.jd_id for c in cands}
    if len(jd_ids) > 1 and not allow_multiple_jds:
        phan_bo: dict[str, list[str]] = {}
        for c in cands:
            phan_bo.setdefault(c.jd.title if c.jd else "?", []).append(c.name)
        return {
            "error": "needs_confirmation",
            "message": (
                f"Nhóm này gồm ứng viên của {len(jd_ids)} vị trí khác nhau, nên sẽ tạo "
                f"{len(jd_ids)} shortlist riêng mang cùng tên '{name}' — mỗi vị trí một cái. "
                "Nếu bạn chỉ định làm cho MỘT vị trí thì hãy nói rõ vị trí nào."
            ),
            "by_jd": {k: len(v) for k, v in phan_bo.items()},
            "details": phan_bo,
            "how_to_proceed": (
                "HỎI HR xem có đúng ý muốn làm cho tất cả các vị trí trên không. Đồng ý "
                "thì gọi lại kèm allow_multiple_jds=true; nếu HR chỉ muốn một vị trí thì "
                "gọi lại search_candidates với đúng jd_id đó rồi lấy danh sách mới."
            ),
        }

    added, already_in = [], []
    theo_vi_tri: dict[str, int] = {}

    for c in cands:
        sl = _shortlist_for(db, c.jd_id, name, created_by)
        exists = (
            db.query(models.ShortlistItem)
            .filter(
                models.ShortlistItem.shortlist_id == sl.id,
                models.ShortlistItem.cv_id == c.id,
            )
            .first()
        )
        if exists:
            already_in.append(c.name)
            continue

        db.add(models.ShortlistItem(shortlist_id=sl.id, cv_id=c.id))
        added.append(c.name)
        jd_title = c.jd.title if c.jd else "?"
        theo_vi_tri[jd_title] = theo_vi_tri.get(jd_title, 0) + 1

    db.commit()

    out = {
        "shortlist": name,
        "added": added,
        "added_count": len(added),
        "by_jd": theo_vi_tri,
    }
    if already_in:
        out["already_in"] = already_in
    # Điều hướng sang màn hình Shortlisting để HR thấy ngay kết quả.
    if added:
        out["ui_action"] = {"type": "navigate", "path": "/shortlisting"}
    return out


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
    c, err = _find_candidate(db, candidate_id, owner_id)
    if c is None:
        return {"error": err}
    if not c.email:
        return {"error": f"Ứng viên {c.name} chưa có email nên không gửi được thư mời."}

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
    # `_run_async` chứ không phải `asyncio.run`: tool này bị gọi từ bên trong agent
    # loop (async), nơi asyncio.run() luôn ném RuntimeError.
    from app.services.email import send_interview_email

    try:
        _run_async(send_interview_email(c.email, preview["name"], when, location))
    except Exception as e:  # noqa: BLE001 - SMTP hỏng phải nói rõ, không giả vờ đã gửi
        return {"error": f"Gửi email thất bại: {type(e).__name__}: {e}", **preview}
    return {"status": "sent", **preview}


# --------------------------------------------------------------------------- #
# TOOLS — GIAI ĐOẠN SAU PHỎNG VẤN
#
# Trước đây agent chỉ đi được tới lúc SINH câu hỏi rồi tắc: nó tạo được bộ câu hỏi
# nhưng không đọc lại được, không ghi nổi câu trả lời, không chốt được nhận/loại và
# không gửi được thư kết quả. HR phải bỏ khung chat, mở giao diện làm tay phần còn
# lại. Bốn tool dưới đây khép nốt vòng đời đó, và đi CHUNG một đường với giao diện:
# cùng bảng, cùng hàm chấm của `interviewer`, cùng bộ điều kiện gửi mail của
# `routers/shortlist` — nên hai nơi không thể nói hai kết quả khác nhau.
# --------------------------------------------------------------------------- #
# Trần số câu trả lời cho MỘT lời gọi: mỗi câu là một lượt gọi AI chạy tuần tự.
_MAX_ANSWERS = 12
# Trần số thư cho MỘT lời gọi. Thư đã gửi không rút lại được, nên thà bắt chia lô.
_MAX_EMAILS = 30

_DECISIONS = ("accepted", "rejected", "pending")


def _questions_in_order(interview: models.Interview) -> list[models.InterviewQuestion]:
    """Câu hỏi theo đúng thứ tự HR nhìn thấy trên giao diện.

    Thứ tự này là HỢP ĐỒNG giữa `get_interview` và `record_interview_answers`: agent
    đọc câu hỏi số 1..N rồi gửi lại đúng N câu trả lời theo thứ tự đó. Sắp xếp ở một
    chỗ duy nhất để hai tool không bao giờ đánh số lệch nhau.
    """
    return sorted(interview.questions, key=lambda q: q.order_index)


def _interview_score(interview: models.Interview) -> tuple[int, float | None]:
    """(số câu đã chấm, điểm trung bình thang 10). Chưa chấm câu nào -> (0, None)."""
    diem = [q.score for q in interview.questions if q.score is not None]
    if not diem:
        return 0, None
    return len(diem), round(sum(diem) / len(diem), 2)


def _interview_of(db: Session, c: models.Candidate) -> models.Interview | None:
    return db.query(models.Interview).filter(models.Interview.cv_id == c.id).first()


def get_interview(db: Session, candidate_id: str, owner_id=None) -> dict:
    """Đọc buổi phỏng vấn của 1 ứng viên: câu hỏi, câu trả lời, điểm, nhận xét.

    Đây là tool agent PHẢI gọi trước `record_interview_answers`, vì thứ tự câu hỏi
    trong kết quả chính là thứ tự mà lô câu trả lời phải khớp vào.
    """
    c, err = _find_candidate(db, candidate_id, owner_id)
    if c is None:
        return {"error": err or "Không tìm thấy ứng viên."}

    interview = _interview_of(db, c)
    if interview is None:
        return {
            "candidate": c.name,
            "candidate_id": str(c.id),
            "jd_title": c.jd.title if c.jd else None,
            "has_interview": False,
            "note": (
                "Ứng viên chưa có buổi phỏng vấn nào. Gọi generate_interview_questions "
                "để tạo bộ câu hỏi trước."
            ),
        }

    da_cham, trung_binh = _interview_score(interview)
    return {
        "candidate": c.name,
        "candidate_id": str(c.id),
        "jd_title": c.jd.title if c.jd else None,
        "has_interview": True,
        "status": interview.status,
        "question_count": len(interview.questions),
        "answered_count": da_cham,
        "average_score": trung_binh,
        "feedback_summary": interview.feedback_summary,
        "questions": [
            {
                # 1-based: HR đếm "câu 1, câu 2", không ai đếm từ 0.
                "index": i,
                "question": q.question,
                "category": q.category,
                "answer": q.answer_text,
                "score": q.score,
                "ai_evaluation": q.ai_evaluation,
            }
            for i, q in enumerate(_questions_in_order(interview), start=1)
        ],
        "ui_action": {"type": "navigate", "path": f"/projects/{c.jd_id}?open={c.id}"},
    }


def record_interview_answers(
    db: Session,
    candidate_id: str,
    answers: list[str],
    replace: bool = False,
    owner_id=None,
) -> dict:
    """
    Ghi câu trả lời của ứng viên rồi để AI chấm từng câu, đúng như luồng HR bấm chấm
    trên màn hình phỏng vấn.

    `answers` khớp theo THỨ TỰ với danh sách câu hỏi mà `get_interview` vừa trả về:
    phần tử thứ i là câu trả lời cho câu hỏi `index = i`. Chuỗi rỗng = bỏ qua câu đó
    (HR không hỏi, hoặc ứng viên không trả lời), câu đó giữ nguyên trạng thái cũ.

    KHÔNG SINH CÂU HỎI ĐÀO SÂU. Luồng trên giao diện chấm từng câu một nên chèn thêm
    câu follow-up vào giữa là hợp lý; ở đây agent gửi cả lô theo số thứ tự, mà chèn
    câu mới giữa chừng sẽ làm chính những số thứ tự đó lệch đi ngay trong lúc lô đang
    chạy. Muốn đào sâu thì HR làm trên màn hình phỏng vấn.
    """
    c, err = _find_candidate(db, candidate_id, owner_id)
    if c is None:
        return {"error": err or "Không tìm thấy ứng viên."}

    interview = _interview_of(db, c)
    if interview is None:
        return {
            "error": (
                f"{c.name} chưa có buổi phỏng vấn nên chưa có câu hỏi để trả lời. "
                "Gọi generate_interview_questions trước."
            )
        }
    if interview.status == "completed":
        return {
            "error": (
                f"Buổi phỏng vấn của {c.name} đã kết thúc, không nhập thêm câu trả lời "
                "được nữa."
            )
        }

    cau_hoi = _questions_in_order(interview)
    ds = list(answers or [])
    if not any((a or "").strip() for a in ds):
        return {"error": "Chưa có câu trả lời nào để ghi."}
    if len(ds) > len(cau_hoi):
        return {
            "error": (
                f"Buổi phỏng vấn chỉ có {len(cau_hoi)} câu hỏi nhưng nhận được "
                f"{len(ds)} câu trả lời. Gọi get_interview để lấy đúng danh sách câu hỏi "
                "rồi gửi lại theo đúng thứ tự."
            ),
            "question_count": len(cau_hoi),
        }
    if len(ds) > _MAX_ANSWERS:
        return {
            "error": f"Mỗi lần chỉ chấm tối đa {_MAX_ANSWERS} câu (mỗi câu là một lượt "
                     f"gọi AI). Hãy chia nhỏ rồi gọi lại.",
            "requested": len(ds),
        }

    # Không ghi đè công sức đã có mà không hỏi: một câu đã có câu trả lời nghĩa là HR
    # (hoặc lượt trước) đã nhập rồi, và ghi đè sẽ cuốn theo cả điểm lẫn nhận xét của
    # câu đó. Cùng cách xử lý với generate_interview_questions.
    de_len = [
        i + 1
        for i, (q, a) in enumerate(zip(cau_hoi, ds))
        if (a or "").strip() and q.answer_text
    ]
    if de_len and not replace:
        return {
            "error": "needs_confirmation",
            "message": (
                f"Câu {', '.join(map(str, de_len))} của {c.name} đã có câu trả lời và điểm. "
                "Nhập lại sẽ GHI ĐÈ cả câu trả lời lẫn nhận xét cũ."
            ),
            "how_to_proceed": (
                "Hỏi HR xác nhận. Đồng ý thì gọi lại kèm replace=true. Nếu HR chỉ muốn bổ "
                "sung các câu CÒN TRỐNG thì để chuỗi rỗng ở đúng vị trí những câu đã có."
            ),
        }

    from app.services.ai_agent.interviewer import (
        eval_failed,
        evaluate_interview_answer_ai,
    )

    ket_qua, cham_hong = [], []
    for i, (q, tra_loi) in enumerate(zip(cau_hoi, ds), start=1):
        tra_loi = (tra_loi or "").strip()
        if not tra_loi:
            continue
        # Gọi AI TRƯỚC khi ghi: AI hỏng thì câu đó giữ nguyên, không để lại một câu
        # trả lời không có nhận xét/điểm đi kèm.
        danh_gia = evaluate_interview_answer_ai(
            question=q.question,
            expected=q.expected_answer,
            answer=tra_loi,
            allow_follow_up=False,
        )
        # AI HỎNG THÌ KHÔNG GHI GÌ CẢ. `evaluate_interview_answer_ai` nuốt lỗi và trả
        # về một bản giữ chỗ 0 điểm; lưu nó xuống là biến "chưa chấm được" thành "bị 0
        # điểm", và đó là con số HR dùng để loại người. Đã gặp thật: hết ngân sách token
        # Groq (cooldown) -> cả lô câu trả lời đều thành 0 điểm.
        if eval_failed(danh_gia):
            cham_hong.append({"index": i, "reason": danh_gia.get("error") or "AI không chấm được."})
            continue
        q.answer_text = tra_loi
        q.ai_evaluation = danh_gia.get("evaluation", "")
        q.score = danh_gia.get("score")
        ket_qua.append({
            "index": i,
            "question": q.question,
            "score": q.score,
            "ai_evaluation": q.ai_evaluation,
        })

    if not ket_qua:
        # Không ghi được câu nào -> rollback cho chắc rồi báo thẳng, đừng để agent nói
        # "đã ghi xong" trong khi DB không đổi.
        db.rollback()
        return {
            "error": "AI đang không chấm được câu trả lời nên CHƯA ghi gì cả.",
            "details": cham_hong,
            "how_to_proceed": (
                "Thường là do hết hạn mức AI trong ngày. Báo HR thử lại sau ít phút, "
                "đừng gọi lại tool này ngay."
            ),
        }

    # Có câu trả lời = buổi phỏng vấn đang diễn ra (giống endpoint chấm từng câu).
    if interview.status == "pending":
        interview.status = "in_progress"
    db.commit()

    da_cham, trung_binh = _interview_score(interview)
    out = {
        "candidate": c.name,
        "recorded": len(ket_qua),
        "answered_count": da_cham,
        "question_count": len(cau_hoi),
        "average_score": trung_binh,
        "results": ket_qua,
        "next_step": (
            "Đã chấm xong tất cả các câu. Gọi finish_interview để AI tổng kết buổi "
            "phỏng vấn." if da_cham >= len(cau_hoi) else
            f"Còn {len(cau_hoi) - da_cham} câu chưa có câu trả lời."
        ),
    }
    if cham_hong:
        out["failed"] = cham_hong
        out["warning"] = (
            f"{len(cham_hong)} câu KHÔNG chấm được (AI lỗi) nên KHÔNG được lưu — chúng vẫn "
            "trống chứ không phải bị 0 điểm. PHẢI nói rõ điều này với HR."
        )
    return out


def finish_interview(
    db: Session, candidate_id: str, confirm: bool = False, owner_id=None
) -> dict:
    """Kết thúc buổi phỏng vấn: AI đọc toàn bộ biên bản rồi viết nhận xét tổng quan.

    Cùng một hàm tổng kết với nút "Kết thúc" trên giao diện, nên bản tóm tắt HR đọc ở
    hai nơi là một.

    KHÔNG MỞ LẠI ĐƯỢC nên mặc định `confirm=False` chỉ trả về bản XEM TRƯỚC: còn bao
    nhiêu câu chưa trả lời, điểm trung bình hiện tại. Chốt sớm khi mới chấm 2/6 câu là
    khoá luôn buổi phỏng vấn ở một bản tổng kết dựa trên dữ liệu dở dang.
    """
    c, err = _find_candidate(db, candidate_id, owner_id)
    if c is None:
        return {"error": err or "Không tìm thấy ứng viên."}

    interview = _interview_of(db, c)
    if interview is None:
        return {"error": f"{c.name} chưa có buổi phỏng vấn nào."}
    if interview.status == "completed":
        da_cham, trung_binh = _interview_score(interview)
        return {
            "candidate": c.name,
            "status": "already_completed",
            "average_score": trung_binh,
            "feedback_summary": interview.feedback_summary,
        }

    tat_ca = _questions_in_order(interview)
    da_tra_loi = [q for q in tat_ca if q.answer_text]
    if not da_tra_loi:
        return {
            "error": (
                f"Buổi phỏng vấn của {c.name} chưa có câu trả lời nào nên không tổng kết "
                "được. Dùng record_interview_answers để nhập câu trả lời trước."
            )
        }

    if not confirm:
        _, tb = _interview_score(interview)
        con_trong = len(tat_ca) - len(da_tra_loi)
        return {
            "status": "preview",
            "candidate": c.name,
            "answered_count": len(da_tra_loi),
            "question_count": len(tat_ca),
            "unanswered_count": con_trong,
            "average_score": tb,
            "note": (
                "CHƯA kết thúc. Sau khi kết thúc thì KHÔNG nhập thêm câu trả lời được nữa"
                + (f" — hiện còn {con_trong} câu chưa trả lời." if con_trong else ".")
                + " Hỏi HR xác nhận rồi gọi lại với confirm=true."
            ),
        }

    from app.services.ai_agent.interviewer import summarize_interview_ai

    bien_ban = "\n".join(
        f"Hỏi: {q.question}\nĐáp: {q.answer_text}\nAI nhận xét tạm: {q.ai_evaluation}\n"
        for q in da_tra_loi
    )
    interview.feedback_summary = summarize_interview_ai(bien_ban)
    interview.status = "completed"
    db.commit()

    da_cham, trung_binh = _interview_score(interview)
    return {
        "candidate": c.name,
        "status": "completed",
        "answered_count": len(da_tra_loi),
        "scored_count": da_cham,
        "average_score": trung_binh,
        "feedback_summary": interview.feedback_summary,
    }


def list_interview_results(
    db: Session, jd_id: str = "", min_avg_score: float = 0.0, owner_id=None
) -> dict:
    """
    Bảng điểm phỏng vấn: ai đã phỏng vấn, điểm trung bình bao nhiêu (thang 10).

    Đây là tool trả lời câu hỏi kiểu "những người có điểm phỏng vấn trên 7". Điểm ở
    đây là điểm PHỎNG VẤN (trung bình các câu, thang 10), KHÁC hoàn toàn điểm sàng lọc
    CV của search_candidates (thang 100) — trộn hai thang là chốt nhận/loại nhầm người.
    """
    q = _owner_filter(
        db.query(models.Candidate)
        .join(models.Interview, models.Interview.cv_id == models.Candidate.id)
        .join(models.JobDescription, models.Candidate.jd_id == models.JobDescription.id),
        owner_id,
    )
    scope = "tất cả vị trí"
    if jd_id:
        jd, err = _find_jd(db, jd_id, owner_id)
        if jd is None:
            return {"error": err}
        q = q.filter(models.Candidate.jd_id == jd.id)
        scope = jd.title

    rows = []
    for c in q.all():
        interview = c.interview
        if interview is None:
            continue
        da_cham, trung_binh = _interview_score(interview)
        # Chưa chấm câu nào thì KHÔNG có điểm, và "không có điểm" không phải là 0:
        # lọc "trên 7 điểm" mà coi họ là 0 sẽ âm thầm loại người chưa kịp chấm.
        if trung_binh is None or trung_binh < float(min_avg_score or 0):
            continue
        rows.append({
            "candidate_id": str(c.id),
            "name": c.name,
            "jd_title": c.jd.title if c.jd else None,
            "interview_status": interview.status,
            "average_score": trung_binh,
            "scored_questions": da_cham,
            "cv_score": c.evaluation.score if c.evaluation else None,
        })

    rows.sort(key=lambda r: (-(r["average_score"] or 0), r["name"] or ""))
    chua_cham = [
        c.name
        for c in q.all()
        if c.interview is not None and _interview_score(c.interview)[1] is None
    ]
    out = {
        "scope": scope,
        "score_scale": "Điểm phỏng vấn thang 10 (trung bình các câu đã chấm).",
        "count": len(rows),
        "candidate_ids": [r["candidate_id"] for r in rows],
        "candidates": rows,
    }
    if chua_cham:
        out["not_scored_yet"] = chua_cham
        out["warning"] = (
            f"{len(chua_cham)} ứng viên đã có buổi phỏng vấn nhưng CHƯA chấm câu nào nên "
            "không nằm trong danh sách trên. PHẢI nói điều này cho HR trước khi chốt."
        )
    return out


def set_candidate_decision(
    db: Session,
    candidate_ids: list[str],
    decision: str,
    owner_id=None,
) -> dict:
    """
    Chốt kết quả tuyển dụng cho ứng viên trong shortlist: accepted / rejected / pending.

    Quyết định nằm trên shortlist_items (giống hệt nút nhận/loại trên màn hình
    Shortlisting) nên ứng viên PHẢI đã ở trong một shortlist — chưa có thì báo rõ để
    agent gọi add_to_shortlist trước, chứ không tự ý thêm giùm: "nhận người này" không
    đồng nghĩa với "tự đưa họ vào danh sách rút gọn".

    Đây chỉ là ghi quyết định. Thư báo cho ứng viên là việc RIÊNG của
    send_decision_emails — tách ra để HR còn kịp rà lại trước khi thư bay đi.
    """
    quyet_dinh = (decision or "").strip().lower()
    if quyet_dinh not in _DECISIONS:
        return {"error": f"decision phải là một trong {list(_DECISIONS)}."}

    refs = [r for r in (candidate_ids or []) if str(r).strip()]
    if not refs:
        return {"error": "Cần ít nhất 1 ứng viên."}

    cands, not_found, ly_do = _resolve_refs(db, refs, owner_id)
    if not_found:
        return {
            "error": _TU_CHOI_DANH_SACH_HONG,
            "not_found": not_found,
            "details": ly_do,
            "resolved": [c.name for c in cands],
        }

    from app.services.logging import write_audit_log

    updated, khong_trong_shortlist, giu_nguyen = [], [], []
    for c in cands:
        items = (
            db.query(models.ShortlistItem)
            .filter(models.ShortlistItem.cv_id == c.id)
            .all()
        )
        if not items:
            khong_trong_shortlist.append(c.name)
            continue
        doi = False
        for item in items:
            cu = item.candidate_status
            if cu == quyet_dinh:
                continue
            item.candidate_status = quyet_dinh
            # Lỗi gửi mail của quyết định CŨ hết liên quan -> xoá để dòng đó quay về
            # "chưa gửi" cho quyết định mới (cùng cách xử lý với router shortlist).
            if getattr(item, "notify_state", None) == "failed":
                item.notify_state = None
                item.notify_error_code = None
                item.notify_error = None
            doi = True
            write_audit_log(
                db, user_id=_uuid(owner_id) if owner_id else None,
                action="UPDATE_CANDIDATE_STATUS",
                entity_type="shortlist_item", entity_id=item.id,
                old_data={"candidate_status": cu, "cv_id": str(c.id)},
                new_data={"candidate_status": quyet_dinh, "cv_id": str(c.id)},
            )
        (updated if doi else giu_nguyen).append(c.name)

    db.commit()

    out = {
        "decision": quyet_dinh,
        "updated": updated,
        "updated_count": len(updated),
    }
    if giu_nguyen:
        out["already_set"] = giu_nguyen
    if khong_trong_shortlist:
        out["not_in_shortlist"] = khong_trong_shortlist
        out["warning"] = (
            f"Chưa chốt được cho: {', '.join(khong_trong_shortlist)} — họ không nằm trong "
            "shortlist nào. Hỏi HR có muốn thêm vào shortlist trước không. PHẢI báo cho HR."
        )
    if updated and quyet_dinh in ("accepted", "rejected"):
        out["next_step"] = (
            "Quyết định mới chỉ được LƯU, ứng viên chưa biết gì. Muốn báo cho họ thì gọi "
            "send_decision_emails."
        )
        out["ui_action"] = {"type": "navigate", "path": "/shortlisting"}
    return out


def send_decision_emails(
    db: Session, jd_id: str, confirm: bool = False, owner_id=None
) -> dict:
    """
    Gửi thư báo kết quả (nhận/loại) cho các ứng viên ĐÃ CHỐT của một vị trí.

    HÀNH ĐỘNG KHÔNG THU HỒI ĐƯỢC: mặc định confirm=False chỉ trả về bản XEM TRƯỚC —
    ai sẽ nhận thư gì, ai bị bỏ qua và vì sao.

    Điều kiện gửi KHÔNG viết lại ở đây mà dùng thẳng `_classify_notify_target` của
    routers/shortlist — cùng một nguồn sự thật với nút gửi trên giao diện. Viết lại
    một bản thứ hai là cách chắc chắn nhất để một ngày nào đó ứng viên nhận thư hai
    lần, hoặc HR nhìn UI thấy "đã gửi" mà agent lại gửi thêm lần nữa.
    """
    jd, err = _find_jd(db, jd_id, owner_id)
    if jd is None:
        return {"error": err}

    from datetime import datetime, timezone

    from app.routers.shortlist import (
        _classify_notify_target,
        _load_hr_templates,
        _mark_notify_failure,
        _record_send_result,
    )
    from app.services.email_notification import send_shortlist_email

    now = datetime.now(timezone.utc)
    can_gui: list[models.ShortlistItem] = []
    bo_qua: dict[str, list[str]] = {}
    for sl in jd.shortlists:
        for item in sl.items:
            ket_luan, ma_loi, thong_bao = _classify_notify_target(item, now)
            ten = (item.cv.name if item.cv else None) or "?"
            if ket_luan == "send":
                can_gui.append(item)
            else:
                bo_qua.setdefault(ket_luan, []).append(ten)
                if ma_loi:
                    _mark_notify_failure(item, ma_loi, thong_bao, attempted=False, now=now)
    db.commit()

    xem_truoc = [
        {
            "name": (i.cv.name if i.cv else None),
            "email": (i.cv.email if i.cv else None),
            "decision": i.candidate_status,
        }
        for i in can_gui
    ]
    if not can_gui:
        return {
            "status": "nothing_to_send",
            "jd": jd.title,
            "skipped": bo_qua,
            "note": (
                "Không có ai cần gửi thư. Thường là vì chưa chốt nhận/loại (dùng "
                "set_candidate_decision) hoặc đã gửi rồi cho đúng quyết định hiện tại."
            ),
        }
    if not confirm:
        return {
            "status": "preview",
            "jd": jd.title,
            "will_send_count": len(can_gui),
            "will_send": xem_truoc,
            "skipped": bo_qua,
            "note": "CHƯA gửi gì cả. Hỏi HR xác nhận rồi gọi lại với confirm=true.",
        }
    if len(can_gui) > _MAX_EMAILS:
        return {
            "error": f"Mỗi lần chỉ gửi tối đa {_MAX_EMAILS} thư. Hãy chốt và gửi theo lô "
                     f"nhỏ hơn.",
            "pending_count": len(can_gui),
        }

    hr = db.get(models.User, _uuid(owner_id)) if owner_id else None
    if hr is None:
        return {"error": "Không xác định được HR gửi thư."}
    template_map, attachment_map = _load_hr_templates(db, hr.id)

    da_gui, that_bai = [], []
    for item in can_gui:
        # Chụp lại trước khi gửi: `_record_send_result` mở query riêng và có thể làm
        # object hiện tại hết hạn (expire on commit).
        ten = (item.cv.name if item.cv else None) or "Ứng viên"
        email = (item.cv.email if item.cv else None) or ""
        trang_thai = item.candidate_status
        item_id = item.id
        try:
            ket_qua = send_shortlist_email(
                to_email=email,
                hr_email=hr.email,
                hr_name=hr.name or "HR Staff",
                candidate_name=ten,
                jd_title=jd.title,
                status=trang_thai,
                custom_template=template_map.get(trang_thai),
                attachments=attachment_map.get(trang_thai),
            )
            _record_send_result(db, item_id, trang_thai, ket_qua)
            (da_gui if ket_qua.ok else that_bai).append(
                ten if ket_qua.ok else f"{ten}: {ket_qua.error_message}"
            )
        except Exception as e:  # noqa: BLE001 - một thư hỏng không được chặn cả lô
            db.rollback()
            that_bai.append(f"{ten}: {type(e).__name__}: {e}")

    out = {
        "status": "sent",
        "jd": jd.title,
        "sent": da_gui,
        "sent_count": len(da_gui),
        "skipped": bo_qua,
        "ui_action": {"type": "navigate", "path": "/shortlisting"},
    }
    if that_bai:
        out["failed"] = that_bai
        out["warning"] = (
            f"{len(that_bai)} thư KHÔNG gửi được. PHẢI báo cho HR biết đích danh những "
            "người đó, đừng nói chung là đã gửi xong."
        )
    return out


# --------------------------------------------------------------------------- #
# TOOLS điều hướng GIAO DIỆN (không đổi dữ liệu; trả 'ui_action' để FE nhảy trang)
# --------------------------------------------------------------------------- #
def open_jd(db: Session, jd_id: str, owner_id=None) -> dict:
    """Mở trang chi tiết 1 vị trí (project) ở phần giao diện bên phải."""
    jd, err = _find_jd(db, jd_id, owner_id)
    if jd is None:
        return {"error": err}
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

