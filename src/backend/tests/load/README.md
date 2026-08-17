# Load test — kiểm chứng NFR thời gian phản hồi

Bộ test đo thời gian phản hồi của API HireWise và đối chiếu với ngân sách công bố
trước, rồi kết luận **Đạt / Không đạt** cho từng endpoint.

| Tệp | Vai trò |
|---|---|
| `slo.py` | Danh mục ngân sách độ trễ, bộ đo, và bộ sinh báo cáo cuối phiên |
| `locustfile.py` | Bốn hồ sơ tải (duyệt màn hình, ghi shortlist, giám sát admin, đường LLM) |
| `seed.py` | Kiểm tra tài khoản/dữ liệu đã đủ để đo chưa; tạo tài khoản HR khi cần |
| `requirements-load.txt` | Phụ thuộc, tách riêng khỏi image backend |

---

## 1. Chuẩn bị

```powershell
cd src\backend\tests\load
pip install -r requirements-load.txt
```

Hệ thống phải đang chạy (`docker compose up -d`) và **đã chấm xong** các CV đang chờ —
worker chạy nền chiếm CPU và kết nối DB, đo trong lúc đó thì độ trễ ghi nhận được lẫn
cả tải của worker.

Khai báo tài khoản:

```powershell
$env:LOAD_HR_EMAIL    = "hr@example.com"
$env:LOAD_HR_PASSWORD = "matkhau"
# tuỳ chọn — bật hồ sơ giám sát admin
$env:LOAD_ADMIN_EMAIL    = "admin@example.com"
$env:LOAD_ADMIN_PASSWORD = "matkhau-admin"
```

Kiểm tra điều kiện. Bước này cho biết tài khoản có bao nhiêu dữ liệu và cảnh báo khi
dữ liệu quá ít để phép đo có ý nghĩa:

```powershell
python seed.py
```

> Chưa có tài khoản HR riêng cho việc đo? `python seed.py --create-hr` sẽ nhờ admin
> tạo (tạo qua admin nên bỏ qua được luồng xác minh email). Nhưng **tài khoản mới
> không có dữ liệu** — mọi endpoint nghiệp vụ đều lọc theo chủ sở hữu, nên nên dùng
> chính tài khoản đang có dự án thật.

---

## 2. Chạy đo

Chọn hồ sơ tải bằng `--load-profile`. Mỗi hồ sơ quyết định những **lớp người dùng** nào
được đưa vào phiên chạy.

| Hồ sơ | Gồm gì | Dùng khi |
|---|---|---|
| `read` *(mặc định)* | Đường đọc + thao tác ghi tự dọn được | Hầu hết phép đo |
| `write` | `read` + chỉnh điểm ứng viên | Cần đo cả đường ghi không hoàn tác |
| `ai` | Chỉ các endpoint gọi LLM | Lấy số liệu tham khảo cho nhóm F |
| `all` | Tất cả | Hiếm khi là thứ bạn muốn |

### Hồ sơ mặc định — an toàn, không tốn quota AI

```powershell
locust -f locustfile.py --host http://localhost:8000 --headless -u 20 -r 5 -t 3m
```

`-u 20` 20 người dùng đồng thời · `-r 5` tăng 5 người/giây · `-t 3m` chạy 3 phút.

Bỏ `--headless` để mở giao diện web của Locust tại <http://localhost:8089> (có biểu đồ
độ trễ theo thời gian — tiện chụp đưa vào báo cáo).

### Có thao tác ghi để lại dấu vết

```powershell
locust -f locustfile.py --host http://localhost:8000 --load-profile write `
       --headless -u 20 -r 5 -t 3m
```

Bật thêm việc HR ghi đè điểm ứng viên. **Sửa dữ liệu thật, không tự hoàn tác** — chỉ
chạy trên môi trường thử nghiệm.

### Đường có gọi LLM — đọc kỹ trước khi chạy

```powershell
locust -f locustfile.py --host http://localhost:8000 --load-profile ai `
       --headless -u 2 -r 1 -t 5m
```

Mỗi lượt ở đây tiêu **quota Groq thật**. Hạn mức free tier tính theo token/phút và
token/ngày, nên bắn 20 người dùng đồng thời vào nhóm này không đo ra "hệ thống chậm
bao nhiêu" mà chỉ đo ra "hàng đợi rate limiter dài bao nhiêu", đồng thời đốt sạch quota
của cả ngày. Dùng 1–2 người dùng, và đọc kết quả như số liệu **tham khảo**.

> **Vì sao là `--load-profile` chứ không phải `--tags` của Locust?** Tag chỉ lọc *task*,
> không loại *lớp* người dùng: khi mọi task của một lớp bị lọc hết, Locust vẫn sinh
> người dùng của lớp đó rồi ném `No tasks defined on ...` giữa phiên đo. Và tên phải là
> `--load-profile` vì Locust 2.4x đã dùng `--profile` cho việc xuất hồ sơ hiệu năng của
> chính nó — đăng ký trùng tên thì tham số bị bỏ qua trong im lặng.

---

## 3. Đọc kết quả

Cuối mỗi phiên, bộ đo in bảng sau ra terminal và ghi vào `load-report/slo-report.md`
(kèm bản `.json` để vẽ biểu đồ):

```
  ▸ B · truy vấn tổng hợp  (ngân sách nhóm: 800 ms)
  GET /jds/{id}/candidates      1284      112      263      401      612       800    0.0   ĐẠT
  GET /candidates/{id}           642      189      544      903     1120       800    0.0   KHÔNG ĐẠT
```

Kết luận dựa trên **p95**: 95% số lượt phải nằm trong ngân sách. Một lượt vượt ngân
sách cũng bị Locust đánh `Failure` ngay tại thời điểm đó, nên cột *Failures* trong bảng
gốc của Locust phản ánh vi phạm SLO chứ không chỉ lỗi HTTP.

Có endpoint không đạt thì tiến trình thoát với mã `1` — cắm thẳng vào CI được.

### Ngân sách theo nhóm

| Nhóm | p95 | Vì sao đặt mức đó |
|---|---:|---|
| A · tra cứu tức thời | 300 ms | Một truy vấn chỉ mục, danh sách ngắn. Đây là ngưỡng "cảm giác tức thì". |
| B · truy vấn tổng hợp | 800 ms | Gộp nhiều bảng, hoặc dựng lại bảng xếp hạng trong Python. Khối lượng tăng theo số ứng viên. |
| C · ghi dữ liệu | 1 000 ms | Có ghi và commit xuống Postgres. |
| D · xác thực | 1 200 ms | bcrypt 12 vòng tốn ~250–350 ms CPU mỗi lần đối chiếu mật khẩu. Đó là **tính năng bảo mật**; ép xuống 300 ms tức là tự bắt mình hạ số vòng băm. |
| E · nạp tệp | 5 000 ms | Chỉ tính pha đồng bộ: giải nén + PyMuPDF trích text + tạo bản ghi PENDING. Phần chấm điểm do worker làm nền, **không** nằm trong con số này. |
| F · có gọi LLM | 30 000 ms | Qua mạng tới nhà cung cấp, còn phải xếp hàng chờ ngân sách token. Không áp được ngưỡng giao diện lên nhóm này. |

Chỉnh ngưỡng từng endpoint bằng biến môi trường `SLO_<KEY>_MS`, ví dụ dữ liệu lớn hơn
mức thiết kế thì nới riêng bảng xếp hạng:

```powershell
$env:SLO_LEADERBOARD_MS = "1200"
```

Khoá `<KEY>` là cột `key` trong danh mục ở [`slo.py`](slo.py) (`leaderboard`,
`candidate_detail`, `login`, …).

---

## 4. Biến môi trường

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `LOAD_PROFILE` | `read` | Hồ sơ tải mặc định khi không truyền `--load-profile` |
| `LOAD_HR_EMAIL` / `LOAD_HR_PASSWORD` | — | Tài khoản HR dùng để đo. **Bắt buộc.** |
| `LOAD_ADMIN_EMAIL` / `LOAD_ADMIN_PASSWORD` | `DEFAULT_ADMIN_*` trong `.env` | Bật hồ sơ giám sát admin |
| `LOAD_JD_ID` | tự dò | Ghim một dự án cố định — kết quả ổn định hơn khi so sánh giữa các lần chạy |
| `LOAD_CV_ZIP` | tự sinh | ZIP CV thật để đo đường nạp tệp. Bỏ trống thì tự dựng PDF tổng hợp |
| `LOAD_CV_COUNT` | `5` | Số CV trong ZIP tự sinh |
| `LOAD_REPORT_DIR` | `load-report` | Thư mục ghi báo cáo |
| `SLO_MAX_ERROR_RATE` | `0` | Tỉ lệ lỗi HTTP tối đa còn coi là đạt |
| `SLO_<KEY>_MS` | theo nhóm | Ghi đè ngân sách của một endpoint |

---

## 5. Những điều bộ test này **không** đo

Nói rõ để không diễn giải quá tay kết quả:

- **Thời gian chấm xong một CV.** Đó là công việc bất đồng bộ trong Celery worker,
  không phải thời gian phản hồi HTTP. Muốn đo thì phải bấm giờ từ lúc `POST /jds/{id}/cvs`
  tới lúc `status` của ứng viên chuyển sang `COMPLETED` — một phép đo thông lượng khác hẳn.
- **Độ trễ phía trình duyệt.** Đây là phép đo API. Thời gian render React, tải bundle,
  và độ trễ mạng của người dùng cuối nằm ngoài phạm vi.
- **Sức chịu tải của nhóm F.** Bị chặn bởi hạn mức của Groq chứ không phải bởi năng lực
  của HireWise, nên con số ở nhóm đó nói về nhà cung cấp nhiều hơn nói về hệ thống.
- **Hành vi khi Redis hoặc Postgres chết.** Đó là kiểm thử khả năng chịu lỗi, cần một
  kịch bản riêng.
