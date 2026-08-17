"""
Ngân sách thời gian phản hồi (SLO) và bộ đo cho load test HireWise.
==================================================================

VÌ SAO TÁCH RA FILE RIÊNG: bảng thống kê mặc định của Locust chỉ trả lời "chậm bao
nhiêu", không trả lời "như vậy có ĐẠT hay không". Yêu cầu phi chức năng cần một con
số ngưỡng công bố trước, và mỗi lời gọi phải được đối chiếu với đúng ngưỡng của nó.

CÁCH LÀM: mỗi endpoint được xếp vào một NHÓM ĐỘ TRỄ theo việc nó thực sự làm gì,
không phải theo cảm tính. Một lượt gọi vượt ngân sách bị đánh FAIL ngay trong Locust
(nên cột "Failures" phản ánh vi phạm SLO chứ không chỉ lỗi HTTP), đồng thời được ghi
lại để cuối phiên in ra bảng p50/p95/p99 kèm kết luận Đạt / Không đạt.

Ngưỡng đều ghi đè được bằng biến môi trường SLO_<KEY>_MS, ví dụ:
    SLO_LEADERBOARD_MS=1200 locust ...
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from locust import events
from locust.runners import WorkerRunner

# --------------------------------------------------------------------------- #
# Nhóm độ trễ
# --------------------------------------------------------------------------- #
# Ngân sách đặt theo CÔNG VIỆC THẬT mà endpoint phải làm, đo trên p95:
#
#   A · 300ms   — một truy vấn chỉ mục, trả danh sách ngắn. Đây là ngưỡng "cảm giác
#                 tức thì" của người dùng; vượt mốc này là giao diện bắt đầu giật.
#   B · 800ms   — truy vấn gộp nhiều bảng hoặc dựng lại cả bảng xếp hạng trong Python
#                 (leaderboard duyệt skills của từng ứng viên, shortlist sắp lại theo
#                 điểm). Chấp nhận chậm hơn nhóm A vì khối lượng tăng theo số ứng viên.
#   C · 1000ms  — có ghi và commit xuống Postgres.
#   D · 1200ms  — đăng nhập. CỐ Ý rộng: bcrypt (12 vòng) tốn ~250-350ms CPU cho MỖI lần
#                 đối chiếu mật khẩu, và đó là tính năng bảo mật chứ không phải lỗi
#                 hiệu năng. Đặt ngưỡng 300ms ở đây là tự bắt mình phải hạ số vòng băm.
#   E · 5000ms  — POST ZIP CV. Chỉ đo PHA ĐỒNG BỘ (giải nén + PyMuPDF trích text +
#                 tạo bản ghi PENDING); phần chấm điểm AI do worker làm nền nên KHÔNG
#                 nằm trong con số này.
#   F · 30000ms — có gọi LLM qua mạng, còn phải xếp hàng chờ ngân sách token Groq.
#                 Không thể áp ngưỡng giao diện lên nhóm này; điều đáng kiểm là nó có
#                 nằm trong giới hạn kiên nhẫn (và trong TURN_BUDGET=75s của agent) hay
#                 không.
GROUPS = {
    "A": ("A · tra cứu tức thời", 300),
    "B": ("B · truy vấn tổng hợp", 800),
    "C": ("C · ghi dữ liệu", 1000),
    "D": ("D · xác thực (bcrypt)", 1200),
    "E": ("E · nạp tệp — pha đồng bộ", 5000),
    "F": ("F · có gọi LLM", 30000),
}


@dataclass(frozen=True)
class SLO:
    key: str
    label: str  # tên gộp hiển thị trong Locust — PHẢI là mẫu, không chứa UUID thật
    group: str
    note: str = ""

    @property
    def budget_ms(self) -> int:
        """Ngân sách p95, ưu tiên biến môi trường SLO_<KEY>_MS."""
        raw = os.getenv(f"SLO_{self.key.upper()}_MS")
        if raw:
            try:
                return int(raw)
            except ValueError:
                pass
        return GROUPS[self.group][1]

    @property
    def group_label(self) -> str:
        return GROUPS[self.group][0]


def _s(key: str, label: str, group: str, note: str = "") -> SLO:
    return SLO(key=key, label=label, group=group, note=note)


# --------------------------------------------------------------------------- #
# Danh mục SLO — một dòng cho mỗi endpoint được đo
# --------------------------------------------------------------------------- #
SLOS: dict[str, SLO] = {
    s.key: s
    for s in [
        # ── D: xác thực ───────────────────────────────────────────────────────
        _s("login", "POST /auth/login", "D", "bcrypt 12 vòng nằm trong đường đi"),
        _s("me", "GET /auth/me", "A", "giải mã JWT + 1 truy vấn theo email"),
        # ── A: tra cứu tức thời ───────────────────────────────────────────────
        _s("jd_list", "GET /jds", "A", "danh sách dự án + đếm ứng viên gộp 1 query"),
        _s("jd_detail", "GET /jds/{id}", "A"),
        _s("jd_trash", "GET /jds/trash", "A"),
        _s("uploads", "GET /jds/{id}/uploads", "A"),
        _s("shortlist_list", "GET /jds/{id}/shortlists", "A"),
        _s("notifications", "GET /notifications", "A", "chuông thông báo, gọi mỗi lần đổi trang"),
        _s("chat_sessions", "GET /agent/sessions", "A"),
        _s("email_templates", "GET /email-templates", "A"),
        # ── B: truy vấn tổng hợp ──────────────────────────────────────────────
        _s("leaderboard", "GET /jds/{id}/candidates", "B", "giao diện POLL endpoint này khi đang upload"),
        _s("shortlist_detail", "GET /shortlists/{id}", "B"),
        _s("candidate_detail", "GET /candidates/{id}", "B", "kèm raw_text CV + đánh giá chi tiết"),
        _s("interview_get", "GET /interviews/candidate/{id}", "B", "404 khi chưa có buổi PV là hợp lệ"),
        _s("admin_ai_metrics", "GET /admin/ai-metrics", "B"),
        _s("admin_business", "GET /admin/business-metrics", "B"),
        _s("admin_sys_logs", "GET /admin/system-logs", "B"),
        _s("admin_audit_logs", "GET /admin/audit-logs", "B"),
        _s("admin_ai_logs", "GET /admin/ai-logs", "B"),
        _s("admin_users", "GET /users", "B"),
        # ── C: ghi dữ liệu ────────────────────────────────────────────────────
        _s("shortlist_create", "POST /jds/{id}/shortlists", "C"),
        _s("shortlist_add_item", "POST /shortlists/{id}/items", "C"),
        _s("shortlist_set_status", "PATCH /shortlists/{id}/items/{item}", "C", "HR chốt nhận/loại"),
        _s("shortlist_del_item", "DELETE /shortlists/{id}/items/{item}", "C"),
        _s("shortlist_delete", "DELETE /shortlists/{id}", "C"),
        _s("eval_override", "PATCH /evaluations/{id}/override", "C", "chỉ chạy khi bật tag mutate"),
        # ── E: nạp tệp ────────────────────────────────────────────────────────
        _s("cv_upload", "POST /jds/{id}/cvs", "E", "chỉ đo pha đồng bộ, không chờ worker"),
        # ── F: có gọi LLM ─────────────────────────────────────────────────────
        _s("jd_create", "POST /jds", "F", "Groq chuẩn hoá JD"),
        _s("agent_chat", "POST /agent/chat", "F", "agent loop: LLM + tool qua MCP"),
        _s("compare", "POST /compare", "F", "so sánh 2 ứng viên bằng LLM"),
        _s("interview_generate", "POST /interviews/candidate/{id}/generate", "F"),
        _s("interview_evaluate", "POST /interviews/question/{id}/evaluate", "F"),
    ]
}


# --------------------------------------------------------------------------- #
# Thu thập mẫu đo
# --------------------------------------------------------------------------- #
SAMPLES: dict[str, list[float]] = defaultdict(list)
HTTP_ERRORS: dict[str, int] = defaultdict(int)

# Tỉ lệ lỗi HTTP tối đa còn coi là đạt. Mặc định 0: một endpoint đọc mà trả lỗi thì
# con số độ trễ của nó không còn ý nghĩa gì để mà đánh giá.
MAX_ERROR_RATE = float(os.getenv("SLO_MAX_ERROR_RATE", "0"))


def timed(client, key: str, method: str, url: str, expect=(200,), **kwargs):
    """Gửi 1 request, đo thời gian và đối chiếu với ngân sách của `key`.

    Trả về đối tượng response (đã thoát khỏi context manager nên vẫn đọc được
    .json() / .status_code như bình thường).

    Đặt `name` theo nhãn mẫu trong danh mục SLO — KHÔNG dùng URL thật, nếu không mỗi
    UUID sẽ thành một dòng riêng trong bảng Locust và không gộp được thống kê.
    """
    slo = SLOS[key]
    kwargs.setdefault("name", slo.label)
    if method.upper() in ("GET", "DELETE"):
        kwargs.setdefault("timeout", 30)
    else:
        # Nhóm F chờ LLM: 30s là quá ngắn, agent còn có ngân sách lượt tới 75s.
        kwargs.setdefault("timeout", 150 if slo.group == "F" else 60)

    started = time.perf_counter()
    with client.request(method, url, catch_response=True, **kwargs) as resp:
        elapsed_ms = (time.perf_counter() - started) * 1000
        SAMPLES[key].append(elapsed_ms)

        if resp.status_code not in expect:
            HTTP_ERRORS[key] += 1
            body = (resp.text or "")[:180]
            resp.failure(f"HTTP {resp.status_code} (mong đợi {expect}) — {body}")
        elif elapsed_ms > slo.budget_ms:
            resp.failure(f"VƯỢT SLO: {elapsed_ms:.0f}ms > {slo.budget_ms}ms")
        else:
            resp.success()
    return resp


# --------------------------------------------------------------------------- #
# Thống kê
# --------------------------------------------------------------------------- #
def percentile(values: list[float], q: float) -> float:
    """Phân vị theo hạng gần nhất (nearest-rank) — cùng cách Locust tính."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round(q / 100.0 * len(ordered) + 0.5)) - 1
    return ordered[max(0, min(idx, len(ordered) - 1))]


def build_report() -> dict:
    rows = []
    for key, slo in SLOS.items():
        samples = SAMPLES.get(key, [])
        errors = HTTP_ERRORS.get(key, 0)
        count = len(samples)
        if count == 0:
            rows.append({
                "key": key, "endpoint": slo.label, "group": slo.group,
                "group_label": slo.group_label, "budget_ms": slo.budget_ms,
                "count": 0, "verdict": "KHÔNG CHẠY", "note": slo.note,
            })
            continue

        p95 = percentile(samples, 95)
        error_rate = errors / count
        breaches = sum(1 for v in samples if v > slo.budget_ms)
        ok = p95 <= slo.budget_ms and error_rate <= MAX_ERROR_RATE
        rows.append({
            "key": key,
            "endpoint": slo.label,
            "group": slo.group,
            "group_label": slo.group_label,
            "budget_ms": slo.budget_ms,
            "count": count,
            "http_errors": errors,
            "error_rate": round(error_rate * 100, 2),
            "breaches": breaches,
            "breach_rate": round(breaches / count * 100, 2),
            "min_ms": round(min(samples)),
            "p50_ms": round(percentile(samples, 50)),
            "p95_ms": round(p95),
            "p99_ms": round(percentile(samples, 99)),
            "max_ms": round(max(samples)),
            "verdict": "ĐẠT" if ok else "KHÔNG ĐẠT",
            "note": slo.note,
        })

    rows.sort(key=lambda r: (r["group"], r["endpoint"]))
    measured = [r for r in rows if r["count"] > 0]
    failed = [r for r in measured if r["verdict"] == "KHÔNG ĐẠT"]
    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "max_error_rate_pct": MAX_ERROR_RATE * 100,
        "summary": {
            "endpoints_measured": len(measured),
            "endpoints_not_run": len(rows) - len(measured),
            "endpoints_passed": len(measured) - len(failed),
            "endpoints_failed": len(failed),
            "overall": "ĐẠT" if measured and not failed else ("KHÔNG ĐẠT" if failed else "KHÔNG CÓ DỮ LIỆU"),
        },
        "rows": rows,
    }


# --------------------------------------------------------------------------- #
# Kết xuất
# --------------------------------------------------------------------------- #
_H = ["Endpoint", "n", "p50", "p95", "p99", "max", "Ngân sách", "Lỗi%", "Kết luận"]
_W = [42, 6, 7, 7, 7, 7, 10, 6, 11]


def _line(cells, widths=_W) -> str:
    out = []
    for cell, width in zip(cells, widths):
        text = str(cell)
        if len(text) > width:
            text = text[: width - 1] + "…"
        out.append(text.ljust(width) if cell is cells[0] else text.rjust(width))
    return "  ".join(out)


def render_text(report: dict) -> str:
    lines = [
        "",
        "═" * 108,
        "  BÁO CÁO SLO THỜI GIAN PHẢN HỒI — HireWise",
        f"  Sinh lúc {report['generated_at']} · đơn vị mili-giây · kết luận dựa trên p95",
        "═" * 108,
        _line(_H),
        "─" * 108,
    ]
    current_group = None
    for row in report["rows"]:
        if row["count"] == 0:
            continue
        if row["group"] != current_group:
            current_group = row["group"]
            lines.append("")
            lines.append(f"  ▸ {row['group_label']}  (ngân sách nhóm: {GROUPS[row['group']][1]} ms)")
        lines.append(_line([
            row["endpoint"], row["count"], row["p50_ms"], row["p95_ms"], row["p99_ms"],
            row["max_ms"], row["budget_ms"], row["error_rate"], row["verdict"],
        ]))

    skipped = [r for r in report["rows"] if r["count"] == 0]
    if skipped:
        lines += ["", "  ▸ Không có mẫu đo trong phiên này:"]
        lines += [f"      · {r['endpoint']}" for r in skipped]

    s = report["summary"]
    lines += [
        "",
        "─" * 108,
        f"  Đã đo {s['endpoints_measured']} endpoint · "
        f"đạt {s['endpoints_passed']} · không đạt {s['endpoints_failed']} · "
        f"chưa chạy {s['endpoints_not_run']}",
        f"  KẾT LUẬN CHUNG: {s['overall']}",
        "═" * 108,
        "",
    ]
    return "\n".join(lines)


def render_markdown(report: dict) -> str:
    s = report["summary"]
    out = [
        "# Báo cáo SLO thời gian phản hồi — HireWise",
        "",
        f"*Sinh lúc {report['generated_at']}. Mọi con số tính bằng mili-giây; "
        "kết luận dựa trên phân vị 95.*",
        "",
        f"**Kết luận chung: {s['overall']}** — đo {s['endpoints_measured']} endpoint, "
        f"đạt {s['endpoints_passed']}, không đạt {s['endpoints_failed']}.",
        "",
    ]
    current_group = None
    for row in report["rows"]:
        if row["count"] == 0:
            continue
        if row["group"] != current_group:
            current_group = row["group"]
            out += [
                "",
                f"## {row['group_label']}",
                "",
                "| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|",
            ]
        out.append(
            f"| `{row['endpoint']}` | {row['count']} | {row['p50_ms']} | {row['p95_ms']} | "
            f"{row['p99_ms']} | {row['max_ms']} | {row['budget_ms']} | "
            f"{row['breach_rate']}% | {row['error_rate']}% | {row['verdict']} |"
        )

    notes = [r for r in report["rows"] if r["count"] and r["note"]]
    if notes:
        out += ["", "## Ghi chú", ""]
        out += [f"- `{r['endpoint']}` — {r['note']}" for r in notes]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# Móc vào vòng đời Locust
# --------------------------------------------------------------------------- #
@events.report_to_master.add_listener
def _gui_mau_ve_master(client_id, data):
    """Chạy phân tán: worker gom mẫu đo rồi đẩy về master mỗi chu kỳ báo cáo."""
    data["slo_samples"] = {k: v for k, v in SAMPLES.items() if v}
    data["slo_http_errors"] = dict(HTTP_ERRORS)
    SAMPLES.clear()
    HTTP_ERRORS.clear()


@events.worker_report.add_listener
def _nhan_mau_tu_worker(client_id, data):
    for key, values in (data.get("slo_samples") or {}).items():
        SAMPLES[key].extend(values)
    for key, count in (data.get("slo_http_errors") or {}).items():
        HTTP_ERRORS[key] += count


@events.test_stop.add_listener
def _in_bao_cao(environment, **_kwargs):
    # Worker không có bức tranh đầy đủ — chỉ master (hoặc chạy một tiến trình) mới in.
    if isinstance(environment.runner, WorkerRunner):
        return

    report = build_report()
    print(render_text(report))

    out_dir = Path(os.getenv("LOAD_REPORT_DIR", "load-report"))
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "slo-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / "slo-report.md").write_text(render_markdown(report), encoding="utf-8")
        print(f"  Đã ghi báo cáo vào {out_dir.resolve()}\\slo-report.md (và .json)\n")
    except OSError as e:
        print(f"  Không ghi được báo cáo ra đĩa: {e}\n")

    # Mã thoát khác 0 khi có endpoint không đạt -> cắm thẳng vào CI được.
    if report["summary"]["overall"] == "KHÔNG ĐẠT":
        environment.process_exit_code = 1
