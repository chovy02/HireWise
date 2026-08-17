"""
Load test HireWise — kiểm chứng yêu cầu phi chức năng về THỜI GIAN PHẢN HỒI.
===========================================================================

Chạy nhanh (hồ sơ mặc định, KHÔNG tốn quota AI):

    cd src/backend/tests/load
    pip install -r requirements-load.txt
    set LOAD_HR_EMAIL=hr@example.com
    set LOAD_HR_PASSWORD=matkhau
    locust -f locustfile.py --host http://localhost:8000 --headless -u 20 -r 5 -t 3m

Ngưỡng đạt/không đạt nằm trong `slo.py`; cuối phiên bộ đo tự in bảng p50/p95/p99 và
ghi `load-report/slo-report.md`.

BỐN HỒ SƠ TẢI (`--profile`), TÁCH RA CÓ CHỦ ĐÍCH
------------------------------------------------
`read`  (MẶC ĐỊNH — dùng cho hầu hết phép đo)
    Các đường đọc, cộng thêm những thao tác ghi TỰ DỌN được. Phản ánh đúng trải
    nghiệm hằng ngày của HR: mở dự án, xem bảng xếp hạng, mở shortlist.

`write` (thêm thao tác ghi để lại dấu vết)
    Bật thêm việc HR chỉnh điểm ứng viên. SỬA DỮ LIỆU THẬT, không tự hoàn tác —
    chỉ chạy trên môi trường thử nghiệm.

`ai`    (đường có gọi LLM)
    MỖI LƯỢT LÀ MỘT LẦN TIÊU QUOTA GROQ THẬT. Hạn mức free tier tính theo token/phút
    và token/ngày, nên bắn 20 người dùng đồng thời vào đây không đo ra "hệ thống chậm
    bao nhiêu" mà chỉ đo ra "hàng đợi rate limiter dài bao nhiêu" — và đốt sạch quota
    của cả ngày làm việc. Chạy hồ sơ này với 1-2 người dùng, thời gian ngắn, và đọc
    con số như một phép đo THAM KHẢO chứ không phải chỉ tiêu giao diện.

`all`   (mọi hồ sơ cùng lúc — hiếm khi là thứ bạn muốn)

VÌ SAO CHỌN HỒ SƠ BẰNG `--profile` CHỨ KHÔNG PHẢI `--tags` CỦA LOCUST: cơ chế tag chỉ
lọc TASK chứ không loại LỚP người dùng. Khi mọi task của một lớp bị lọc hết, Locust
vẫn sinh ra người dùng của lớp đó rồi ném "No tasks defined on ..." giữa phiên đo —
đã gặp thật. `--profile` quyết định ngay từ đầu lớp nào được đưa vào phiên chạy.

DỮ LIỆU CẦN CÓ TRƯỚC
--------------------
Mọi endpoint nghiệp vụ đều lọc theo chủ sở hữu, nên tài khoản dùng để test PHẢI có
sẵn ít nhất một dự án đã nạp CV và chấm xong. Dùng chính tài khoản HR đang có dữ liệu
thật; `seed.py` chỉ dùng để tạo tài khoản khi cần.
"""

from __future__ import annotations

import io
import os
import random
import zipfile

from locust import HttpUser, between, events, task
from locust.exception import StopUser

from slo import SLOS, timed

PROFILES = {
    "read": "đường đọc + ghi tự dọn — an toàn, không tốn quota AI",
    "write": "read + thao tác ghi để lại dấu vết (chỉnh điểm, tạo JD)",
    "ai": "chỉ các đường có gọi LLM — TIÊU QUOTA GROQ THẬT",
    "all": "tất cả các hồ sơ trên",
}

# --------------------------------------------------------------------------- #
# Cấu hình
# --------------------------------------------------------------------------- #
try:  # tiện lợi khi chạy tay: đọc luôn .env ở gốc dự án nếu có python-dotenv
    from dotenv import load_dotenv

    for _up in (".env", "../.env", "../../.env", "../../../.env", "../../../../.env"):
        if os.path.exists(_up):
            load_dotenv(_up, override=False)
            break
except ImportError:
    pass

HR_EMAIL = os.getenv("LOAD_HR_EMAIL", "")
HR_PASSWORD = os.getenv("LOAD_HR_PASSWORD", "")
ADMIN_EMAIL = os.getenv("LOAD_ADMIN_EMAIL") or os.getenv("DEFAULT_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("LOAD_ADMIN_PASSWORD") or os.getenv("DEFAULT_ADMIN_PASSWORD", "")

# Ghim sẵn một dự án thay vì để mỗi người dùng tự dò (đo ổn định hơn khi so sánh
# giữa các lần chạy).
PINNED_JD_ID = os.getenv("LOAD_JD_ID", "")
# ZIP CV thật để đo đường nạp tệp. Bỏ trống -> tự sinh ZIP tổng hợp (xem _zip_cv_gia).
CV_ZIP_PATH = os.getenv("LOAD_CV_ZIP", "")
CV_ZIP_COUNT = int(os.getenv("LOAD_CV_COUNT", "5"))


# Hồ sơ đang chạy và cờ cho phép ghi dữ liệu không hoàn tác được. Cả hai được chốt
# một lần trong sự kiện `init` rồi các task chỉ việc đọc.
ACTIVE_PROFILE = "read"
ALLOW_MUTATION = False


@events.init_command_line_parser.add_listener
def _them_tham_so(parser):
    # TÊN PHẢI LÀ `--load-profile`: Locust 2.4x đã dùng `--profile` cho việc xuất hồ sơ
    # hiệu năng của chính nó, đăng ký trùng tên thì argparse ném ArgumentError và tham
    # số của ta bị bỏ qua trong im lặng (hồ sơ luôn rơi về mặc định mà không ai biết).
    parser.add_argument(
        "--load-profile",
        dest="load_profile",
        default=os.getenv("LOAD_PROFILE", "read"),
        choices=list(PROFILES),
        help="Hồ sơ tải: " + " · ".join(f"{k} = {v}" for k, v in PROFILES.items()),
    )


@events.init.add_listener
def _chon_ho_so(environment, **_kw):
    """Loại thẳng những lớp không thuộc hồ sơ ra khỏi phiên chạy.

    Phải làm ở `init` (trước khi runner được dựng), chứ không phải bằng `--tags`:
    tag chỉ lọc task, lớp vẫn được sinh ra rồi chết vì không còn task nào.
    """
    global ACTIVE_PROFILE, ALLOW_MUTATION

    ACTIVE_PROFILE = getattr(environment.parsed_options, "load_profile", None) or "read"
    ALLOW_MUTATION = ACTIVE_PROFILE in ("write", "all")

    giu, bo = [], []
    for uc in environment.user_classes:
        if ACTIVE_PROFILE not in getattr(uc, "profiles", frozenset()):
            bo.append(f"{uc.__name__} (ngoài hồ sơ)")
        elif getattr(uc, "need_admin", False) and not (ADMIN_EMAIL and ADMIN_PASSWORD):
            # Không có thông tin admin thì lớp này chỉ tạo ra một tràng lỗi đăng nhập.
            bo.append(f"{uc.__name__} (thiếu LOAD_ADMIN_EMAIL/PASSWORD)")
        else:
            giu.append(uc)
    environment.user_classes = giu

    print("\n" + "─" * 78)
    print("  LOAD TEST HireWise — đo thời gian phản hồi")
    print(f"  Hồ sơ       : {ACTIVE_PROFILE} — {PROFILES[ACTIVE_PROFILE]}")
    print(f"  Host        : {environment.host or '(đặt bằng --host)'}")
    print(f"  Tài khoản HR: {HR_EMAIL or '(CHƯA ĐẶT LOAD_HR_EMAIL)'}")
    print(f"  Dự án ghim  : {PINNED_JD_ID or '(tự dò từ GET /jds)'}")
    print(f"  Lớp chạy    : {', '.join(uc.__name__ for uc in giu) or '(KHÔNG CÓ LỚP NÀO)'}")
    if bo:
        print(f"  Đã loại     : {', '.join(bo)}")
    print(f"  Ngân sách   : {len(SLOS)} endpoint có SLO — chi tiết trong slo.py")
    print("─" * 78 + "\n")


# --------------------------------------------------------------------------- #
# Lớp nền: đăng nhập + dò dữ liệu
# --------------------------------------------------------------------------- #
class ApiUser(HttpUser):
    """Đăng nhập một lần lúc khởi động rồi giữ token suốt phiên — đúng như SPA làm."""

    abstract = True
    email = ""
    password = ""

    def on_start(self):
        if not self.email or not self.password:
            print(
                f"[{type(self).__name__}] Thiếu thông tin đăng nhập. "
                "Đặt LOAD_HR_EMAIL / LOAD_HR_PASSWORD (và LOAD_ADMIN_* nếu chạy nhóm giám sát)."
            )
            raise StopUser()

        resp = timed(
            self.client, "login", "POST", "/auth/login",
            json={"email": self.email, "password": self.password},
        )
        if resp.status_code != 200:
            print(f"[{type(self).__name__}] Đăng nhập thất bại cho {self.email}: {resp.text[:200]}")
            raise StopUser()

        self.client.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
        timed(self.client, "me", "GET", "/auth/me")
        self.after_login()

    def after_login(self):
        """Nơi lớp con dò các id cần dùng."""


class HRUser(ApiUser):
    """Nền chung cho mọi hồ sơ tải chạy dưới vai HR."""

    abstract = True
    email = HR_EMAIL
    password = HR_PASSWORD

    def after_login(self):
        self.jd_id: str | None = None
        self.candidate_ids: list[str] = []
        self.scored_candidate_ids: list[str] = []
        self.evaluation_ids: list[str] = []
        self.shortlist_ids: list[str] = []
        self.discover()

    def discover(self):
        """Dò một dự án có dữ liệu để các task sau có thứ mà gọi.

        Bản thân các lời gọi ở đây CŨNG là endpoint thật của giao diện (SPA nạp
        đúng chuỗi này khi HR mở dashboard rồi bấm vào một dự án), nên chúng được
        tính vào thống kê chứ không phải chi phí phụ của phép đo.
        """
        resp = timed(self.client, "jd_list", "GET", "/jds")
        if resp.status_code != 200:
            raise StopUser()

        jds = resp.json()
        if PINNED_JD_ID:
            self.jd_id = PINNED_JD_ID
        elif jds:
            # Ưu tiên dự án NHIỀU ứng viên nhất: đó là trường hợp xấu nhất của
            # leaderboard, và cũng là thứ đáng đặt ngưỡng nhất.
            self.jd_id = max(jds, key=lambda j: j.get("candidate_count", 0))["id"]

        if not self.jd_id:
            print(
                f"[HR] Tài khoản {self.email} chưa có dự án nào. Load test cần sẵn dữ "
                "liệu (dự án + CV đã chấm). Xem phần 'Dữ liệu cần có trước' trong README."
            )
            raise StopUser()

        resp = timed(self.client, "leaderboard", "GET", f"/jds/{self.jd_id}/candidates")
        if resp.status_code == 200:
            rows = resp.json()
            self.candidate_ids = [c["id"] for c in rows]
            self.scored_candidate_ids = [
                c["id"] for c in rows if c.get("status") == "COMPLETED" and c.get("score") is not None
            ]

        resp = timed(self.client, "shortlist_list", "GET", f"/jds/{self.jd_id}/shortlists")
        if resp.status_code == 200:
            self.shortlist_ids = [s["id"] for s in resp.json()]

    # -- tiện ích --------------------------------------------------------- #
    def a_candidate(self) -> str | None:
        return random.choice(self.candidate_ids) if self.candidate_ids else None

    def a_scored_candidate(self) -> str | None:
        return random.choice(self.scored_candidate_ids) if self.scored_candidate_ids else None


# --------------------------------------------------------------------------- #
# Hồ sơ 1 — HR duyệt màn hình (tải chủ đạo, chỉ đọc)
# --------------------------------------------------------------------------- #
class HRBrowsingUser(HRUser):
    """Mô phỏng thao tác thường ngày của HR.

    Trọng số task lấy theo tần suất thật trên giao diện: bảng xếp hạng được POLL liên
    tục trong lúc worker chấm CV, nên nó là endpoint bị gọi nhiều nhất — và cũng là
    endpoint nặng nhất trong nhóm chỉ-đọc.
    """

    profiles = frozenset({"read", "write", "all"})
    weight = 10
    wait_time = between(1, 4)

    @task(10)
    def poll_bang_xep_hang(self):
        """Giao diện tự nạp lại danh sách ứng viên khi có CV đang được chấm."""
        timed(self.client, "leaderboard", "GET", f"/jds/{self.jd_id}/candidates")

    @task(6)
    def mo_dashboard(self):
        timed(self.client, "jd_list", "GET", "/jds")
        timed(self.client, "notifications", "GET", "/notifications")

    @task(6)
    def mo_du_an(self):
        timed(self.client, "jd_detail", "GET", f"/jds/{self.jd_id}")
        timed(self.client, "leaderboard", "GET", f"/jds/{self.jd_id}/candidates")

    @task(5)
    def mo_ho_so_ung_vien(self):
        cid = self.a_candidate()
        if not cid:
            return
        timed(self.client, "candidate_detail", "GET", f"/candidates/{cid}")
        # 404 = ứng viên chưa có buổi phỏng vấn. Đó là trạng thái BÌNH THƯỜNG, không
        # phải lỗi — tính vào lỗi thì tỉ lệ lỗi sẽ báo động giả suốt phiên đo.
        timed(
            self.client, "interview_get", "GET", f"/interviews/candidate/{cid}",
            expect=(200, 404),
        )

    @task(4)
    def mo_shortlist(self):
        resp = timed(self.client, "shortlist_list", "GET", f"/jds/{self.jd_id}/shortlists")
        if resp.status_code != 200:
            return
        rows = resp.json()
        if rows:
            timed(self.client, "shortlist_detail", "GET", f"/shortlists/{random.choice(rows)['id']}")

    @task(2)
    def xem_lich_su_tai_len(self):
        timed(self.client, "uploads", "GET", f"/jds/{self.jd_id}/uploads")

    @task(2)
    def mo_lich_su_chat(self):
        timed(self.client, "chat_sessions", "GET", "/agent/sessions")

    @task(1)
    def mo_thung_rac(self):
        timed(self.client, "jd_trash", "GET", "/jds/trash")

    @task(1)
    def mo_mau_mail(self):
        timed(self.client, "email_templates", "GET", "/email-templates")


# --------------------------------------------------------------------------- #
# Hồ sơ 2 — HR thao tác shortlist (ghi, tự dọn sạch)
# --------------------------------------------------------------------------- #
class HRShortlistUser(HRUser):
    """Đo đường GHI: tạo shortlist → thêm ứng viên → chốt quyết định → dọn sạch.

    TỰ DỌN LÀ BẮT BUỘC: tên shortlist có unique index theo (jd_id, tên), nên nếu để
    lại rác thì lần chạy thứ hai sẽ ăn 409 hàng loạt và toàn bộ phép đo hỏng. Tên gắn
    kèm số ngẫu nhiên cũng vì lý do đó — nhiều người dùng ảo chạy song song.
    """

    profiles = frozenset({"read", "write", "all"})
    weight = 2
    wait_time = between(2, 6)

    @task
    def vong_doi_shortlist(self):
        ten = f"loadtest-{random.randint(10**6, 10**7 - 1)}"
        resp = timed(
            self.client, "shortlist_create", "POST", f"/jds/{self.jd_id}/shortlists",
            json={"name": ten}, expect=(201,),
        )
        if resp.status_code != 201:
            return
        shortlist_id = resp.json()["id"]

        try:
            cid = self.a_candidate()
            if not cid:
                return
            resp = timed(
                self.client, "shortlist_add_item", "POST", f"/shortlists/{shortlist_id}/items",
                json={"candidate_id": cid}, expect=(201, 409),
            )
            if resp.status_code != 201:
                return
            item_id = resp.json()["id"]

            timed(
                self.client, "shortlist_set_status", "PATCH",
                f"/shortlists/{shortlist_id}/items/{item_id}",
                json={"candidate_status": random.choice(["accepted", "rejected", "pending"])},
            )
            timed(self.client, "shortlist_detail", "GET", f"/shortlists/{shortlist_id}")
            timed(
                self.client, "shortlist_del_item", "DELETE",
                f"/shortlists/{shortlist_id}/items/{item_id}", expect=(204,),
            )
        finally:
            # Chạy cả khi có bước giữa chừng hỏng — không được để lại shortlist rác.
            timed(
                self.client, "shortlist_delete", "DELETE", f"/shortlists/{shortlist_id}",
                expect=(204,),
            )

    @task
    def chinh_diem_ung_vien(self):
        """HR ghi đè điểm AI chấm. ĐỔI DỮ LIỆU THẬT và không tự hoàn tác được —
        vì vậy chỉ chạy ở hồ sơ `write` / `all`."""
        if not ALLOW_MUTATION:
            return
        cid = self.a_scored_candidate()
        if not cid:
            return
        resp = timed(self.client, "candidate_detail", "GET", f"/candidates/{cid}")
        if resp.status_code != 200:
            return
        evaluation = (resp.json() or {}).get("evaluation") or {}
        if not evaluation.get("id"):
            return

        timed(
            self.client, "eval_override", "PATCH",
            f"/evaluations/{evaluation['id']}/override",
            json={
                "new_score": round(random.uniform(40, 95), 1),
                "reason": "Điều chỉnh tự động trong phiên load test.",
            },
        )


# --------------------------------------------------------------------------- #
# Hồ sơ 3 — Admin xem bảng giám sát
# --------------------------------------------------------------------------- #
class AdminMonitoringUser(ApiUser):
    """Trang Admin Gateway nạp nhiều bảng tổng hợp cùng lúc — đây là nhóm truy vấn
    quét toàn bảng log, và là chỗ dễ chậm dần theo thời gian sử dụng nhất."""

    profiles = frozenset({"read", "write", "all"})
    need_admin = True
    weight = 1
    wait_time = between(3, 8)
    email = ADMIN_EMAIL
    password = ADMIN_PASSWORD

    @task(3)
    def bang_dieu_khien_giam_sat(self):
        timed(self.client, "admin_ai_metrics", "GET", "/admin/ai-metrics")
        timed(self.client, "admin_business", "GET", "/admin/business-metrics")

    @task(2)
    def xem_nhat_ky(self):
        timed(self.client, "admin_sys_logs", "GET", "/admin/system-logs")
        timed(self.client, "admin_ai_logs", "GET", "/admin/ai-logs")

    @task(1)
    def xem_kiem_toan(self):
        timed(self.client, "admin_audit_logs", "GET", "/admin/audit-logs")

    @task(1)
    def quan_ly_tai_khoan(self):
        timed(self.client, "admin_users", "GET", "/users")
        timed(self.client, "notifications", "GET", "/notifications")


# --------------------------------------------------------------------------- #
# Hồ sơ 4 — đường có gọi LLM (mặc định KHÔNG chạy)
# --------------------------------------------------------------------------- #
def _pdf_toi_thieu(dong: list[str]) -> bytes:
    """Dựng một PDF hợp lệ tối thiểu có text trích được bằng PyMuPDF.

    Tự dựng thay vì kèm sẵn file mẫu: CV thật là dữ liệu cá nhân, không nên nằm trong
    kho mã nguồn. Bảng xref được tính offset đúng để PyMuPDF không phải chạy chế độ
    sửa lỗi — nếu không, thời gian đo được sẽ nhiễu bởi chính bước sửa lỗi đó.
    """
    def esc(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    noi_dung = "BT /F1 11 Tf 1 0 0 1 56 780 Tm 14 TL\n"
    noi_dung += "".join(f"({esc(d)}) Tj T*\n" for d in dong)
    noi_dung += "ET"
    sb = noi_dung.encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(sb)).encode() + b" >>\nstream\n" + sb + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    total = len(objects) + 1
    out += f"xref\n0 {total}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {total} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


def _zip_cv_gia(so_luong: int) -> bytes:
    """ZIP nhiều CV tổng hợp. Mỗi CV có nội dung khác nhau -> khác SHA-256, nên không
    bị chặn bởi cơ chế chống trùng của `stage_cvs`."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(so_luong):
            dau = random.randint(10**8, 10**9 - 1)
            zf.writestr(
                f"cv_loadtest_{dau}.pdf",
                _pdf_toi_thieu([
                    f"Nguyen Van Loadtest {dau}",
                    f"Email: loadtest{dau}@example.com",
                    "Dien thoai: 0900000000",
                    "",
                    "KINH NGHIEM",
                    "- 3 nam phat trien phan mem voi Python va FastAPI",
                    "- Xay dung he thong xu ly du lieu tren PostgreSQL va Redis",
                    "",
                    "KY NANG",
                    "- Python, FastAPI, SQLAlchemy, Docker, Celery",
                    "- React, JavaScript, Tailwind CSS",
                    "",
                    "HOC VAN",
                    "- Ky su Cong nghe thong tin",
                ]),
            )
    return buf.getvalue()


class AILatencyUser(HRUser):
    """Đo các đường có gọi LLM. CHỈ chạy với `--profile ai` (hoặc `all`).

    ĐỌC KỸ TRƯỚC KHI CHẠY: mỗi task ở đây tiêu quota Groq thật. `wait_time` để rất
    rộng và trọng số để thấp là có chủ đích — mục tiêu là lấy vài chục mẫu đại diện,
    không phải tạo tải. Muốn biết hệ thống chịu được bao nhiêu người dùng đồng thời
    thì đo bằng ba hồ sơ phía trên; nhóm này bị chặn bởi hạn mức của nhà cung cấp
    chứ không phải bởi năng lực của HireWise.
    """

    profiles = frozenset({"ai", "all"})
    weight = 1
    wait_time = between(20, 45)

    @task(3)
    def hoi_copilot(self):
        """Câu hỏi CHỈ ĐỌC — cố ý không nhờ agent tạo/xoá gì, để hồ sơ `ai` vẫn an
        toàn chạy trên môi trường có dữ liệu thật."""
        cau_hoi = random.choice([
            "Liệt kê các vị trí tuyển dụng của tôi.",
            "Top 3 ứng viên điểm cao nhất của dự án này là ai?",
            "Dự án này đang có bao nhiêu ứng viên đã chấm xong?",
            "Cho tôi xem các danh sách rút gọn hiện có.",
        ])
        timed(
            self.client, "agent_chat", "POST", "/agent/chat",
            json={"message": cau_hoi, "context": {"page": "project", "jd_id": self.jd_id}},
        )

    @task(2)
    def so_sanh_ung_vien(self):
        if len(self.scored_candidate_ids) < 2:
            return
        cap = random.sample(self.scored_candidate_ids, 2)
        timed(
            self.client, "compare", "POST", "/compare",
            json={"candidate_ids": cap, "aspect": "Kinh nghiệm thực chiến và kỹ năng lõi"},
        )

    @task(2)
    def sinh_cau_hoi_phong_van(self):
        cid = self.a_scored_candidate()
        if not cid:
            return
        timed(
            self.client, "interview_generate", "POST",
            f"/interviews/candidate/{cid}/generate",
            json={"aspect": "Khả năng thiết kế hệ thống"},
        )

    @task(1)
    def cham_cau_tra_loi(self):
        cid = self.a_scored_candidate()
        if not cid:
            return
        resp = timed(
            self.client, "interview_get", "GET", f"/interviews/candidate/{cid}",
            expect=(200, 404),
        )
        if resp.status_code != 200:
            return
        cau_hoi = (resp.json() or {}).get("questions") or []
        if not cau_hoi:
            return
        timed(
            self.client, "interview_evaluate", "POST",
            f"/interviews/question/{random.choice(cau_hoi)['id']}/evaluate",
            json={
                "answer_text": "Ứng viên mô tả đã tối ưu truy vấn bằng cách thêm chỉ mục "
                               "và gộp các lời gọi, giảm thời gian phản hồi từ 2 giây "
                               "xuống khoảng 300 mili-giây."
            },
        )

    @task(1)
    def tao_jd_moi(self):
        """Tạo dự án mới — để lại dữ liệu, nên còn cần hồ sơ `write`/`all` nữa."""
        if not ALLOW_MUTATION:
            return
        timed(
            self.client, "jd_create", "POST", "/jds", expect=(201,),
            json={
                "raw_text": "Tuyển Backend Engineer, 2-4 năm kinh nghiệm Python và FastAPI, "
                            "thành thạo PostgreSQL, có kinh nghiệm Docker và hàng đợi tác vụ. "
                            "Ưu tiên ứng viên từng làm hệ thống nhiều người dùng."
            },
        )

    @task(1)
    def nap_zip_cv(self):
        """Đo PHA ĐỒNG BỘ của việc nạp CV (giải nén + trích text + tạo bản ghi).

        Nằm trong lớp `ai` dù bản thân endpoint KHÔNG gọi LLM: mỗi CV nạp thành công
        sẽ sinh một task Celery, và task đó mới là thứ tiêu quota. Chạy vô tư ở đây
        nghĩa là nhét hàng trăm CV rác vào hàng đợi chấm điểm.
        """
        if not ALLOW_MUTATION:
            return
        if CV_ZIP_PATH and os.path.exists(CV_ZIP_PATH):
            with open(CV_ZIP_PATH, "rb") as f:
                du_lieu, ten = f.read(), os.path.basename(CV_ZIP_PATH)
        else:
            du_lieu, ten = _zip_cv_gia(CV_ZIP_COUNT), "loadtest_cvs.zip"

        timed(
            self.client, "cv_upload", "POST", f"/jds/{self.jd_id}/cvs", expect=(202,),
            files={"file": (ten, du_lieu, "application/zip")},
        )
