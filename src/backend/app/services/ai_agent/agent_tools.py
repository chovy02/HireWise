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
import itertools
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlencode

from sqlalchemy.exc import IntegrityError
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


# Bộ đếm nonce điều hướng. `itertools.count` chứ không phải dấu thời gian giây: một
# lượt agent gọi vài tool trong CÙNG một giây, mà hai directive trùng hệt nhau thì cái
# sau không làm gì cả.
_dem_dieu_huong = itertools.count(1)


def dieu_huong(path: str, **query) -> dict:
    """Directive bảo giao diện mở `path`, LUÔN kèm nonce `t`.

    MỌI đường điều hướng phải đi qua đây. Lý do là lỗi HR gặp nhiều nhất: agent làm
    xong việc nhưng màn hình bên trái đứng im, phải F5 mới thấy. Agent thường điều
    hướng tới ĐÚNG trang HR đang đứng, mà React Router coi "cùng một URL" là không có
    gì xảy ra — component không remount, effect nạp dữ liệu không chạy lại, nên HR nhìn
    thấy y nguyên dữ liệu cũ. `t` đổi mỗi lần khiến URL luôn khác đi, và các trang đặt
    nó trong deps của effect sẽ nạp lại.

    Trước đây `t` chỉ được gắn tay ở hai chỗ (shortlist, phỏng vấn); 5 đường còn lại
    (`open_jd`, `open_dashboard`, `open_shortlisting`, highlight kết quả tìm kiếm, mở
    chi tiết ứng viên) đều thiếu — nên đúng những thao tác hay dùng nhất lại là những
    thao tác không làm màn hình động đậy.
    """
    q = {k: str(v) for k, v in query.items() if v not in (None, "")}
    # mốc giây + số đếm trong tiến trình: đọc log biết được lúc nào, mà vẫn không trùng.
    q["t"] = f"{int(datetime.now(timezone.utc).timestamp())}-{next(_dem_dieu_huong)}"
    return {"type": "navigate", "path": f"{path}?{urlencode(q)}"}


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


def _find_candidate(
    db: Session, ref, owner_id=None, jd_id=None
) -> tuple[models.Candidate | None, str | None]:
    """Tìm ứng viên từ UUID HOẶC tên, chỉ trong JD của `owner_id`. Trả `(c, lý_do)`.

    NHẬP NHẰNG LÀ LỖI, KHÔNG PHẢI CHUYỆN TỰ QUYẾT. Bản trước lấy `.first()` theo
    `created_at` giảm dần, nên "Khoa" khớp ba người thì tool âm thầm chọn một —
    và HR không có cách nào biết mình vừa thao tác lên ai. Giờ trả lỗi kèm tên các
    ứng viên khớp để agent hỏi lại hoặc dùng candidate_id.

    `jd_id` THU HẸP VỀ MỘT VỊ TRÍ, và nó gỡ đúng bế tắc HR gặp: một người ứng tuyển
    nhiều vị trí thì gọi tên là nhập nhằng, mà HR đang đứng ở màn hình của MỘT vị trí
    nên với họ chẳng có gì mơ hồ cả. Trước đây tool không có chỗ nhận thông tin đó,
    nên "gửi thư từ chối cho Lê Hoàng Yến" bị từ chối thẳng dù agent BIẾT rõ HR đang
    mở vị trí nào (ngữ cảnh giao diện). Có `jd_id` thì tra trong đúng vị trí đó, chỉ
    khi vẫn còn nhập nhằng mới báo lỗi.
    """
    base = _owner_filter(
        db.query(models.Candidate).join(
            models.JobDescription,
            models.Candidate.jd_id == models.JobDescription.id,
        ),
        owner_id,
    )
    if jd_id:
        jd, err = _find_jd(db, jd_id, owner_id)
        # JD tra không ra (id sai, hoặc vị trí đã bị xoá) -> BÁO NGAY, tuyệt đối không
        # lặng lẽ bỏ bộ lọc rồi tra khắp mọi vị trí: làm vậy vừa mở lại đúng cảnh thao
        # tác lan sang vị trí khác, vừa khiến lỗi hiện ra dưới dạng "tên khớp 3 hồ sơ"
        # — agent đọc xong sẽ đi sửa cái tên, trong khi hỏng là ở jd_id.
        if jd is None:
            return None, err
        base = base.filter(models.Candidate.jd_id == jd.id)
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
    db: Session, refs: list[str], owner_id=None, jd_id=None
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
        c, err = _find_candidate(db, ref, owner_id, jd_id)
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
# CHỈ NÓI VẤN ĐỀ, KHÔNG DẶN VIỆC. Câu này đi thẳng vào `error`, mà LLM có thói quen
# đọc nguyên văn `error` ra cho HR — đã xảy ra thật: HR nhận đúng câu "Hãy gọi
# search_candidates để lấy đúng candidate_ids rồi gọi lại tool này với mảng đó", một
# lời dặn nội bộ hoàn toàn vô nghĩa với người dùng. Phần hướng dẫn cho LLM chuyển hết
# sang `how_to_proceed` (xem `_huong_dan_ref_hong`), nơi nó vốn thuộc về.
_TU_CHOI_DANH_SACH_HONG = (
    "Chưa xác định chắc chắn được ứng viên nào nên CHƯA thao tác gì cả."
)


def _huong_dan_ref_hong(ly_do: list[str]) -> str:
    """Việc LLM phải làm tiếp — KHÔNG dành cho HR đọc.

    Tách theo loại thất bại, vì hai loại cần hai cách chữa khác hẳn nhau:
      - nhập nhằng (một người ứng tuyển nhiều vị trí) -> thu hẹp bằng jd_id của vị trí
        HR đang mở, KHÔNG phải đi tra lại danh sách;
      - không tìm thấy -> tra lại bằng search_candidates.
    """
    nhap_nhang = any("khớp" in (r or "") for r in ly_do)
    if nhap_nhang:
        return (
            "Có tên khớp NHIỀU hồ sơ vì ứng viên ứng tuyển nhiều vị trí. Gọi lại tool "
            "này kèm jd_id của vị trí HR đang mở (xem NGỮ CẢNH GIAO DIỆN) để thu hẹp. "
            "Không có ngữ cảnh thì HỎI HR đang nói về vị trí nào — đừng tự chọn."
        )
    return (
        "Gọi search_candidates để lấy đúng candidate_ids rồi gọi lại tool này. Nói với "
        "HR bằng lời của bạn là chưa tìm ra ai, đừng đọc lại nguyên văn thông báo này."
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
    # Dashboard CHÍNH LÀ danh sách vị trí — HR hỏi "đang tuyển những vị trí nào" thì mở
    # ra cho họ nhìn, đừng bắt đọc lại y hệt trong khung chat rồi tự bấm sang.
    return {"count": len(jds), "jds": jds, "ui_action": dieu_huong("/")}


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
        # HR xin "xem chi tiết vị trí X" -> mở đúng trang vị trí đó ra.
        "ui_action": dieu_huong(f"/projects/{jd.id}"),
    }


def search_candidates(
    db: Session,
    jd_id: str | None = None,
    min_score: float = 0.0,
    max_score: float = 0.0,
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

    `max_score` cũng vậy — KHOẢNG ĐIỂM là thứ HR hỏi thường xuyên ("lấy nhóm 50 đến 60
    điểm", "ai dưới 40"). Trước khi có nó, câu đó KHÔNG diễn đạt được: LLM chỉ điền
    được `min_score=50` rồi `limit=3` cắt từ trên xuống, nên "3 người từ 50 đến 60
    điểm" trả về 77, 68, 55 — hai người đầu nằm ngoài khoảng HR vừa nêu, mà không có
    gì trong hệ thống báo sai. Đã xảy ra thật.

    `max_score=0` = KHÔNG chặn trên (giữ nguyên hành vi cũ khi HR chỉ nêu sàn).
    """
    jd = None
    if jd_id:
        jd, err = _find_jd(db, jd_id, owner_id)
        if jd is None:
            return {"error": err}

    tran = float(max_score or 0)
    san = float(min_score or 0)
    if tran and tran < san:
        return {
            "error": (
                f"Khoảng điểm không hợp lệ: max_score={tran:g} nhỏ hơn "
                f"min_score={san:g}. Hãy kiểm tra lại con số HR vừa nêu."
            )
        }

    # Không có jd_id -> tìm xuyên MỌI vị trí, nhưng vẫn phải chỉ trong vị trí của
    # chính người đang hỏi, nếu không Copilot sẽ trả ứng viên của tài khoản khác.
    q = _owner_filter(
        db.query(models.Candidate)
        .join(models.Evaluation, models.Evaluation.cv_id == models.Candidate.id)
        .join(
            models.JobDescription,
            models.Candidate.jd_id == models.JobDescription.id,
        )
        .filter(models.Evaluation.score >= san),
        owner_id,
    )
    if tran:
        q = q.filter(models.Evaluation.score <= tran)
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
        # Nhắc lại BỘ LỌC ĐÃ ÁP để LLM không mô tả sai danh sách nó vừa nhận. Đã gặp:
        # HR xin "3 người từ 50 đến 60", tool chỉ lọc được sàn 50 rồi trả 77/68/55,
        # và câu trả lời vẫn gọi đó là nhóm 50-60.
        "score_filter": (
            f"điểm từ {san:g} đến {tran:g}" if tran
            else (f"điểm từ {san:g} trở lên" if san else "không lọc theo điểm")
        ),
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
            result["ui_action"] = dieu_huong(
                f"/projects/{target}",
                highlight=",".join(b["candidate_id"] for b in briefs),
            )
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
        "ui_action": dieu_huong(f"/projects/{c.jd_id}", open=c.id),
    }


# --------------------------------------------------------------------------- #
# TOOLS (hành động / gọi AI)
# --------------------------------------------------------------------------- #
def create_jd(db: Session, raw_text: str, created_by: str, owner_id=None) -> dict:
    """created_by do agent loop tiêm vào (user đang đăng nhập), LLM không điền.
    `owner_id` nhận cho đồng nhất với các tool khác — ở đây chính là created_by."""
    jd = create_jd_from_text(db, raw_text, _uuid(created_by))
    return {
        "jd_id": str(jd.id),
        "title": jd.title,
        "status": jd.status,
        # Mở luôn vị trí vừa tạo. Directive nằm ở ĐÂY chứ không phải trong agent loop:
        # ở đó nó là một câu `if name == "create_jd"` đặc cách theo tên tool, mà luật
        # "tool tự khai màn hình của mình" chỉ giữ được nếu không có ngoại lệ nào.
        # (Agent loop vẫn phải tự thêm `refresh` cho danh sách dự án ở cột trái — JD
        # mới chưa có trong `projects` của frontend.)
        "ui_action": dieu_huong(f"/projects/{jd.id}"),
    }


def compare_candidates(
    db: Session,
    candidate_ids: list[str] | None = None,
    jd_id: str | None = None,
    count: int | None = None,
    order: str = "",
    aspect: str = "",
    owner_id=None,
) -> dict:
    """
    So sánh ứng viên. Hai cách dùng:
      1) HR chỉ đích danh  -> truyền candidate_ids (UUID HOẶC tên).
      2) HR nói "N người X nhất" -> truyền jd_id + count + order, TOOL tự lấy đúng N
         người đó từ DB (không bắt LLM phải nhớ/đọc ra từng UUID -> hết cảnh "bảo 3
         mà so 2").
    Thiếu người thì BÁO RÕ, không âm thầm bỏ qua.

    `order` KHÔNG PHẢI tuỳ chọn phụ. Trước đây tham số này tên là `top_n` và câu truy
    vấn hard-code `score.desc()`, nên "so sánh 3 ứng viên có điểm THẤP NHẤT" là việc
    KHÔNG LÀM ĐƯỢC: tool luôn trả về 3 người đứng đầu bảng, rồi LLM viết lại thành
    "ba ứng viên điểm thấp nhất là …". Không có gì trong hệ thống báo sai, mà đó lại
    đúng là câu HR hỏi khi cần quyết định LOẠI ai — tin vào nó là loại nhầm đúng
    những người giỏi nhất. Đã xảy ra thật hai lần.
    """
    cands: list[models.Candidate] = []
    missing: list[str] = []
    ly_do: list[str] = []
    chieu: str | None = None

    if candidate_ids:
        # Tool ĐỌC: so phần tìm được rồi cảnh báo, không chặn cả lô như tool ghi —
        # xem `_TU_CHOI_DANH_SACH_HONG`.
        cands, missing, ly_do = _resolve_refs(db, candidate_ids, owner_id, jd_id)
    elif jd_id and count:
        jd, err = _find_jd(db, jd_id, owner_id)
        if jd is None:
            return {"error": err}
        tang_dan = str(order or "").strip().lower() == "asc"
        chieu = "điểm THẤP nhất" if tang_dan else "điểm CAO nhất"
        diem = (
            models.Evaluation.score.asc() if tang_dan
            else models.Evaluation.score.desc()
        )
        cands = (
            db.query(models.Candidate)
            .join(models.Evaluation, models.Evaluation.cv_id == models.Candidate.id)
            .filter(models.Candidate.jd_id == jd.id)
            # Chốt phá hoà: "3 người cao nhất" phải luôn ra cùng 3 người, kể cả khi có
            # ứng viên trùng điểm ngay tại mốc cắt.
            .order_by(diem, models.Candidate.created_at, models.Candidate.id)
            .limit(max(2, int(count)))
            .all()
        )
    else:
        return {"error": "Cần truyền candidate_ids, hoặc jd_id + count + order."}

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
    if chieu:
        # Nói thẳng đã lấy đầu nào của bảng. Cùng một bộ 3 người, hiểu nhầm chiều là
        # báo với HR "3 người kém nhất" trong khi đó là 3 người giỏi nhất.
        result["selected"] = f"{len(cands)} người {chieu} của vị trí {jd.title}"
    # Tô sáng đúng những người vừa được đem ra so trên bảng xếp hạng, để HR đối chiếu
    # được bài so sánh với điểm số thật. Mọi ứng viên ở đây chắc chắn cùng một vị trí —
    # khác vị trí thì đã thoát ở nhánh trên.
    result["ui_action"] = dieu_huong(
        f"/projects/{jd_ref}", highlight=",".join(str(c.id) for c in cands)
    )
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
    jd_id: str = "",
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
    cands, not_found, ly_do = _resolve_refs(db, refs, owner_id, jd_id)
    if not_found:
        return {
            "error": _TU_CHOI_DANH_SACH_HONG,
            "not_found": not_found,
            "details": ly_do,
            "resolved": [c.name for c in cands],
            "how_to_proceed": _huong_dan_ref_hong(ly_do),
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

    # CHỈ mở màn hình phỏng vấn khi làm cho ĐÚNG MỘT người: cả lô 5 người mà nhảy vào
    # buổi của một người thì HR tưởng 4 người kia bị bỏ sót. Lô nhiều người cứ để HR
    # đứng yên và đọc câu trả lời của agent.
    xong = [c for c, r in zip(cands, results) if r["status"] in ("created", "replaced")]
    if len(cands) == 1 and xong:
        out["ui_action"] = _mo_phong_van(xong[0])
    return out


def _mo_phong_van(c: models.Candidate) -> dict:
    """Directive mở màn hình phỏng vấn CỦA ĐÚNG ứng viên này.

    Vì sao không dùng `/projects/{jd}?open={cv}` như trước: đường đó mở trang tổng quan
    vị trí rồi bật popup chi tiết ĐÁNH GIÁ — HR nhờ "chấm câu trả lời của Nguyễn Minh
    Khoa" xong lại bị ném ra màn hình tổng quan "Backend Python", không thấy buổi phỏng
    vấn mình vừa nhờ agent làm việc trên đó. Đúng lỗi đã gặp.

    Màn hình phỏng vấn KHÔNG có route riêng: nó là chế độ xem thứ ba của /shortlisting
    (`view === 'interview'` + `interviewFor`), nên phải đi qua query param.
    """
    return dieu_huong("/shortlisting", jd=c.jd_id, view="interview", cv=c.id)


# --------------------------------------------------------------------------- #
# TOOLS Shortlist
# --------------------------------------------------------------------------- #
def create_shortlist(
    db: Session, jd_id: str, name: str, created_by: str, owner_id=None
) -> dict:
    """Tạo 1 shortlist rỗng cho 1 vị trí; đã có shortlist cùng tên thì DÙNG LẠI.

    Bản trước INSERT thẳng, không tra gì cả — nên chỉ cần agent gọi tool này rồi gọi
    tiếp add_to_shortlist với cùng cái tên (hoặc HR nhờ tạo lại lần nữa) là vị trí đó
    có hai shortlist trùng tên. Dùng chung `_shortlist_for` với add_to_shortlist để
    hai đường vào không thể cho ra hai kết quả khác nhau.
    """
    jd, err = _find_jd(db, jd_id, owner_id)
    if jd is None:
        return {"error": err}
    ten = _ten_shortlist(name)
    if not ten:
        return {"error": "Cần tên shortlist."}

    da_co = _khoa_shortlist(ten) in {_khoa_shortlist(s.name) for s in jd.shortlists}
    sl = _shortlist_for(db, jd.id, ten, created_by)
    return {
        # "exists" chứ không im lặng báo "created": agent phải nói đúng cho HR là danh
        # sách đó có sẵn, thay vì để HR tưởng vừa có thêm một danh sách mới.
        "status": "exists" if da_co else "created",
        "shortlist_id": str(sl.id),
        "name": sl.name,
        "jd": jd.title,
        "count": len(sl.items),
        # Mở luôn danh sách vừa tạo. Không có dòng này thì HR nhờ "tạo shortlist tên X"
        # xong ngồi nhìn màn hình cũ, không có gì chứng tỏ nó đã được tạo.
        "ui_action": _mo_shortlist(sl),
    }


def list_shortlists(db: Session, jd_id: str, owner_id=None) -> dict:
    """Liệt kê các shortlist của 1 vị trí (kèm số ứng viên)."""
    jd, err = _find_jd(db, jd_id, owner_id)
    if jd is None:
        return {"error": err}
    ds = sorted(jd.shortlists, key=lambda s: s.created_at)
    out = {
        "jd": jd.title,
        "shortlists": [
            {"shortlist_id": str(s.id), "name": s.name, "count": len(s.items)}
            for s in ds
        ],
    }
    # Mở màn hình shortlist của ĐÚNG vị trí đó, và chọn sẵn danh sách đầu tiên. Không
    # có shortlist nào thì vẫn mở — HR thấy ngay "chưa có" kèm nút tạo, đỡ phải hỏi lại.
    out["ui_action"] = (
        _mo_shortlist(ds[0]) if ds
        else dieu_huong("/shortlisting", jd=jd.id, view="shortlist")
    )
    return out


def _mo_shortlist(sl: models.Shortlist) -> dict:
    """Directive mở ĐÚNG shortlist này trên giao diện.

    Vì sao không chỉ trả `/shortlisting`: trang đó mặc định mở chế độ Leaderboard của
    một vị trí nào đó, nên HR vừa bảo "thêm 3 người vào shortlist" xong lại nhìn thấy
    bảng xếp hạng toàn bộ ứng viên — tưởng agent chưa làm gì.

    Nonce `t` do `dieu_huong` lo.
    """
    return dieu_huong("/shortlisting", jd=sl.jd_id, view="shortlist", sl=sl.id)


def _khoa_shortlist(name) -> str:
    """Khoá so tên shortlist: bỏ qua HOA/thường, khoảng trắng thừa và dạng Unicode —
    nhưng GIỮ NGUYÊN DẤU.

    VÌ SAO KHÔNG BỎ DẤU (bản trước dùng `_norm`, và đã sai thật): trong tiếng Việt,
    hai tên chỉ khác dấu là HAI TÊN KHÁC NHAU. `_norm` đưa cả "cặn bã" lẫn "càn bả"
    về "can ba", nên HR xin tạo "cặn bã" mà vị trí đó đã có "càn bả" thì tool lặng lẽ
    DÙNG LẠI danh sách cũ — HR gõ một đằng, màn hình hiện một nẻo, và không có gì báo
    là tên đã bị thay.

    Bỏ dấu vốn để cứu trường hợp LLM gõ thiếu dấu ("tiem nang"). Nhưng cái giá là đặt
    SAI TÊN theo yêu cầu của HR, mà tên là thứ HR nhìn thấy và gọi hằng ngày. Thà đẻ
    ra một danh sách gần trùng (nhìn thấy được, xoá được) còn hơn âm thầm đổi tên.

    Khoá này cũng khớp ĐÚNG với unique index `lower(btrim(name))` dưới DB, nên tầng
    Python và tầng DB không còn nói hai chuyện khác nhau.
    """
    return _ten_shortlist(name).casefold()


def _ten_shortlist(name) -> str:
    """Dạng chuẩn của tên shortlist để LƯU vào DB (vẫn giữ dấu và chữ hoa của HR).

    Chỉ gộp khoảng trắng và đưa về NFC. NFC không thừa: chữ "ề" có hai cách mã hoá
    (một ký tự dựng sẵn, hoặc "e" + dấu rời), LLM lượt này trả cách này lượt sau trả
    cách kia — hai chuỗi HIỆN RA GIỐNG HỆT NHAU nhưng `==` là False.
    """
    return unicodedata.normalize("NFC", " ".join(str(name or "").split()))


def _shortlist_for(db: Session, jd_id, name: str, created_by: str) -> models.Shortlist:
    """Lấy shortlist tên `name` của một vị trí, chưa có thì tạo.

    SO TÊN BẰNG `_khoa_shortlist`: bỏ qua hoa/thường, khoảng trắng thừa và dạng Unicode
    (NFC/NFD) — vì cùng MỘT ý định của HR tới đây dưới nhiều mặt chữ ("tiềm năng",
    "Tiềm Năng", "tiềm  năng", bản dùng dấu rời trông y hệt mà `==` vẫn False), và mỗi
    biến thể trượt là một shortlist mới: dropdown hiện hai dòng "tiềm năng (3)" giống
    hệt nhau.

    NHƯNG GIỮ DẤU — xem `_khoa_shortlist`. Bản trước so bỏ dấu và đã sai thật: HR xin
    "cặn bã" mà vị trí đó có sẵn "càn bả" thì tool im lặng dùng lại danh sách cũ.

    Trong nhóm khớp thì lấy bản CŨ NHẤT, để hai lượt agent gọi cách nhau vẫn rơi vào
    cùng một shortlist thay vì tuỳ thứ tự Postgres trả về.

    Lọc bằng Python (mỗi vị trí chỉ có vài shortlist) thay vì trong SQL để khoá so tên
    nằm ở ĐÚNG MỘT CHỖ, không phải viết lại một lần nữa bằng SQL rồi trôi lệch.
    """
    name = _ten_shortlist(name)
    khoa = _khoa_shortlist(name)

    def tim() -> models.Shortlist | None:
        ds = (
            db.query(models.Shortlist)
            .filter(models.Shortlist.jd_id == jd_id)
            .order_by(models.Shortlist.created_at, models.Shortlist.id)
            .all()
        )
        return next((s for s in ds if _khoa_shortlist(s.name) == khoa), None)

    sl = tim()
    if sl is not None:
        return sl

    # Tra-rồi-ghi vẫn còn khe hở khi hai lượt chạy chồng nhau: cả hai cùng thấy "chưa
    # có" rồi cùng INSERT. Unique index uq_shortlists_jd_ten (models.Shortlist) là
    # chốt cuối; ở đây chỉ cần nhận lỗi đó rồi tra lại để dùng bản mà lượt kia vừa tạo.
    # begin_nested() để INSERT hỏng chỉ cuộn lại SAVEPOINT này, không giết cả session.
    try:
        with db.begin_nested():
            sl = models.Shortlist(jd_id=jd_id, name=name, created_by=_uuid(created_by))
            db.add(sl)
        db.commit()
        db.refresh(sl)
        return sl
    except IntegrityError:
        db.rollback()
        sl = tim()
        if sl is None:  # không phải va chạm tên -> để lỗi thật nổi lên
            raise
        return sl


def add_to_shortlist(
    db: Session,
    candidate_ids: list[str] | None = None,
    created_by: str = "",
    shortlist_name: str = "AI Shortlist",
    jd_id: str = "",
    min_score: float = 0.0,
    max_score: float = 0.0,
    limit: int = 0,
    order: str = "",
    allow_multiple_jds: bool = False,
    owner_id=None,
) -> dict:
    """
    Đưa ứng viên vào shortlist. Hai cách dùng, GIỐNG `compare_candidates`:
      1) HR gọi đích danh   -> truyền `candidate_ids`.
      2) HR nêu TIÊU CHÍ    -> truyền jd_id + min_score/max_score/limit/order, TOOL tự
         chọn người từ DB.

    VÌ SAO PHẢI CÓ CÁCH (2) — đây là lỗi HR gặp thật: HR gõ "thêm những ứng viên có
    điểm từ 50 đến 60 vào shortlist trung bình". Trước đây tool chỉ nhận candidate_ids,
    nên luồng bắt buộc là search_candidates -> LLM TỰ CẦM danh sách id -> add. Khâu
    giữa đó do LLM nhớ, và nó nhớ sai: nó bê nguyên bộ id của LƯỢT TRƯỚC (nhóm "3
    người thấp nhất", toàn 20 điểm) sang, thành ra shortlist "trung bình" chứa đúng ba
    người 20 điểm. Không có gì trong hệ thống phát hiện được, vì với tool thì đó vẫn
    là ba id hợp lệ. Log còn ghi lại đúng thói quen này ở compare_candidates: hai lượt
    liên tiếp dùng lại y nguyên bộ id của lượt trước đó.

    Để tool TỰ TRUY VẤN thì không còn khâu nào cho LLM nhớ sai: tiêu chí HR vừa nói
    được thi hành thẳng trên DB, trong cùng một lời gọi.

    NHẬN CẢ DANH SÁCH vì HR gần như luôn thao tác theo nhóm. Bản chỉ nhận 1 người bắt
    agent gọi lại N lần, mỗi lần gửi lại toàn bộ hội thoại cho LLM — vừa đốt token vừa
    dễ chạm trần số bước của agent.

    LƯU Ý NGHIỆP VỤ: shortlist thuộc về VỊ TRÍ. Nhóm ứng viên trải trên nhiều vị trí sẽ
    vào NHIỀU shortlist cùng tên, mỗi vị trí một cái — nên nhóm trải nhiều vị trí phải
    được HR xác nhận trước, xem `allow_multiple_jds`.
    """
    refs = [r for r in (candidate_ids or []) if str(r).strip()]
    loc: dict | None = None

    if not refs:
        # Không có id -> phải có tiêu chí. Dùng CHÍNH `search_candidates` để câu truy
        # vấn chỉ tồn tại ở một chỗ; sửa cách lọc điểm về sau không thể lệch hai nơi.
        if not (jd_id or min_score or max_score or limit):
            return {
                "error": "Cần `candidate_ids`, HOẶC tiêu chí lọc (jd_id + min_score/"
                         "max_score/limit/order).",
            }
        kq = search_candidates(
            db, jd_id=jd_id, min_score=min_score, max_score=max_score,
            limit=limit or 50, order=order or "desc", owner_id=owner_id,
        )
        if "error" in kq:
            return kq
        refs = list(kq.get("candidate_ids") or [])
        loc = {
            "scope": kq.get("scope"),
            "min_score": min_score,
            "max_score": max_score or None,
            "sorted_by": kq.get("sorted_by"),
        }
        if not refs:
            return {
                "error": "Không có ứng viên nào khớp tiêu chí nên KHÔNG thêm ai cả.",
                "criteria": loc,
                "how_to_proceed": "Nói cho HR biết là không có ai trong khoảng đó.",
            }

    if not refs:
        return {"error": "Cần ít nhất 1 ứng viên."}

    name = _ten_shortlist(shortlist_name) or "AI Shortlist"

    # Resolve TRỌN danh sách trước, chưa ghi gì. Đây là tool đã từng thêm nhầm một
    # người thật vào shortlist vì LLM bịa tên "Trần Thị B" — xem `_TU_CHOI_DANH_SACH_HONG`
    # và `_name_matches`. Chặn ở đây thì cả shortlist lẫn dữ liệu đều không bị đụng.
    cands, not_found, ly_do = _resolve_refs(db, refs, owner_id, jd_id)
    if not_found:
        return {
            "error": _TU_CHOI_DANH_SACH_HONG,
            "not_found": not_found,
            "details": ly_do,
            "resolved": [c.name for c in cands],
            "how_to_proceed": _huong_dan_ref_hong(ly_do),
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

    # LLM hay kể trùng một người trong cùng danh sách ("Nam", rồi "Nguyễn Văn Nam");
    # `_resolve_refs` giải ra cùng một Candidate nên phải lọc, không thì `added` đếm
    # người đó hai lần và agent báo lại cho HR con số sai.
    da_thay: set = set()
    cands = [c for c in cands if not (c.id in da_thay or da_thay.add(c.id))]

    dich: models.Shortlist | None = None  # shortlist để MỞ RA cho HR xem ngay
    for c in cands:
        sl = _shortlist_for(db, c.jd_id, name, created_by)
        if dich is None:
            dich = sl
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
        # KÈM ĐIỂM, không chỉ tên. HR nêu tiêu chí theo điểm ("từ 50 đến 60") nên điểm
        # là thứ DUY NHẤT chứng minh tool lấy đúng người. Trả về mỗi cái tên thì LLM
        # viết "đã thêm 2 người có điểm từ 50 đến 60" trong khi thực tế toàn người 20
        # điểm — mà chẳng có gì trong ngữ cảnh của nó mâu thuẫn để mà phát hiện.
        added.append({
            "name": c.name,
            "score": c.evaluation.score if c.evaluation else None,
        })
        jd_title = c.jd.title if c.jd else "?"
        theo_vi_tri[jd_title] = theo_vi_tri.get(jd_title, 0) + 1

    db.commit()

    out = {
        # Tên THẬT của shortlist đang dùng, không phải tên LLM vừa gõ: "Tiềm Năng" có
        # thể rơi vào danh sách "tiềm năng" đã có sẵn, và agent phải nhắc lại cho HR
        # đúng cái tên HR nhìn thấy trên màn hình.
        "shortlist": dich.name if dich is not None else name,
        "added": added,
        "added_count": len(added),
        "by_jd": theo_vi_tri,
    }
    if loc:
        # Nói rõ tool đã tự lọc theo tiêu chí nào — để câu trả lời cuối bám vào đúng
        # khoảng điểm HR nêu, thay vì bịa lại theo trí nhớ.
        out["criteria"] = loc
    # TÊN LƯU KHÁC TÊN VỪA XIN -> nói thẳng, đừng để HR tự phát hiện trên màn hình.
    #
    # Xảy ra khi rơi vào một danh sách đã có sẵn chỉ khác hoa/thường. Lỗi HR gặp là
    # bản nặng hơn của việc này: gõ "cặn bã" mà màn hình hiện "càn bả". Giờ so tên đã
    # giữ dấu nên ca đó không còn, nhưng lời nhắc này vẫn phải có — nó là thứ duy nhất
    # bắt agent NÓI RA khi tên bị đổi, thay vì im lặng báo "đã thêm xong".
    if dich is not None and dich.name != name:
        out["ten_khac_yeu_cau"] = {"HR xin": name, "danh sách dùng": dich.name}
        out["warning"] = (
            f"Đã dùng danh sách CÓ SẴN tên '{dich.name}', không phải '{name}' như vừa "
            "yêu cầu (hai tên chỉ khác hoa/thường). PHẢI nói rõ điều này với HR."
        )
    if already_in:
        out["already_in"] = already_in
    # Mở ĐÚNG shortlist vừa thao tác, không chỉ mở màn hình Shortlisting.
    if dich is not None:
        out["ui_action"] = _mo_shortlist(dich)
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
    # Thư đã ra khỏi máy chủ -> mở buổi phỏng vấn của đúng người đó, vì việc kế tiếp
    # của HR luôn là chuẩn bị câu hỏi cho họ. Chỉ mở khi GỬI THẬT: bản xem trước
    # (confirm=False) và ca gửi hỏng đều thoát ở trên, chưa có gì đổi để mà xem.
    return {"status": "sent", **preview, "ui_action": _mo_phong_van(c)}


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
        "ui_action": _mo_phong_van(c),
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
    # Mở thẳng biên bản phỏng vấn của ĐÚNG người vừa chấm, để HR đọc lại được nhận xét
    # từng câu. Trước đây tool này không trả ui_action nào nên HR ngồi lại nguyên màn
    # hình cũ (thường là trang tổng quan vị trí) và tưởng agent chưa làm gì.
    out["ui_action"] = _mo_phong_van(c)
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
            # Không kết thúc lại được, nhưng bản tổng kết cũ vẫn là thứ HR đang hỏi tới.
            "ui_action": _mo_phong_van(c),
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
        # Bản tổng kết vừa viết nằm trên chính màn hình này — mở ra để HR đọc ngay.
        "ui_action": _mo_phong_van(c),
    }


def list_interview_results(
    db: Session,
    jd_id: str = "",
    min_avg_score: float = 0.0,
    max_avg_score: float = 0.0,
    owner_id=None,
) -> dict:
    """
    Bảng điểm phỏng vấn: ai đã phỏng vấn, điểm trung bình bao nhiêu (thang 10).

    Đây là tool trả lời câu hỏi kiểu "những người có điểm phỏng vấn trên 7". Điểm ở
    đây là điểm PHỎNG VẤN (trung bình các câu, thang 10), KHÁC hoàn toàn điểm sàng lọc
    CV của search_candidates (thang 100) — trộn hai thang là chốt nhận/loại nhầm người.

    Có `max_avg_score` vì cùng lý do với `search_candidates.max_score`: HR hỏi theo
    KHOẢNG ("nhóm 5 tới 7 điểm") thường xuyên như hỏi theo ngưỡng, và thiếu chặn trên
    thì câu đó trả về cả người ngoài khoảng mà không có gì báo sai.
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

    san = float(min_avg_score or 0)
    tran = float(max_avg_score or 0)
    if tran and tran < san:
        return {
            "error": (
                f"Khoảng điểm không hợp lệ: max_avg_score={tran:g} nhỏ hơn "
                f"min_avg_score={san:g}. Hãy kiểm tra lại con số HR vừa nêu."
            )
        }

    rows = []
    for c in q.all():
        interview = c.interview
        if interview is None:
            continue
        da_cham, trung_binh = _interview_score(interview)
        # Chưa chấm câu nào thì KHÔNG có điểm, và "không có điểm" không phải là 0:
        # lọc "trên 7 điểm" mà coi họ là 0 sẽ âm thầm loại người chưa kịp chấm.
        if trung_binh is None or trung_binh < san:
            continue
        if tran and trung_binh > tran:
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
        "score_filter": (
            f"điểm từ {san:g} đến {tran:g}" if tran
            else (f"điểm từ {san:g} trở lên" if san else "không lọc theo điểm")
        ),
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

    # Đúng MỘT người -> mở thẳng biên bản của họ, đó chắc chắn là thứ HR đang hỏi tới.
    #
    # Nhiều người thì KHÔNG điều hướng: hệ thống không có màn hình nào bày bảng điểm
    # phỏng vấn của cả nhóm. Kéo HR sang một trang chỉ khớp một phần còn tệ hơn để họ
    # đứng yên đọc câu trả lời — họ sẽ tưởng trang đó là câu trả lời đầy đủ.
    if len(rows) == 1:
        c = db.query(models.Candidate).get(_uuid(rows[0]["candidate_id"]))
        if c is not None:
            out["ui_action"] = _mo_phong_van(c)
    return out


def set_candidate_decision(
    db: Session,
    candidate_ids: list[str],
    decision: str,
    jd_id: str = "",
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

    cands, not_found, ly_do = _resolve_refs(db, refs, owner_id, jd_id)
    if not_found:
        return {
            "error": _TU_CHOI_DANH_SACH_HONG,
            "not_found": not_found,
            "details": ly_do,
            "resolved": [c.name for c in cands],
            "how_to_proceed": _huong_dan_ref_hong(ly_do),
        }

    from app.services.logging import write_audit_log

    updated, khong_trong_shortlist, giu_nguyen = [], [], []
    # SHORTLIST NÀO SẼ MỞ RA CHO HR: cái chứa NHIỀU NHẤT nhóm vừa chốt.
    #
    # Bản trước lấy `items[0].shortlist` của người ĐẦU TIÊN, mà query lại không có
    # order_by. Hai chỗ sai cộng lại: (a) một ứng viên nằm trong nhiều shortlist thì
    # Postgres trả theo thứ tự vật lý trong heap, và chính vòng lặp này UPDATE các
    # item nên thứ tự đó đổi ngay giữa chừng; (b) người đầu danh sách có thể là người
    # DUY NHẤT thuộc một shortlist khác. Kết quả: cùng một câu lệnh, lần thì mở đúng
    # shortlist HR đang làm, lần thì nhảy sang shortlist khác — đúng lỗi HR gặp.
    dem_shortlist: dict = {}
    for c in cands:
        items = (
            db.query(models.ShortlistItem)
            .join(models.Shortlist, models.Shortlist.id == models.ShortlistItem.shortlist_id)
            # Thứ tự XÁC ĐỊNH, không phụ thuộc heap.
            .filter(models.ShortlistItem.cv_id == c.id)
            .order_by(models.Shortlist.created_at, models.Shortlist.id)
            .all()
        )
        if not items:
            khong_trong_shortlist.append(c.name)
            continue
        for item in items:
            sl = item.shortlist
            so, _ = dem_shortlist.get(sl.id, (0, sl))
            dem_shortlist[sl.id] = (so + 1, sl)
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
        if dem_shortlist:
            # Nhiều người nhất trước; hoà thì lấy shortlist CŨ NHẤT rồi tới id nhỏ
            # nhất — cùng quy ước với `_shortlist_for`, để hai lần chạy trên cùng dữ
            # liệu luôn mở ra đúng một màn hình.
            dich = sorted(
                dem_shortlist.values(),
                key=lambda cap: (-cap[0], cap[1].created_at, str(cap[1].id)),
            )[0][1]
            out["ui_action"] = _mo_shortlist(dich)
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
    }
    # Mở lại đúng shortlist vừa gửi để HR thấy ngay cột trạng thái email đổi.
    if can_gui:
        out["ui_action"] = _mo_shortlist(can_gui[0].shortlist)
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
        "ui_action": dieu_huong(f"/projects/{jd.id}"),
    }


def open_dashboard(db: Session, owner_id=None) -> dict:
    """Mở màn hình Dashboard (danh sách vị trí tuyển dụng)."""
    return {"ui_action": dieu_huong("/")}


def open_shortlisting(db: Session, owner_id=None) -> dict:
    """Mở màn hình Shortlisting (danh sách rút gọn ứng viên)."""
    return {"ui_action": dieu_huong("/shortlisting")}

