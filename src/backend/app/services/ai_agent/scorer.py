import json
import os

from app.services.ai_agent.exceptions import LLMBudgetExhausted
from app.services.ai_agent.gemini_client import generate_text
from app.services.ai_agent.prompt_utils import clean_json_response

SCORER_MODEL = "gemini-2.5-flash"

# Bằng chứng được tìm NGAY TRONG lượt chấm điểm, thay vì thêm một lượt gọi riêng.
#
# VÌ SAO GỘP: bản cũ gọi API 3 lần/CV và gửi full text CV tới 2 lần (parse + evidence).
# Với trần 12k token/phút của Groq free tier, riêng khoản đó đã ngốn ~40% ngân sách
# mỗi CV, khiến upload 15 CV chắc chắn đụng rate limit. Gộp lại còn 2 lượt/CV, và
# lượt này chỉ nhận thông tin ĐÃ TRÍCH (gọn hơn CV gốc nhiều lần).
#
# Đặt LLM_EVIDENCE_FROM_CV=1 nếu cần trích dẫn đúng nguyên văn CV gốc: chính xác
# hơn nhưng tốn thêm ~2-3k token/CV.
EVIDENCE_FROM_CV = os.getenv("LLM_EVIDENCE_FROM_CV", "0") == "1"


# ────────────────────────────────────────────────────────────
# THANG ĐIỂM (RUBRIC)
# ────────────────────────────────────────────────────────────
# Trọng số nằm Ở ĐÂY, KHÔNG để model tự chọn — và điểm tổng do code nhân trọng số
# rồi cộng lại, không phải con số model tự nghĩ ra.
#
# VÌ SAO: bản cũ để model trả thẳng một `score` cạnh `score_breakdown`. Hai thứ đó
# không hề ràng buộc nhau, nên thường xuyên gặp cảnh breakdown 90/85/80 mà điểm
# tổng lại 62 — HR không có cách nào truy ra 62 từ đâu ra, và hai ứng viên tương
# đương có thể lệch nhau chục điểm chỉ vì model "cảm thấy" khác. Cố định trọng số
# ở code khiến điểm số (a) giải thích được từng phần, (b) so sánh được giữa các ứng
# viên vì mọi người dùng chung một công thức.
#
# `legacy` là tên key trong cột score_breakdown — giữ nguyên 3 tên cũ
# (skills_match / experience_match / education_match) để các bản ghi đã chấm trước
# đây và UI cũ vẫn đọc được.
RUBRIC = (
    {
        "key": "required_skills",
        "legacy": "skills_match",
        "label": "Kỹ năng bắt buộc",
        "weight": 35,
        "guide": "Mức độ đáp ứng required_skills của JD. Tính cả kỹ năng tương đương "
                 "(vd: Trello ≈ Jira). Thiếu kỹ năng cốt lõi thì phải hạ mạnh.",
    },
    {
        "key": "experience",
        "legacy": "experience_match",
        "label": "Kinh nghiệm",
        "weight": 25,
        "guide": "Số năm kinh nghiệm so với experience_years, VÀ mức độ liên quan của "
                 "công việc đã làm với responsibilities của JD. Đúng số năm nhưng sai "
                 "lĩnh vực thì không được điểm cao.",
    },
    {
        "key": "projects",
        "legacy": "project_match",
        "label": "Dự án & thành tựu",
        "weight": 15,
        "guide": "Dự án/thành tựu có chứng minh được năng lực JD cần không. Ưu tiên kết "
                 "quả đo lường được (số liệu, quy mô, tác động) hơn là danh sách công nghệ.",
    },
    {
        "key": "education",
        "legacy": "education_match",
        "label": "Học vấn",
        "weight": 10,
        "guide": "Bằng cấp/chuyên ngành so với yêu cầu education. Kinh nghiệm thực tế "
                 "mạnh có thể bù cho bằng cấp lệch chuyên ngành.",
    },
    {
        "key": "extras",
        "legacy": "extras_match",
        "label": "Ưu tiên & chứng chỉ",
        "weight": 10,
        "guide": "preferred_skills, chứng chỉ, giải thưởng, kỹ năng mềm cần cho vị trí. "
                 "Đây là phần cộng thêm — không có preferred_skills nào thì cho theo mức "
                 "trung bình, đừng cho 0.",
    },
    {
        "key": "languages",
        "legacy": "language_match",
        "label": "Ngoại ngữ",
        "weight": 5,
        "guide": "So với languages của JD. JD không yêu cầu ngoại ngữ thì cho điểm trung "
                 "tính (~70), không phạt ứng viên.",
    },
)

_RUBRIC_KEYS = tuple(spec["key"] for spec in RUBRIC)

# Model hay trả về tên trục theo kiểu cũ hoặc tự đặt lại — quy về key chuẩn thay vì
# bỏ trục đó đi (bỏ đi thì trục biến mất khỏi bảng điểm mà không ai biết vì sao).
_DIMENSION_ALIASES = {
    "skills_match": "required_skills",
    "skills": "required_skills",
    "skill": "required_skills",
    "required_skill": "required_skills",
    "hard_skills": "required_skills",
    "experience_match": "experience",
    "experiences": "experience",
    "work_experience": "experience",
    "education_match": "education",
    "project_match": "projects",
    "project": "projects",
    "projects_achievements": "projects",
    "achievements": "projects",
    "extras_match": "extras",
    "extra": "extras",
    "preferred": "extras",
    "preferred_skills": "extras",
    "certifications": "extras",
    "language_match": "languages",
    "language": "languages",
}

# Trần số phần tử cho từng mảng. Không chặn thì model viết dài vô tận, JSON chạm
# trần output rồi bị cắt giữa dòng -> lỗi hiện ra thành "không parse được JSON".
_MAX_STRENGTHS = 8
_MAX_WEAKNESSES = 8
_MAX_RISKS = 5
_MAX_INTERVIEW_FOCUS = 5
_MAX_COVERAGE = 20
_MAX_CHIPS = 12

_VERDICTS = ("strong_fit", "good_fit", "possible_fit", "weak_fit", "not_fit")
_LEVELS = ("high", "medium", "low")
_COVERAGE_STATUSES = ("met", "partial", "missing", "unknown")
_COVERAGE_KINDS = (
    "required_skill", "preferred_skill", "experience",
    "education", "language", "responsibility",
)


def _rubric_block() -> str:
    return "\n".join(
        f"- {s['key']} ({s['label']}, trọng số {s['weight']}%): {s['guide']}"
        for s in RUBRIC
    )


SCORE_PROMPT = """Bạn là chuyên gia tuyển dụng cấp cao. Hãy đánh giá ứng viên so với yêu cầu công việc một cách CHI TIẾT, CÓ CĂN CỨ VÀ KIỂM CHỨNG ĐƯỢC — người đọc phải thấy rõ vì sao ứng viên được/mất điểm ở từng chỗ.
Trả về DUY NHẤT một object JSON, không kèm giải thích, không markdown.

Yêu cầu công việc (JD):
---
{jd_requirements}
---

Thông tin ứng viên (đã trích xuất từ CV):
---
{candidate_info}
---
{cv_section}
Các trục đánh giá (cho điểm 0-100 cho TỪNG trục, độc lập nhau; hệ thống tự nhân trọng số để ra điểm tổng nên bạn KHÔNG cần tính điểm tổng):
{rubric_block}

Schema JSON cần trả về:
{
  "verdict": "một trong: strong_fit | good_fit | possible_fit | weak_fit | not_fit",
  "confidence": "một trong: high | medium | low — mức độ tin cậy của đánh giá này",
  "confidence_reason": "string 1 câu: vì sao tin cậy ở mức đó (vd: CV thiếu mô tả công việc nên phải suy luận)",
  "summary": "string 4-6 câu: chân dung ứng viên, điểm quyết định khiến họ phù hợp/không phù hợp, và khuyến nghị hành động cho HR. Viết thành văn, không gạch đầu dòng.",
  "seniority": {
    "candidate_level": "string cấp bậc thực tế của ứng viên (intern/fresher/junior/middle/senior/lead...) hoặc null",
    "jd_level": "string cấp bậc JD cần hoặc null",
    "note": "string 1 câu so sánh hai mức trên (thấp hơn / vừa / vượt yêu cầu) hoặc null"
  },
  "experience_gap": {
    "candidate_years": 0,
    "required_years": 0,
    "note": "string 1 câu: thừa/thiếu bao nhiêu năm và kinh nghiệm đó có đúng lĩnh vực không, hoặc null"
  },
  "dimensions": [
    {
      "key": "đúng một trong các key trục ở trên",
      "score": 0,
      "comment": "string 1-2 câu giải thích CỤ THỂ vì sao trục này được điểm đó",
      "matched": ["string những thứ ứng viên ĐÃ đáp ứng ở trục này"],
      "missing": ["string những thứ còn THIẾU ở trục này"]
    }
  ],
  "requirement_coverage": [
    {
      "requirement": "string tên yêu cầu, lấy NGUYÊN VĂN từ JD",
      "kind": "một trong: required_skill | preferred_skill | experience | education | language | responsibility",
      "status": "một trong: met | partial | missing | unknown",
      "evidence": "string câu trích từ dữ liệu ứng viên chứng minh status, hoặc null",
      "note": "string 1 câu bổ sung (vd: chỉ dùng ở dự án học tập, chưa có kinh nghiệm production), hoặc null"
    }
  ],
  "strengths": [
    {
      "title": "string tên điểm mạnh, ngắn gọn",
      "detail": "string 1-2 câu: điểm mạnh này giúp gì cho ĐÚNG vị trí đang tuyển",
      "impact": "một trong: high | medium | low — mức ảnh hưởng tới quyết định tuyển",
      "evidence": "string câu trích từ dữ liệu ứng viên làm căn cứ, hoặc null"
    }
  ],
  "weaknesses": [
    {
      "title": "string tên điểm yếu/thiếu hụt, ngắn gọn",
      "detail": "string 1-2 câu: thiếu hụt này gây rủi ro gì khi vào việc",
      "severity": "một trong: high | medium | low",
      "blocking": false,
      "evidence": "string câu trích làm căn cứ, hoặc null nếu là do CV THIẾU thông tin"
    }
  ],
  "risks": [
    {
      "title": "string dấu hiệu cần lưu ý",
      "detail": "string 1-2 câu mô tả và vì sao đáng lưu ý",
      "severity": "một trong: high | medium | low"
    }
  ],
  "interview_focus": [
    {
      "area": "string điều cần kiểm chứng khi phỏng vấn",
      "question": "string một câu hỏi cụ thể để kiểm chứng điều đó",
      "why": "string 1 câu: vì sao cần hỏi (bám vào điểm yếu/rủi ro/chỗ CV nói chưa rõ)"
    }
  ]
}

Quy tắc bắt buộc:
- Mọi điểm số là số nguyên 0-100. KHÔNG trả về điểm tổng.
- dimensions: phải có ĐỦ và ĐÚNG {dimension_count} trục kể trên, mỗi trục một phần tử, dùng đúng chuỗi key.
- requirement_coverage: liệt kê TỪNG required_skill và TỪNG preferred_skill của JD thành một dòng riêng, cộng thêm một dòng cho số năm kinh nghiệm, một dòng cho học vấn, một dòng cho ngoại ngữ nếu JD có yêu cầu. Tối đa {max_coverage} dòng, ưu tiên required_skill.
  + met: có bằng chứng rõ ràng.  + partial: có liên quan/tương đương nhưng chưa đủ.
  + missing: CV không hề có.     + unknown: CV nói không rõ, không kết luận được.
- Cân nhắc kỹ năng tương đương (vd: Jira và Trello đều là công cụ quản lý Agile) — coi là partial, kèm note giải thích.
- Xem xét cả certifications và awards khi đánh giá.
- CV thiếu thông tin cho một tiêu chí thì ghi nhận là thiếu, TUYỆT ĐỐI không tự suy diễn thành có.
- blocking=true chỉ khi thiếu hụt đó khiến ứng viên không làm được việc, không phải chỉ "hơi yếu".
- risks: chỉ nêu điều thật sự thấy trong dữ liệu (khoảng trống thời gian, nhảy việc dày, mô tả mâu thuẫn, quá cấp/dưới cấp so với JD). Không có thì trả [].
- Tối đa {max_strengths} strengths, {max_weaknesses} weaknesses, {max_risks} risks, {max_focus} interview_focus. Chọn thứ QUAN TRỌNG NHẤT, không kể lể.
- evidence chỉ được trích từ dữ liệu đã cho, tuyệt đối không bịa. Không tìm được căn cứ thì để null.
- Viết toàn bộ nội dung bằng tiếng Việt."""

_CV_SECTION = """
Nội dung CV gốc (dùng để trích dẫn nguyên văn làm bằng chứng):
---
{cv_text}
---
"""


# ────────────────────────────────────────────────────────────
# CHUẨN HOÁ KẾT QUẢ MODEL
# ────────────────────────────────────────────────────────────
# LLM trả JSON đúng schema ~90% số lần: thiếu trục, đặt sai tên key, trả điểm dạng
# chuỗi "85", trả strengths là list string thay vì list object... Tất cả gom về đây
# xử lý một lần, để cả pipeline và UI phía sau luôn nhận được đúng một hình dạng.

def _as_text(v) -> str | None:
    if v is None or isinstance(v, (dict, list)):
        return None
    s = str(v).strip()
    # Model thỉnh thoảng ghi đúng chữ "null"/"không có" thay vì để null thật.
    if not s or s.lower() in ("null", "none", "n/a", "không có", "không rõ"):
        return None
    return s


def _as_score(v) -> int | None:
    """None = model không cho điểm trục này (khác hẳn với cho 0 điểm)."""
    try:
        return max(0, min(100, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def _as_int(v) -> int | None:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _as_enum(v, allowed: tuple, default=None):
    s = str(v or "").strip().lower().replace(" ", "_").replace("-", "_")
    return s if s in allowed else default


def _as_chips(v, limit: int = _MAX_CHIPS) -> list[str]:
    """Về list string, chấp nhận cả string đơn, dict, hay list dict."""
    if v is None:
        return []
    if isinstance(v, str):
        items = [v]
    elif isinstance(v, dict):
        items = list(v.values())
    elif isinstance(v, list):
        items = v
    else:
        return []

    out = []
    for item in items:
        if isinstance(item, dict):
            item = (item.get("name") or item.get("skill") or item.get("title")
                    or item.get("requirement") or item.get("text"))
        text = _as_text(item)
        if text and text not in out:
            out.append(text)
    return out[:limit]


def _as_dict(v) -> dict:
    return v if isinstance(v, dict) else {}


def _as_list(v) -> list:
    if isinstance(v, list):
        return v
    # Model đôi khi bọc mảng trong dict: {"1": {...}, "2": {...}}.
    if isinstance(v, dict):
        return list(v.values())
    return []


def _normalize_dimensions(raw) -> list[dict]:
    """
    Trả về ĐÚNG các trục trong RUBRIC, theo đúng thứ tự, kèm trọng số từ code.

    Trục model không chấm được để score=None và bị loại khỏi phép tính điểm tổng
    (xem `_weighted_score`) thay vì tính là 0 điểm.
    """
    by_key: dict[str, dict] = {}

    items = raw
    if isinstance(raw, dict):
        # Dạng {"required_skills": {...}} hoặc {"required_skills": 80}.
        items = [
            {**v, "key": v.get("key") or k} if isinstance(v, dict) else {"key": k, "score": v}
            for k, v in raw.items()
        ]

    for item in _as_list(items):
        if not isinstance(item, dict):
            continue
        raw_key = str(item.get("key") or item.get("name") or "").strip().lower()
        raw_key = raw_key.replace(" ", "_").replace("-", "_")
        key = raw_key if raw_key in _RUBRIC_KEYS else _DIMENSION_ALIASES.get(raw_key)
        if key and key not in by_key:
            by_key[key] = item

    dims = []
    for spec in RUBRIC:
        got = by_key.get(spec["key"], {})
        dims.append({
            "key": spec["key"],
            "label": spec["label"],
            "weight": spec["weight"],
            "score": _as_score(got.get("score")),
            "comment": _as_text(got.get("comment")),
            "matched": _as_chips(got.get("matched")),
            "missing": _as_chips(got.get("missing")),
        })
    return dims


def _weighted_score(dims: list[dict]) -> int:
    """
    Điểm tổng = bình quân có trọng số của các trục ĐƯỢC CHẤM.

    Trục thiếu điểm bị loại khỏi cả tử số và mẫu số (chia lại trọng số) — nếu tính
    là 0 thì một CV không nêu học vấn sẽ mất trắng 10 điểm tổng chỉ vì model bỏ sót
    một trục, chứ không phải vì ứng viên kém.
    """
    scored = [d for d in dims if d["score"] is not None]
    total_weight = sum(d["weight"] for d in scored)
    if not total_weight:
        return 0
    total = sum(d["score"] * d["weight"] for d in scored)
    return max(0, min(100, int(round(total / total_weight))))


# Cho phép điểm trục "kỹ năng bắt buộc" cao hơn tỉ lệ đạt bao nhiêu điểm trước khi
# bị kéo xuống. Vẫn để một khoảng vì kỹ năng tương đương đáng được cộng thêm chút
# (biết MySQL khi JD đòi PostgreSQL không phải là số 0), nhưng không được cộng vô hạn.
_SKILL_CAP_TOLERANCE = 10

# Quy đổi trạng thái đối chiếu thành tỉ lệ đạt.
_STATUS_CREDIT = {"met": 1.0, "partial": 0.5, "unknown": 0.25, "missing": 0.0}


def _reconcile_required_skills(dims: list[dict], coverage: list[dict],
                               jd_requirements: dict) -> str | None:
    """
    Kéo điểm trục "kỹ năng bắt buộc" về đúng tỉ lệ kỹ năng thực sự đạt.

    VÌ SAO CẦN: model rất hay cho 80/100 ở trục kỹ năng trong khi bảng đối chiếu ngay
    cạnh đó ghi thiếu 1 trong 3 kỹ năng bắt buộc. Hai con số cùng màn hình mà nói hai
    chuyện khác nhau thì HR mất niềm tin vào cả hai — và đây đúng là loại lỗi mà bản
    "chấm điểm bằng cảm tính" trước đây không có cách nào phát hiện.

    CHỈ HẠ, KHÔNG BAO GIỜ NÂNG, và chỉ khi model đã liệt kê đủ số kỹ năng bắt buộc của
    JD — liệt kê thiếu thì tỉ lệ tính ra không đáng tin, thà để nguyên điểm của model.

    Trả về câu giải thích nếu có chỉnh, None nếu không.
    """
    rows = [c for c in coverage if c["kind"] == "required_skill"]
    jd_required = jd_requirements.get("required_skills") if isinstance(jd_requirements, dict) else None
    if not rows or not jd_required or len(rows) < len(jd_required):
        return None

    dim = next((d for d in dims if d["key"] == "required_skills"), None)
    if dim is None or dim["score"] is None:
        return None

    ratio = sum(_STATUS_CREDIT.get(c["status"], 0.0) for c in rows) / len(rows)
    cap = int(round(ratio * 100))
    if dim["score"] <= cap + _SKILL_CAP_TOLERANCE:
        return None

    met = sum(1 for c in rows if c["status"] == "met")
    old = dim["score"]
    dim["score"] = cap
    return (
        f"Điểm kỹ năng bắt buộc hạ từ {old} xuống {cap} cho khớp với bảng đối chiếu "
        f"({met}/{len(rows)} yêu cầu đạt)."
    )


def _normalize_coverage(raw) -> list[dict]:
    out = []
    for item in _as_list(raw)[:_MAX_COVERAGE]:
        if not isinstance(item, dict):
            # Chỉ có tên yêu cầu, không rõ đạt hay không.
            name = _as_text(item)
            if name:
                out.append({"requirement": name, "kind": None,
                            "status": "unknown", "evidence": None, "note": None})
            continue
        requirement = _as_text(item.get("requirement") or item.get("name"))
        if not requirement:
            continue
        out.append({
            "requirement": requirement,
            "kind": _as_enum(item.get("kind") or item.get("type"), _COVERAGE_KINDS),
            "status": _as_enum(item.get("status"), _COVERAGE_STATUSES, "unknown"),
            "evidence": _as_text(item.get("evidence")),
            "note": _as_text(item.get("note")),
        })
    return out


def _normalize_findings(raw, level_field: str, default_level: str,
                        limit: int, extra_flags: tuple = ()) -> list[dict]:
    """
    Chuẩn hoá strengths / weaknesses / risks — cùng một hình dạng, khác nhau ở tên
    trường mức độ (impact với điểm mạnh, severity với điểm yếu/rủi ro).

    Chấp nhận cả dạng cũ (list string) để không vỡ khi model trả về kiểu bản trước.
    """
    out = []
    for item in _as_list(raw)[:limit]:
        if not isinstance(item, dict):
            title = _as_text(item)
            if title:
                out.append({"title": title, "detail": None,
                            level_field: default_level, "evidence": None,
                            **{f: False for f in extra_flags}})
            continue
        title = _as_text(item.get("title") or item.get("name"))
        detail = _as_text(item.get("detail") or item.get("description"))
        if not title and not detail:
            continue
        entry = {
            # Chỉ có detail mà không có title thì lấy detail làm title, vì UI và
            # cột evidence cũ đều dùng title làm khoá.
            "title": title or detail,
            "detail": detail if title else None,
            level_field: _as_enum(
                item.get(level_field) or item.get("impact") or item.get("severity"),
                _LEVELS, default_level,
            ),
            "evidence": _as_text(item.get("evidence")),
        }
        for flag in extra_flags:
            entry[flag] = bool(item.get(flag))
        out.append(entry)
    return out


def _normalize_focus(raw) -> list[dict]:
    out = []
    for item in _as_list(raw)[:_MAX_INTERVIEW_FOCUS]:
        if not isinstance(item, dict):
            text = _as_text(item)
            if text:
                out.append({"area": text, "question": None, "why": None})
            continue
        area = _as_text(item.get("area") or item.get("topic"))
        question = _as_text(item.get("question"))
        if not area and not question:
            continue
        out.append({
            "area": area or question,
            "question": question,
            "why": _as_text(item.get("why") or item.get("reason")),
        })
    return out


def _legacy_evidence(strengths: list[dict], weaknesses: list[dict]) -> dict:
    """
    Dựng lại hình dạng evidence cũ ({"strengths_evidence": {tên: trích dẫn}}).

    Cột `evidence` của bảng evaluations vẫn giữ đúng hình dạng này: các bản ghi đã
    chấm từ trước không có cột `details`, nên UI phải đọc được cả hai kiểu.
    """
    return {
        "strengths_evidence": {s["title"]: s["evidence"] for s in strengths},
        "weaknesses_evidence": {w["title"]: w["evidence"] for w in weaknesses},
    }


def _normalize_result(raw: dict, jd_requirements: dict = None) -> dict:
    """Từ JSON thô của model -> dict mà pipeline lưu thẳng vào bảng evaluations."""
    dims = _normalize_dimensions(raw.get("dimensions") or raw.get("score_breakdown"))
    coverage = _normalize_coverage(raw.get("requirement_coverage"))

    # Chỉnh cho điểm khớp với bằng chứng TRƯỚC khi tính điểm tổng.
    adjustments = [
        note for note in (
            _reconcile_required_skills(dims, coverage, jd_requirements or {}),
        ) if note
    ]
    score = _weighted_score(dims)

    strengths = _normalize_findings(
        raw.get("strengths"), "impact", "medium", _MAX_STRENGTHS
    )
    weaknesses = _normalize_findings(
        raw.get("weaknesses"), "severity", "medium", _MAX_WEAKNESSES,
        extra_flags=("blocking",),
    )
    risks = _normalize_findings(raw.get("risks"), "severity", "medium", _MAX_RISKS)

    summary = _as_text(raw.get("summary")) or _as_text(raw.get("explanation"))
    seniority = _as_dict(raw.get("seniority"))
    gap = _as_dict(raw.get("experience_gap"))

    details = {
        "verdict": _as_enum(raw.get("verdict"), _VERDICTS, "possible_fit"),
        "confidence": _as_enum(raw.get("confidence"), _LEVELS, "medium"),
        "confidence_reason": _as_text(raw.get("confidence_reason")),
        "summary": summary,
        "seniority": {
            "candidate_level": _as_text(seniority.get("candidate_level")),
            "jd_level": _as_text(seniority.get("jd_level")),
            "note": _as_text(seniority.get("note")),
        },
        "experience_gap": {
            "candidate_years": _as_int(gap.get("candidate_years")),
            "required_years": _as_int(gap.get("required_years")),
            "note": _as_text(gap.get("note")),
        },
        "dimensions": dims,
        "requirement_coverage": coverage,
        "coverage_summary": {
            status: sum(1 for c in coverage if c["status"] == status)
            for status in _COVERAGE_STATUSES
        },
        "strengths": strengths,
        "weaknesses": weaknesses,
        "risks": risks,
        "interview_focus": _normalize_focus(raw.get("interview_focus")),
        # Những chỗ code đã tự sửa điểm của model cho khớp bằng chứng — hiển thị luôn
        # cho HR chứ không sửa lặng lẽ, vì điểm hiện trên màn hình khác điểm AI chấm.
        "adjustments": adjustments,
        # Điểm tổng do code tính; giữ lại con số model tự đưa (nếu có) để đối chiếu
        # khi cần soi lại một đánh giá bất thường.
        "ai_suggested_score": _as_score(raw.get("score")),
        "rubric_version": 2,
    }

    return {
        "score": score,
        "explanation": summary,
        # Giữ 2 key này ở dạng list string cho các luồng cũ (test, process_cv_from_text).
        "strengths": [s["title"] for s in strengths],
        "weaknesses": [w["title"] for w in weaknesses],
        "score_breakdown": {
            spec["legacy"]: d["score"]
            for spec, d in zip(RUBRIC, dims) if d["score"] is not None
        },
        "evidence": _legacy_evidence(strengths, weaknesses),
        "details": details,
    }


def score_cv(candidate_info: dict, jd_requirements: dict, raw_text: str = None) -> dict:
    """
    Chấm điểm ứng viên so với JD: điểm từng trục theo thang điểm cố định, đối chiếu
    từng yêu cầu của JD, điểm mạnh/yếu kèm bằng chứng, rủi ro và gợi ý cần kiểm
    chứng khi phỏng vấn.

    Điểm tổng KHÔNG do model tự chấm mà do code nhân trọng số RUBRIC với điểm từng
    trục — xem `_weighted_score`.

    Kết quả trả về: score, explanation, strengths, weaknesses, score_breakdown,
    evidence (hình dạng cũ) và details (toàn bộ phân tích chi tiết).

    Raises:
        LLMBudgetExhausted: hết quota Groq — để Celery hẹn giờ chấm lại, không đánh
        CV thành FAILED.
    """
    if not candidate_info or candidate_info.get("parse_error"):
        return {"score_error": "Thông tin ứng viên không hợp lệ để chấm điểm."}
    try:
        cv_section = ""
        if EVIDENCE_FROM_CV and raw_text and raw_text.strip():
            cv_section = _CV_SECTION.replace("{cv_text}", raw_text)

        prompt = SCORE_PROMPT.replace(
            "{jd_requirements}",
            # separators gọn (không indent): JSON lồng nhau của JD/CV mà format đẹp
            # thì riêng dấu cách và xuống dòng đã ngốn cả trăm token mỗi lượt gọi.
            json.dumps(jd_requirements, ensure_ascii=False, separators=(",", ":")),
        ).replace(
            "{candidate_info}",
            json.dumps(candidate_info, ensure_ascii=False, separators=(",", ":")),
        ).replace("{cv_section}", cv_section)\
         .replace("{rubric_block}", _rubric_block())\
         .replace("{dimension_count}", str(len(RUBRIC)))\
         .replace("{max_coverage}", str(_MAX_COVERAGE))\
         .replace("{max_strengths}", str(_MAX_STRENGTHS))\
         .replace("{max_weaknesses}", str(_MAX_WEAKNESSES))\
         .replace("{max_risks}", str(_MAX_RISKS))\
         .replace("{max_focus}", str(_MAX_INTERVIEW_FOCUS))

        response_text = clean_json_response(
            generate_text(SCORER_MODEL, prompt, agent_name="cv_scorer")
        )
        raw = json.loads(response_text)
        if not isinstance(raw, dict):
            return {"score_error": "Model không trả về object JSON."}
        return _normalize_result(raw, jd_requirements)
    except LLMBudgetExhausted:
        raise
    except json.JSONDecodeError as e:
        return {"score_error": f"Không parse được JSON từ response: {e}"}
    except Exception as e:
        return {"score_error": f"Lỗi gọi API: {e}"}
