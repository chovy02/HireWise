"""
Các phép chiếu (projection) trên một bản Evaluation.

Cột `details` chứa toàn bộ phân tích chi tiết của lượt chấm điểm (xem
scorer._normalize_result). Không phải chỗ nào cũng cần cả khối đó: Copilot cần bản
gọn để nhồi vào context, bộ sinh câu hỏi phỏng vấn chỉ cần phần thiếu hụt. Gom vào
một module riêng để router và agent_tools dùng chung, thay vì mỗi nơi tự bóc dict.

Mọi hàm ở đây phải chạy được với đánh giá CŨ (details = None): các bản ghi chấm từ
trước khi có cột này không thể backfill, nên đường lùi là bắt buộc, không phải phòng xa.
"""

from app import models


def evaluation_for_agent(ev: models.Evaluation) -> dict:
    """
    Bản GỌN của đánh giá để nhồi vào context của Copilot.

    Không đưa cả cột `details` vào: riêng phần trích dẫn bằng chứng và câu hỏi phỏng
    vấn gợi ý đã dài ngang một CV, mà Copilot thường hỏi về nhiều ứng viên một lượt.
    Ở đây giữ lại đúng thứ dùng để trả lời và so sánh: điểm từng trục kèm lý do,
    những yêu cầu chưa đạt, điểm mạnh/yếu và rủi ro.
    """
    d = ev.details or {}
    coverage = d.get("requirement_coverage") or []
    return {
        "score": ev.score,
        "score_breakdown": ev.score_breakdown,
        "explanation": ev.explanation,
        "evidence": ev.evidence,
        "verdict": d.get("verdict"),
        "confidence": d.get("confidence"),
        "seniority": d.get("seniority"),
        "experience_gap": d.get("experience_gap"),
        "dimensions": [
            {"key": dim.get("key"), "score": dim.get("score"), "comment": dim.get("comment")}
            for dim in (d.get("dimensions") or [])
        ],
        "coverage_summary": d.get("coverage_summary"),
        "requirements_not_met": [
            {"requirement": c.get("requirement"), "status": c.get("status"), "note": c.get("note")}
            for c in coverage
            if c.get("status") in ("missing", "partial")
        ],
        "strengths": [
            {"title": s.get("title"), "detail": s.get("detail"), "impact": s.get("impact")}
            for s in (d.get("strengths") or [])
        ],
        "weaknesses": [
            {"title": w.get("title"), "detail": w.get("detail"),
             "severity": w.get("severity"), "blocking": w.get("blocking")}
            for w in (d.get("weaknesses") or [])
        ],
        "risks": d.get("risks") or [],
    }


def weakness_context(ev: models.Evaluation) -> str:
    """
    Gom điểm yếu + chỗ cần kiểm chứng thành văn bản cho bộ sinh câu hỏi phỏng vấn.

    Trước đây chỗ này truyền `ev.explanation` — bản tóm tắt chung chung, nên câu hỏi
    sinh ra cũng chung chung theo. Giờ đưa đúng từng thiếu hụt kèm mức độ và những
    điểm mà lượt chấm đã đánh dấu "cần kiểm chứng", để câu hỏi bám vào chỗ nghi vấn.
    """
    d = ev.details or {}
    lines = []

    for w in d.get("weaknesses") or []:
        severity = w.get("severity") or "medium"
        detail = f" — {w['detail']}" if w.get("detail") else ""
        lines.append(f"- [{severity}] {w.get('title')}{detail}")

    for f in d.get("interview_focus") or []:
        why = f" (vì: {f['why']})" if f.get("why") else ""
        lines.append(f"- Cần kiểm chứng: {f.get('area')}{why}")

    for c in d.get("requirement_coverage") or []:
        if c.get("status") in ("missing", "partial"):
            lines.append(f"- Yêu cầu JD chưa đạt ({c['status']}): {c.get('requirement')}")

    # Đánh giá cũ (chưa có cột details) thì vẫn dùng phần giải thích như trước.
    return "\n".join(lines) if lines else (ev.explanation or "")
