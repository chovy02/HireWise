# PROMPT ĐỂ PASTE VÀO CLAUDE.AI (WEB) — XUẤT FILE .PPTX

> Copy toàn bộ phần nằm giữa hai đường kẻ dưới đây rồi dán vào khung chat của Claude web.
> Yêu cầu: tài khoản Claude phải bật tính năng tạo file (Upgraded file creation / Analysis tool).

---

Hãy tạo cho tôi một **file PowerPoint (.pptx) báo cáo đồ án**, dùng công cụ chạy code với thư viện **python-pptx**, rồi cho tôi tải file về.

## A. YÊU CẦU KỸ THUẬT CỦA FILE PPTX

- Khổ slide **16:9**: `prs.slide_width = Inches(13.333)`, `prs.slide_height = Inches(7.5)`.
- Dùng layout trắng (`prs.slide_layouts[6]`) và **tự đặt mọi textbox/shape bằng tọa độ** — đừng dùng placeholder mặc định vì chúng hay lệch.
- **Font: `Calibri`** (hoặc `Arial`) cho toàn bộ — bắt buộc, vì nội dung là **tiếng Việt có dấu**, các font trang trí hay mất dấu. Cỡ chữ: tiêu đề slide 32pt bold, tiêu đề phụ 20pt, nội dung 16–18pt, chữ trong bảng 12–14pt, chữ trong hình vẽ 10–12pt.
- Bảng màu (khai thành hằng số ở đầu code, dùng nhất quán):
  - `NAVY = RGBColor(0x0F, 0x2B, 0x46)` — nền slide tiêu đề chương, chữ tiêu đề
  - `ACCENT = RGBColor(0x1E, 0x88, 0xE5)` — màu nhấn, gạch chân tiêu đề, header bảng
  - `LIGHT = RGBColor(0xEC, 0xF3, 0xFA)` — nền ô nhạt
  - `GRAY = RGBColor(0x5A, 0x6B, 0x7B)` — chữ phụ
  - `WHITE`, và `WARN = RGBColor(0xFF, 0xF4, 0xCE)` — nền cho phần nhóm tự điền
- Mỗi slide nội dung có: dải tiêu đề trên cùng (textbox tiêu đề + một đường kẻ ngang màu ACCENT), và **số slide ở góc dưới phải**.
- Slide mở đầu mỗi phần lớn là **slide chuyển chương** nền NAVY, chữ trắng, cỡ lớn.

### Cách viết code cho gọn (quan trọng — đừng viết tay từng slide)

Định nghĩa trước các hàm trợ giúp rồi **gọi trong vòng lặp trên dữ liệu**:

```python
def add_title_slide(prs, title, subtitle, fields)      # slide bìa
def add_section_slide(prs, number, title)              # slide chuyển chương (nền NAVY)
def add_bullet_slide(prs, title, bullets, note=None)   # bullets, hỗ trợ 2 cấp (tuple (level, text))
def add_two_col_slide(prs, title, left, right)         # hai cột bullets
def add_table_slide(prs, title, headers, rows, widths=None, note=None)
def add_box(slide, x, y, w, h, text, fill, font_color, size=11, bold=False)   # 1 ô chữ nhật bo góc
def add_arrow(slide, x1, y1, x2, y2, label=None)       # mũi tên nối (connector + textbox nhãn)
def add_class_box(slide, x, y, w, name, attrs)         # ô class: thanh tiêu đề + danh sách thuộc tính
def add_sequence(slide, actors, messages)              # sequence diagram: lifeline + mũi tên có nhãn
def add_todo_box(slide, x, y, w, h, text)              # ô nền WARN, viền đứt, cho phần nhóm tự điền
```

Nội dung slide khai thành **list dict** rồi lặp — như vậy 40 slide vẫn gọn.

### Xử lý giới hạn độ dài phản hồi

Bộ slide này dài. Nếu một lần chạy code không đủ chỗ, hãy làm **nhiều lượt**:
1. Lượt 1: định nghĩa helper + tạo phần 0–3, `prs.save('HireWise_BaoCao.pptx')`.
2. Lượt sau: `prs = Presentation('HireWise_BaoCao.pptx')`, định nghĩa lại helper, thêm tiếp các phần còn lại, save đè.
3. Cuối cùng báo cho tôi tổng số slide và đưa link tải file.

**Không được bỏ bớt slide vì lý do độ dài** — cứ chia nhiều lượt cho tới khi đủ.

## B. CÁCH VẼ SƠ ĐỒ TRONG PPTX

PowerPoint không có Mermaid, nên **vẽ bằng shape thật** (`MSO_SHAPE.ROUNDED_RECTANGLE`, `MSO_SHAPE.RECTANGLE`, đường thẳng, connector có đầu mũi tên). Quy tắc:

- **Sơ đồ kiến trúc / luồng dữ liệu:** các ô chữ nhật bo góc xếp theo lưới, mũi tên nối ngang/dọc, nhãn mũi tên là textbox nhỏ 10pt đặt cạnh giữa mũi tên. Ô nào là service Docker thì ghi thêm dòng nhỏ tên container + cổng.
- **Class diagram:** mỗi class là một ô: thanh tiêu đề nền ACCENT chữ trắng (tên class), thân nền LIGHT liệt kê thuộc tính chính (tối đa 6 dòng/class, chọn thuộc tính quan trọng nhất). Quan hệ vẽ bằng đường thẳng, ghi bội số (`1`, `N`) bằng textbox nhỏ ở hai đầu.
- **Sequence diagram:** hàng participant ở trên (ô chữ nhật), mỗi participant có một **đường lifeline dọc đứt nét** kéo xuống, các message là **mũi tên ngang** giữa hai lifeline, nhãn đặt ngay trên mũi tên. Message trả về dùng nét đứt. Nhánh `alt` thể hiện bằng một khung chữ nhật rỗng viền mảnh bao quanh nhóm message, góc trên trái ghi `alt [điều kiện]`.
- **Use case diagram:** actor vẽ bằng hình oval nhỏ + nhãn (hoặc chỉ ô chữ nhật ghi tên actor cũng được), use case là các oval (`MSO_SHAPE.OVAL`) nằm trong một khung "System boundary" chữ nhật lớn, nối bằng đường thẳng.
- Sơ đồ nào quá phức tạp để vẽ đẹp thì **vẫn vẽ bản rút gọn**, đừng bỏ trống, và thêm một `add_todo_box` nhỏ ghi `«nhóm có thể thay bằng ảnh sơ đồ chi tiết»`.
- Chữ trong shape phải **vừa trong ô** (chọn cỡ 10–12pt, ô đủ rộng) — đừng để tràn.

## C. QUY TẮC VỀ PHẦN CÒN THIẾU (RẤT QUAN TRỌNG)

Tôi cung cấp bên dưới toàn bộ dữ kiện có thật lấy từ source code. Với nội dung mà dữ kiện **không đủ** (số liệu benchmark, kết quả test thủ công, ảnh chụp màn hình, tên thành viên, ngày tháng...):

- **Vẫn tạo slide đó**, dựng sẵn bố cục đầy đủ (bảng có sẵn cột và vài dòng trống, khung ảnh có caption sẵn).
- Đánh dấu chỗ cần điền bằng `add_todo_box` (nền WARN, viền đứt) với nội dung dạng `«… nhóm tự điền …»`.
- **TUYỆT ĐỐI KHÔNG bịa** số liệu đo lường, tên người, ngày tháng như thể là thật. Số liệu duy nhất được coi là thật là những gì liệt kê ở phần DỮ KIỆN bên dưới.

---

# DỮ KIỆN THẬT VỀ ĐỒ ÁN (lấy trực tiếp từ source code)

## 1. Tên & ý tưởng

**HireWise** — phần mềm hỗ trợ tuyển dụng bằng AI (AI-powered recruitment screening platform).

Bài toán: một tin tuyển dụng nhận về hàng trăm CV; HR phải đọc thủ công, chấm điểm theo cảm tính, mỗi người chấm một kiểu, không truy vết được vì sao ứng viên A trên ứng viên B. Việc lọc CV, tạo shortlist, soạn câu hỏi phỏng vấn và gửi mail kết quả đều là thao tác lặp lại, tốn hàng chục giờ mỗi đợt tuyển.

Giải pháp của HireWise:
1. HR tạo **JD (Job Description)** → AI bóc tách JD thành bộ yêu cầu có cấu trúc (JSON).
2. HR upload **file ZIP chứa nhiều CV PDF** → hệ thống trích text, khử trùng lặp, đưa vào hàng đợi nền.
3. AI **chấm điểm từng CV theo rubric có trọng số cố định trong code** (không để model tự nghĩ ra điểm tổng), kèm **bằng chứng trích từ CV** cho từng nhận định.
4. HR xem **bảng xếp hạng**, so sánh ứng viên, tạo **shortlist**, chốt nhận/loại.
5. AI **sinh câu hỏi phỏng vấn** riêng cho từng ứng viên, ghi nhận câu trả lời, chấm điểm phỏng vấn thang 10, tổng kết.
6. **Gửi email kết quả** theo mẫu HR tự soạn (có ảnh inline, file đính kèm), theo dõi trạng thái gửi từng người.
7. Xuyên suốt là một **Copilot chat**: HR gõ tiếng Việt tự nhiên ("lấy 3 người điểm cao nhất bỏ vào shortlist tên là tiềm năng"), AI Agent tự chọn tool, thao tác dữ liệu thật, **và điều hướng luôn giao diện** sang đúng màn hình chứa kết quả.

Điểm khác biệt cốt lõi so với một chatbot gắn thêm:
- Điểm số **giải thích được và so sánh được** (trọng số nằm ở code, điểm tổng do code nhân trọng số rồi cộng).
- Agent thao tác dữ liệu thật qua **MCP (Model Context Protocol)** với đầy đủ rào chắn danh tính, phạm vi dữ liệu, và xác nhận hành động không thu hồi được.

## 2. Vai trò người dùng

| Vai trò | Mô tả |
|---|---|
| `hr_staff` | Nhân viên tuyển dụng — người dùng chính. Tạo JD, upload CV, xem bảng xếp hạng, shortlist, phỏng vấn, gửi mail, dùng Copilot chat. |
| `admin` | Quản trị hệ thống — quản lý tài khoản (khóa/mở), xem system logs / AI logs / agent tool logs / audit logs, xem business metrics, đăng thông báo hệ thống, export CSV. |

Xác thực: đăng ký → nhận **mã OTP 6 chữ số qua email** → xác minh (`is_active`) → đăng nhập nhận **JWT**. Admin có thể khóa tài khoản (`is_banned`, tách riêng khỏi `is_active`).

## 3. Công nghệ (chính xác theo requirements.txt / package.json)

**Backend:** Python 3.11, FastAPI 0.110.0, Uvicorn 0.29.0, SQLAlchemy 2.0.29 (ORM kiểu `Mapped[...]`), PostgreSQL 15 (psycopg2-binary), Alembic 1.13.1, Pydantic v2 + pydantic-settings, python-jose (JWT), passlib+bcrypt, fastapi-mail, PyMuPDF 1.24 (đọc PDF).

**Xử lý nền:** Celery 5.3.6 + Redis 7 (broker DB 0, result backend DB 1, sổ sách rate limit DB 2), worker chạy `--concurrency=4`.

**LLM:** Groq (OpenAI-compatible, free tier). Model agent chính `openai/gpt-oss-120b`, dự phòng `openai/gpt-oss-20b`. Pipeline chấm CV gọi qua module `gemini_client.py` (tên file giữ theo lịch sử dự án, hiện chạy trên Groq).

**MCP:** Python SDK `mcp>=1.12,<2` — FastMCP server, transport **Streamable HTTP**.

**Frontend:** React 18.3, Vite 6, TailwindCSS 4, react-router-dom 6.28, lucide-react (icon).

**Hạ tầng:** Docker Compose, 6 service, TZ=Asia/Ho_Chi_Minh toàn bộ container.

**Test:** pytest 8.3.3.

## 4. Kiến trúc triển khai — 6 service Docker

| Service | Container | Vai trò | Cổng |
|---|---|---|---|
| `frontend` | hirewise_frontend | React + Vite dev server | 5173 (publish) |
| `api` | hirewise_api | FastAPI — điểm vào duy nhất của người dùng, xác thực JWT, chạy migration lúc khởi động (`app.prestart`) | 8000 (publish) |
| `mcp` | hirewise_mcp | **HireWise MCP Server** (FastMCP, Streamable HTTP) | 8001 — **CỐ Ý KHÔNG publish ra host** |
| `worker` | hirewise_worker | Celery worker chấm CV nền, concurrency=4 | — |
| `db` | hirewise_db | PostgreSQL 15 (healthcheck `pg_isready`) | 5433→5432 |
| `redis` | hirewise_redis | Broker + result backend + sổ sách rate limit | 6379 |

Luồng gọi: `frontend → api (JWT) → mcp (Bearer token + header danh tính) → DB`. Service `api` khai `depends_on: mcp: condition: service_healthy` — nếu chỉ chờ `service_started` thì lượt chat đầu tiên sau khi `up` sẽ âm thầm rơi xuống đường fallback.

Volume: `postgres_data`, `cv_storage` (file PDF CV), `email_attachments` (ảnh/file gắn vào mẫu mail).

## 5. Mô hình dữ liệu — 21 bảng (SQLAlchemy ORM)

`users`, `email_templates`, `email_template_attachments`, `chat_sessions`, `chat_messages`, `job_descriptions`, `upload_batches`, `candidates`, `candidate_skills`, `candidate_projects`, `evaluations`, `evaluation_overrides`, `shortlists`, `shortlist_items`, `interviews`, `interview_questions`, `agent_tool_logs`, `system_logs`, `ai_logs`, `audit_logs`, `notifications`.

Quan hệ chính (dùng cho **Class Diagram**):

- `User 1—N JobDescription` (created_by); `User 1—N Shortlist`; `User 1—N ChatSession`; `User 1—N AgentToolLog`; `User 1—N EmailTemplate` (unique `user_id + template_type`).
- `JobDescription 1—N Candidate`; `1—N Evaluation`; `1—N Shortlist`; `1—N UploadBatch`. Có **xóa mềm** qua cột `deleted_at` (thùng rác — khôi phục được, vì mỗi JD gắn hàng chục CV đã tốn quota AI để chấm).
- `Candidate 1—N CandidateSkill`; `1—N CandidateProject`; `1—1 Evaluation`; `1—1 Interview`; `1—N ShortlistItem`.
- `Evaluation 1—N EvaluationOverride` (HR chỉnh điểm phải ghi lý do, lưu old_score/new_score); `1—N AgentToolLog`.
- `Shortlist 1—N ShortlistItem`; `ShortlistItem N—1 Candidate`.
- `Interview 1—N InterviewQuestion` (sắp theo `order_index`).
- `ChatSession 1—N ChatMessage` (có đếm `prompt_tokens` / `completion_tokens`).

Thuộc tính đáng đưa lên slide:
- `Evaluation`: `score` (float, thang 100), `score_breakdown` (JSONB), `evidence` (JSONB), `details` (JSONB — kết luận, độ tin cậy, điểm từng trục, đối chiếu từng yêu cầu JD, điểm mạnh/yếu, rủi ro, gợi ý phỏng vấn), `is_overridden`.
- `Candidate`: `status` (`cho_xu_ly` / `FAILED` / đã chấm), `file_hash` (khử trùng CV), `error_message` (phân biệt lỗi tạm thời với lỗi vĩnh viễn như CV là ảnh scan).
- `UploadBatch`: `total` / `staged` / `duplicated` / `failed` — thống kê một lượt upload ZIP.
- `ShortlistItem`: `candidate_status` (pending/accepted/rejected) + các cột theo dõi gửi mail: `notified_at`, `notified_status`, `notify_state` (null/sending/sent/failed), `notify_error_code`, `notify_error`, `notify_attempts`, `notify_last_attempt_at`.
- **Quy ước thời gian toàn hệ thống:** mọi cột thời gian là `timestamptz` và luôn ghi `datetime.now(timezone.utc)` — trước đây dùng `timestamp` không offset khiến trình duyệt ở UTC+7 hiển thị sai lệch 7 tiếng.
- **Ràng buộc chống trùng ở tầng DB:** unique index `uq_shortlists_jd_ten` trên `(jd_id, lower(btrim(name)))` — hai lượt agent chạy chồng nhau từng tạo ra hai shortlist "tiềm năng (3)" y hệt.

Có **20 file migration Alembic** trong `migrations/versions/` (đặt tên tiếng Việt: `them_bang_upload_batches`, `chuyen_moc_thoi_gian_sang_timestamptz`, `gop_shortlist_trung_ten_va_khoa_duy_nhat`...).

## 6. API Backend (FastAPI routers)

| Router | Endpoint tiêu biểu |
|---|---|
| `auth` | `POST /register`, `POST /resend-code`, `POST /verify-email`, `POST /login`, `GET/PATCH /me`, `PUT /me/password` |
| `users` | CRUD người dùng, `PATCH /{id}/deactivate` |
| `cv` (3 router) | `POST /jds`, `GET /jds`, `GET /jds/trash`, `GET /jds/{id}`, `DELETE /jds/{id}` (xóa mềm), `POST /jds/{id}/restore`, `DELETE /jds/{id}/permanent`, upload ZIP, `GET /jds/{id}/uploads`, `GET /jds/{id}/candidates` (leaderboard), `GET /candidates/{id}`, `POST /candidates/{id}/retry`, `GET /candidates/{id}/cv` (tải PDF), `PATCH /evaluations/{id}/override` |
| `shortlist` | tạo/liệt kê/xem/xóa shortlist, thêm–sửa–xóa item, chốt quyết định, gửi mail kết quả |
| `interview` | `GET /candidate/{id}`, `POST /candidate/{id}/generate` (AI sinh câu hỏi), thêm/xóa câu hỏi, `POST /question/{id}/evaluate` (AI chấm câu trả lời), `PATCH /{id}/complete` |
| `compare` | `POST /compare` — AI so sánh nhiều ứng viên |
| `agent` | `POST /agent/chat`, `GET /agent/sessions`, `GET /agent/sessions/{id}`, `DELETE /agent/sessions/{id}` |
| `email_templates` | xem/sửa mẫu, upload–tải–xóa file đính kèm |
| `notifications` | `GET /notifications` |
| `admin` | `/system-logs`, `/ai-metrics`, `/ai-logs`, `/agent-tool-logs`, `/audit-logs`, `/audit-filters`, `/business-metrics`, CRUD `/notifications`, 4 endpoint `/export/*` xuất CSV |

## 7. Frontend — các màn hình

Route (React Router, có `RoleRoute` chặn theo vai trò):
`/login`, `/signup`, `/verify` (công khai) — `/` Bảng điều khiển, `/projects/new` Tạo vị trí, `/projects/:id` Chi tiết vị trí (leaderboard + upload + đánh giá), `/shortlisting` Danh sách rút gọn, `/settings/email-templates` Mẫu email, `/trash` Thùng rác, `/settings/account` Tài khoản, `/admin` Cổng quản trị.

Component đáng nhắc: `CopilotChat`, `EvaluationPanel`, `CandidateDetailModal`, `InterviewModal`, `InterviewSummary`, `TokenEditor` + `RichTextToolbar` (soạn mẫu mail), `PageContext` (gửi ngữ cảnh trang HR đang xem lên cho agent), `useAgentReload` (agent thao tác xong thì màn hình tự nạp lại).

## 8. Pipeline chấm CV (dùng cho Sequence Diagram)

1. HR upload ZIP → `ingest_zip` giải nén, `extract_text_from_pdf` (PyMuPDF) trích text, `save_cv_pdf` lưu file, tính `file_hash` để bỏ CV trùng → tạo `Candidate` (status `cho_xu_ly`) + ghi `UploadBatch`.
2. Mỗi CV đẩy một task Celery `evaluate_candidate` vào Redis (task có `rate_limit="20/m"`).
3. Worker chạy `pipeline.evaluate_candidate`: `parse_cv` (LLM bóc tách thông tin) → `score_cv` (LLM chấm + sinh bằng chứng **trong cùng một lượt gọi**) → lưu `Evaluation`.
4. Vướng hạn mức LLM → ném `LLMBudgetExhausted` → Celery **hẹn lại** (tối đa 12 lần, countdown = retry-after + jitter ngẫu nhiên 0–15s để cả batch không cùng lúc lao vào lần nữa). Hết lượt hẹn thì đánh `FAILED` kèm `error_message` chứ không để CV kẹt im lặng.

**Rubric chấm điểm — trọng số cố định trong code** (tổng 100):

| Trục | Trọng số |
|---|---|
| Kỹ năng bắt buộc (`required_skills`) | 35 |
| Kinh nghiệm (`experience`) | 25 |
| Dự án & thành tựu (`projects`) | 15 |
| Học vấn (`education`) | 10 |
| Ưu tiên & chứng chỉ (`extras`) | 10 |
| Ngoại ngữ (`languages`) | 5 |

Lý do thiết kế (nên nói trong slide): bản đầu để model trả thẳng một `score` cạnh `score_breakdown`; hai thứ không ràng buộc nhau nên gặp cảnh breakdown 90/85/80 mà điểm tổng lại 62 — HR không truy được 62 từ đâu ra. Cố định trọng số ở code khiến điểm (a) giải thích được từng phần, (b) so sánh được giữa các ứng viên vì mọi người dùng chung một công thức.

Tối ưu quota: bản cũ gọi LLM **3 lần/CV** và gửi full text CV **2 lần** (parse + evidence) → gộp bằng chứng vào lượt chấm còn **2 lần/CV**.

Xếp hạng dùng chung một khóa sắp xếp (`core/ranking.py`): điểm cao trước, chưa có điểm xếp cuối, phá hòa bằng `(created_at, id)` — nếu mỗi màn hình tự sắp xếp thì hai ứng viên trùng điểm hiện thứ tự khác nhau ở Leaderboard và Shortlist.

## 9. ★ PHẦN RIÊNG VỀ MCP (Model Context Protocol) — làm hẳn một chương 7 slide

### 9.1 MCP là gì và vì sao dự án dùng

MCP là giao thức chuẩn để một ứng dụng **phơi năng lực (tool) ra cho LLM** theo một hợp đồng thống nhất, thay vì mỗi model một kiểu function-calling riêng. Trong HireWise, MCP **nằm thật trong luồng chạy của sản phẩm**, không phải demo bên lề:

```
run_agent → mcp_client (Streamable HTTP) → HireWise MCP Server → agent_tools → PostgreSQL
```

Danh sách tool **không hard-code** ở backend: mỗi lượt chat, backend hỏi MCP server `tools/list`, đưa schema đó cho LLM, LLM chọn tool, backend gọi `tools/call` qua MCP.

### 9.2 Kiến trúc: một nguồn sự thật duy nhất (`tool_registry.py`)

Vấn đề đã xảy ra thật: bộ tool từng được mô tả ở **hai nơi viết tay song song** — schema function-calling cho Groq trong `agent_tools.py`, và các wrapper `@mcp.tool()` trong `mcp_server/server.py`. Hai bản trôi lệch: `send_interview_invite` có ở bản Groq nhưng **chưa hề đăng ký trên MCP server**, trong khi system prompt vẫn dặn LLM dùng nó → đường chính không có cách nào gửi thư mời phỏng vấn.

Giải pháp: mọi tool khai **một lần duy nhất** thành `ToolSpec` trong `tool_registry.py`. Hai nơi tiêu thụ đều **sinh ra** từ đó:
- MCP server duyệt REGISTRY → tự dựng hàm đúng chữ ký → `mcp.add_tool(...)`.
- Đường fallback: `llm_tool_schemas()` sinh thẳng schema function-calling cho Groq.

Thêm tool = thêm một `ToolSpec`. Không còn chỗ nào để quên. (Vẽ sơ đồ: 1 ô REGISTRY ở giữa → 2 mũi tên sang 2 ô "MCP server" và "Fallback schema".)

### 9.3 Bộ 20 tool trên MCP server

| # | Tool | Nhãn | Loại |
|---|---|---|---|
| 1 | `list_jds` | Liệt kê vị trí tuyển dụng | read-only, idempotent |
| 2 | `get_jd` | Xem chi tiết vị trí | read-only, idempotent |
| 3 | `search_candidates` | Tìm ứng viên | read-only, idempotent |
| 4 | `get_candidate` | Xem chi tiết ứng viên | read-only, idempotent |
| 5 | `list_shortlists` | Liệt kê shortlist | read-only, idempotent |
| 6 | `compare_candidates` | So sánh ứng viên | read-only (gọi LLM nên không idempotent) |
| 7 | `create_jd` | Tạo vị trí tuyển dụng mới | ghi, `user_bound=created_by` |
| 8 | `generate_interview_questions` | Sinh câu hỏi phỏng vấn | ghi, **destructive** (ghi đè bộ câu hỏi) |
| 9 | `create_shortlist` | Tạo shortlist | ghi, `user_bound=created_by` |
| 10 | `add_to_shortlist` | Thêm ứng viên vào shortlist | ghi, `user_bound=created_by` |
| 11 | `send_interview_invite` | Gửi thư mời phỏng vấn | **destructive + open_world** (SMTP) |
| 12 | `get_interview` | Xem buổi phỏng vấn | read-only, idempotent |
| 13 | `record_interview_answers` | Nhập câu trả lời phỏng vấn | ghi, **destructive** |
| 14 | `finish_interview` | Kết thúc & tổng kết phỏng vấn | **destructive** |
| 15 | `list_interview_results` | Bảng điểm phỏng vấn | read-only, idempotent |
| 16 | `set_candidate_decision` | Chốt nhận / loại ứng viên | ghi (không destructive — đổi lại được) |
| 17 | `send_decision_emails` | Gửi thư báo kết quả | **destructive + open_world** (SMTP) |
| 18 | `open_jd` | Mở trang vị trí | điều hướng UI |
| 19 | `open_dashboard` | Mở Dashboard | điều hướng UI |
| 20 | `open_shortlisting` | Mở màn hình Shortlisting | điều hướng UI |

Ba tool cuối là điểm thú vị: **agent điều khiển được cả giao diện** — HR hỏi gì thì màn hình mở đúng chỗ chứa thứ đó.

Các annotation MCP (`read_only` / `destructive` / `idempotent` / `open_world`) **được dùng thật**: `agent.py` đọc `read_only` để biết trong lượt vừa rồi đã có tool GHI nào chạy xong chưa.

### 9.4 Ba lớp bảo mật của MCP server

1. **Xác thực:** mọi request phải mang `Authorization: Bearer $MCP_AUTH_TOKEN`. Thiếu biến môi trường → server **từ chối khởi động** (chạy tiếp im lặng là tự sinh ra một endpoint đọc/ghi ẩn danh). Ngoại lệ duy nhất: `/healthz`.
2. **Danh tính đi theo phiên, không theo lời gọi tool:** HR đang thao tác được khai qua **header `X-HireWise-Actor`**, không phải tham số tool. Bản trước nhận `acting_user_id` như tham số bình thường nên nó nằm trong inputSchema mà LLM nhìn thấy — chỉ cần quên lọc một chỗ là model tự điền được id người khác. Danh tính là thuộc tính của **kết nối**, không phải của lời gọi tool. Server vẫn **xác minh lại** id đó với bảng `users` (tồn tại, đúng vai trò, chưa bị khóa), và **không có danh tính mặc định để mượn**.
3. **Phạm vi dữ liệu:** `owner_id` được **tiêm** vào MỌI tool ở tầng `_run` (kể cả tool đọc), **ghi đè** giá trị client gửi lên — nên tool mới thêm sau này không thể vô tình đọc dữ liệu của HR khác.

Bổ sung: cổng 8001 **cố ý không publish ra host**. Đây là service nội bộ, chỉ container `api` gọi qua tên `mcp` trong Docker network. Publish ra host là mở một cửa đi thẳng vào dữ liệu tuyển dụng, không qua đăng nhập và không qua JWT.

### 9.5 Bề mặt tối giản & mọi tool chạy ngoài event loop

- Server chỉ phơi `tools/list` + `tools/call`. **Không** resource, **không** prompt, **không** `instructions` — HireWise không có luồng "client chat đa dụng ở ngoài tự đi tìm dữ liệu"; chính `agent.py` chọn tool và soạn prompt. Giữ `instructions` lại còn là bản sao thứ hai của SYSTEM_PROMPT, đúng kiểu hai bản mô tả song song rồi trôi lệch.
- FastMCP gọi tool đồng bộ **thẳng trên event loop**, mà tool ở đây là code chặn (query DB, gọi LLM, `sleep` của rate limiter). Để nguyên thì một lượt sinh câu hỏi cho 8 ứng viên giữ event loop hàng chục giây → client thứ hai không được đọc request, `/healthz` không trả lời (Docker đánh dấu unhealthy), stream Streamable HTTP không gửi nổi keep-alive nên phiên đứt giữa chừng. Giải pháp: mọi tool là `async def` và đẩy phần chặn qua `anyio.to_thread.run_sync`.

### 9.6 Đường fallback và bài toán "hỏng giữa lượt"

Nếu MCP server không kết nối được → agent tự động quay về gọi thẳng hàm Python in-process (schema sinh từ **cùng** registry nên LLM thấy y hệt ở hai đường) → sản phẩm không chết giữa demo.

Nhưng nếu MCP chết **sau khi một tool GHI đã chạy xong**, hệ thống **không** chạy lại cả lượt — làm vậy sẽ tạo JD lần hai, gửi email lần hai. Trường hợp đó báo lỗi trung thực cho HR. Đây chính là chỗ annotation `read_only` được dùng thật.

Client MCP còn: phân biệt **lỗi kết nối** (→ fallback) với **lỗi nghiệp vụ** (→ trả cho LLM tự xử lý); **timeout riêng cho mỗi lời gọi tool** (150s, mặc định transport là 5 phút — đủ để một tool treo giữ luôn request của HR); **cache danh sách tool 300s**.

### 9.7 Vòng lặp agent (`agent.py`)

- Model chính `openai/gpt-oss-120b`, chuỗi dự phòng xếp theo **năng lực gọi tool giảm dần** — đã thử đặt model rút gọn lên đầu: nó **bịa ra ứng viên không tồn tại** ("Trần Văn A", "Nguyễn Thị B") thay vì dùng kết quả `search_candidates` vừa nhận.
- `MAX_STEPS=10` (số vòng gọi tool tối đa/lượt), `TURN_BUDGET=75s` (trần thời gian một lượt chat, tính cả thời gian chờ rate limit), `max_output=700` token (Groq trừ hạn mức theo token **yêu cầu**, để trống là mỗi lượt tự ăn thêm ngân sách không dùng tới).
- Groq SDK mặc định tự retry 429 hai lần **im lặng bên trong lời gọi** → tắt (`max_retries=0`) để tầng trên nhận lỗi ngay và tự quyết: đổi tài khoản, hoặc đổi model.
- Lịch sử hội thoại **dựng lại từ DB** (kèm ghi chú kết quả tool các lượt trước), không tin history do frontend gửi lên → agent nhớ đúng UUID/dữ liệu đã tra.
- Hậu xử lý: **xóa mọi UUID** khỏi câu trả lời (prompt đã dặn nhưng prompt chỉ là xác suất; model dự phòng vẫn in "Nguyễn Minh Khoa (ID: 6828d1a8-…)" — với HR đó là rác và còn mời gọi họ chép id vào lượt sau thay vì gọi tên người).
- SYSTEM_PROMPT có các quy tắc: chỉ gọi đúng tool cần (hỏi/tra cứu thì **cấm** kèm tool ghi); không bịa id/tên; tool trả `not_found`/`needs_confirmation` nghĩa là **chưa làm gì**; hành động không thu hồi được phải gọi lần đầu **không bật cờ confirm** để lấy bản xem trước, chờ HR đồng ý rồi mới gọi lại; trả lời tiếng Việt tối đa 1–2 câu, không in UUID.

### 9.8 Sự cố thật đã dẫn tới thiết kế rào chắn (slide "đắt" nhất của bài)

HR gõ: *"lấy 3 người có điểm cao nhất bỏ vào shortlist đặt tên là tiềm năng và đặt câu hỏi phỏng vấn mỗi người 3 câu"*. Chuỗi hỏng:
1. Agent gọi `compare_candidates` với `jd_id="Backend Developer"` → lỗi, vì vị trí thật tên "Backend Python" — chuỗi "Backend Developer" chính là **ví dụ trong mô tả schema** lúc đó, model lấy luôn làm dữ liệu.
2. Không có danh sách ứng viên, agent tự nghĩ ra `["Nguyễn Văn A", "Trần Thị B", "Lê Văn C"]`.
3. Hàm tra cứu so bằng `ILIKE %ref%` nên "Trần Thị B" khớp **"TRẦN THỊ BẢO NGỌC"** → thêm một người thật mà HR chưa từng nhắc vào shortlist, rồi sinh luôn 3 câu hỏi phỏng vấn cho người đó.
4. HR nhận câu trả lời: *"đã thêm … tuy nhiên không tìm thấy Nguyễn Văn A và Lê Văn C"*.

Từ đó sinh ra các rào chắn (đều có test khóa lại): bỏ dấu + so khớp theo ranh giới từ thay vì `%ref%`; tên khớp nhiều người → báo nhập nhằng chứ không tự chọn; **một tên sai thì chặn cả lô, không ghi gì**; tool ghi khử trùng danh sách trước khi thao tác; danh sách hỏng thì **không gọi AI** (khỏi đốt quota).

## 10. Chống rate limit LLM

Hạn mức Groq tính theo **tài khoản × model**, không theo tiến trình. Upload 1 ZIP 15 CV = ~45 lời gọi bắn ra gần như cùng lúc → 429 hàng loạt → retry mù → CV bị đánh FAILED.

Kiến trúc điều tiết:
- `rate_limiter.py` đếm request + token đã tiêu trong cửa sổ phút/ngày **trên Redis** — nơi duy nhất mọi container (`api`, `worker`, `mcp`) nhìn thấy chung. Mỗi tiến trình đếm riêng thì cộng lại vẫn vượt trần.
- Trước mỗi lời gọi phải **đặt chỗ trước** phần token ước tính; hết ngân sách thì **chờ** tới lúc cửa sổ mở lại thay vì bắn rồi ăn 429.
- Cửa sổ cố định (fixed window), chỉ dùng **85%** (`SAFETY_RATIO`) hạn mức thật để chừa sai số.
- **Pool nhiều tài khoản:** pipeline chấm CV dùng `GROQ_API_KEY_1` + `GROQ_API_KEY_2` (hai tài khoản riêng → ngân sách gấp đôi); khung chat dùng cả 3 key. Nhiều key **cùng một tài khoản** thì không tăng quota → có bước **khử trùng** key, vì nếu đếm thành hai ngân sách độc lập thì bộ đặt chỗ cấp phát gấp đôi rồi cả hai cùng đâm 429.
- Ba tuyến phòng thủ: (1) đặt chỗ token trước khi gọi → phần lớn 429 không xảy ra; (2) còn ăn 429 thì đọc `retry-after` của Groq và nghỉ đúng con số đó; (3) chờ quá lâu → ném `LLMBudgetExhausted` → Celery hẹn giờ chạy lại CV đó.
- `worker --concurrency=4` khớp với **4 "ngăn" ngân sách độc lập**: 2 tài khoản × 2 model.

## 11. KẾT QUẢ TEST — SỐ LIỆU THẬT

Chạy: `docker exec hirewise_mcp python -m pytest /app/tests -q` → **82 passed, 0 failed** (1.93 giây).

| File test | Số test | Loại | Nội dung kiểm thử |
|---|---|---|---|
| `test_agent_tools_guards.py` | **18** | Unit (rào chắn) | Nhóm ứng viên trải nhiều vị trí thì hỏi lại và **không ghi gì**; AI chấm hỏng thì **không ghi điểm 0**; không ghi đè câu đã có câu trả lời; số câu trả lời > số câu hỏi thì từ chối; hết quota mà chưa làm gì thì nói thẳng; **đã ghi dữ liệu rồi mới chết thì phải nói ra**; bỏ UUID khỏi câu trả lời không được làm mất ai khỏi danh sách. |
| `test_agent_tools_resolve.py` | **20** | Unit (tra cứu) | Bỏ dấu & hoa–thường không làm trượt tên; gọi tắt hợp lệ vẫn khớp; **tên giữ chỗ ("Nguyễn Văn A") không khớp ai**; tiền tố giữa từ không còn được coi là khớp; tên khớp nhiều người → báo nhập nhằng; `add_to_shortlist` **chặn cả lô dù chỉ một tên sai**; danh sách hỏng thì **không gọi AI**. |
| `test_mcp_contract.py` | **16** | Contract | Mọi tool trong registry đều có trên MCP; MCP **không có tool lạ**; schema hai đường khớp nhau (tên tham số + tham số bắt buộc); **không tool nào còn tham số danh tính**; mọi tool chạy ngoài event loop; bề mặt chỉ gồm tool; không lộ tham số tiêm ra LLM; mọi tool trả `dict`; tool ghi không bị đánh dấu `read_only`; annotation lên tới MCP; **hành động không đảo ngược đều có rào xác nhận**; SYSTEM_PROMPT chỉ nhắc tool có thật. |
| `test_mcp_runtime.py` | **28** | Runtime invariant | Thiếu/sai token → **401**; token đúng tiền tố vẫn bị từ chối; `/healthz` không cần token; id không phải UUID / không ứng tài khoản nào / sai vai trò / **tài khoản bị khóa** → từ chối; không header → từ chối; **không còn danh tính dùng chung**; **`owner_id` do client gửi lên bị vứt đi**; `user_bound` được tiêm từ danh tính; lỗi hệ thống → `ToolError` còn lỗi nghiệp vụ vẫn là kết quả bình thường; danh tính hỏng thì **không gọi tool**; tool `health` không bao giờ đến tay LLM; tham số nội bộ bị lọc khỏi schema của LLM. |
| **TỔNG** | **82** | | **82 passed / 0 failed** |

Đặc điểm bộ test: **không cần DB, không cần mạng, không tốn token AI** — mọi thứ đụng hạ tầng đều thay bằng bản giả (fake/stub). Nhờ vậy chạy trong ~2 giây trên bất kỳ máy nào.

Quy mô mã nguồn: ~11.600 dòng Python (backend + MCP server), chưa tính frontend.

---

# D. CẤU TRÚC SLIDE (khoảng 38–42 slide)

**Phần 0 — Mở đầu**
1. Bìa: **HireWise — Hệ thống hỗ trợ tuyển dụng ứng dụng AI Agent & MCP**. Các dòng Môn học / Lớp / GVHD / Nhóm thực hiện để `add_todo_box`.
2. Mục lục (8 phần).

**Phần 1 — Ý tưởng & bài toán** (slide chuyển chương trước)
3. Bối cảnh & vấn đề.
4. Ý tưởng giải pháp — **vẽ sơ đồ 7 bước theo chiều ngang** (7 ô + mũi tên).
5. Điểm khác biệt / tính mới.
6. Đối tượng người dùng & phạm vi đề tài.

**Phần 2 — Yêu cầu**
7. Functional Requirements — bảng mã FR-xx, nhóm theo module (Auth/RBAC, JD, Upload & chấm CV, Leaderboard & so sánh, Shortlist & quyết định, Email, Phỏng vấn, Copilot AI, Admin & log).
8. Functional Requirements (tiếp).
9. **Non-Functional Requirements** — bảng mã NFR-xx, lấy từ chính các quyết định kỹ thuật có thật: hiệu năng (chấm CV bất đồng bộ; cache tool list 300s; timeout tool 150s; TURN_BUDGET 75s), độ tin cậy (healthcheck, prestart migration, fallback MCP, Celery retry 12 lần có jitter, không lặp side-effect sau tool ghi), bảo mật (JWT, RBAC, bcrypt, OTP, MCP bearer token, header danh tính xác minh lại, `owner_id` tiêm ở tầng dưới, cổng 8001 không publish), toàn vẹn dữ liệu (unique index, xóa mềm, audit log, timestamptz), bảo trì (một nguồn sự thật cho tool, 82 test, 20 migration), khả dụng (tiếng Việt, agent điều hướng UI, lỗi phân biệt tạm thời/vĩnh viễn), chi phí (rate limiter Redis, gộp 3→2 lượt LLM/CV, pool nhiều tài khoản).
10. NFR (tiếp) nếu tràn.
11. Ràng buộc & giả định (free tier LLM, chạy Docker Compose một máy, CV phải là PDF có text — file scan/ảnh sẽ FAILED).

**Phần 3 — Use Case Model**
12. **Use Case Diagram** — actor `HR Staff`, `Admin` hai bên, khung "HireWise System" ở giữa chứa các oval use case, thêm actor phụ `Email Service (SMTP)` và `LLM Provider (Groq)`.
13. Bảng danh sách use case (mã UC-xx, tên, actor, mô tả ngắn).
14. Đặc tả chi tiết **UC "Upload & chấm điểm CV hàng loạt"** (tiền điều kiện, luồng chính, luồng thay thế: CV trùng / CV không đọc được text / hết quota LLM, hậu điều kiện) — trình bày dạng bảng 2 cột.
15. Đặc tả chi tiết **UC "Trò chuyện với Copilot để thao tác dữ liệu"** — dùng đúng câu lệnh thật ở mục 9.8, luồng thay thế "tên nhập nhằng → hỏi lại, không ghi gì" và "MCP mất kết nối → fallback".

**Phần 4 — Architecture**
16. **Sơ đồ kiến trúc 6 service Docker** — vẽ shape: frontend → api → mcp → db; worker ↔ redis; ghi rõ cổng publish, và ghi chú nổi bật "8001 KHÔNG publish".
17. Kiến trúc phân lớp backend (Routers → Services → Models/DB), nhóm service: `ai_agent`, `cv_processing`, `data_ingestion`, `email`, `logging`.
18. Tech stack theo tầng (bảng hoặc các ô xếp tầng).
19. **Luồng dữ liệu chấm CV** — sơ đồ từ ZIP tới Evaluation, phân biệt rõ phần đồng bộ và phần qua Celery/Redis.

**Phần 5 — Class Diagram**
20. Class Diagram lõi tuyển dụng: `User`, `JobDescription`, `UploadBatch`, `Candidate`, `CandidateSkill`, `CandidateProject`, `Evaluation`, `EvaluationOverride` — đủ thuộc tính chính + bội số.
21. Class Diagram shortlist – phỏng vấn – email: `Shortlist`, `ShortlistItem`, `Interview`, `InterviewQuestion`, `EmailTemplate`, `EmailTemplateAttachment`.
22. Class Diagram AI & nhật ký: `ChatSession`, `ChatMessage`, `AgentToolLog`, `AILog`, `SystemLog`, `AuditLog`, `Notification`.
23. Class Diagram tầng service AI (không phải bảng DB): `ToolSpec`/`Param` (registry) — `MCPClient` — `AgentLoop` — `RateLimiter` — `Pipeline`/`Parser`/`Scorer`, có quan hệ "sinh ra schema cho".

**Phần 6 — Sequence Diagram** (mỗi slide một sơ đồ, vẽ bằng lifeline + mũi tên)
24. **Upload ZIP → chấm điểm CV**: HR → Frontend → API → ingestion → DB → Redis → Celery Worker → LLM → DB. Có khung `alt` cho "CV trùng" và cho `LLMBudgetExhausted → retry`.
25. **Một lượt chat Copilot đi qua MCP**: HR → CopilotChat → `POST /agent/chat` → chat_store dựng history → agent loop → `tools/list` → LLM chọn tool → `tools/call` (kèm `X-HireWise-Actor`) → MCP server xác minh danh tính + tiêm `owner_id` → agent_tools → DB → kết quả về LLM → trả lời + lệnh điều hướng UI.
26. **MCP mất kết nối**: nhánh fallback in-process, và nhánh "đã có tool GHI chạy xong → KHÔNG chạy lại, báo lỗi trung thực".
27. **Sinh câu hỏi phỏng vấn & chốt kết quả + gửi email** — thể hiện rõ **hai pha xác nhận** (gọi lần đầu không bật cờ → xem trước → HR đồng ý → gọi lại kèm cờ).
28. **Đăng ký & xác minh email OTP**.

**Phần 7 — MCP (chương riêng, bắt buộc)**
29. MCP là gì, vì sao chọn (mục 9.1) + sơ đồ chuỗi `run_agent → mcp_client → MCP server → agent_tools → DB`.
30. Vấn đề "hai bản mô tả tool song song rồi trôi lệch" → một nguồn sự thật `tool_registry` (sơ đồ 1 registry → 2 nhánh).
31. Bảng 20 tool kèm annotation — **tô màu nền ô** phân biệt: read-only (xanh nhạt), ghi (vàng nhạt), destructive/open_world (đỏ nhạt).
32. Ba lớp bảo mật của MCP server + lý do không publish cổng 8001 (vẽ 3 lớp lồng nhau).
33. Bề mặt tối giản + bài học event loop (`anyio.to_thread`).
34. Đường fallback & bài toán "hỏng giữa lượt" (idempotency của side-effect).
35. **Case study sự cố thật** ở mục 9.8 → 4 bước hỏng vẽ thành chuỗi, rồi 5 rào chắn sinh ra từ nó.

**Phần 8 — Kết quả**
36. **Bảng kết quả test**: 4 dòng theo 4 file (18/20/16/28) + dòng TỔNG **82 passed / 0 failed**, cột "Loại kiểm thử". Ghi rõ lệnh chạy và thời gian 1.93s.
37. Đặc điểm bộ test (không cần DB/mạng/token AI) + quy mô mã nguồn ~11.600 dòng Python, 21 bảng, 20 migration, 20 tool MCP — trình bày dạng các ô số liệu lớn.
38. `add_todo_box`: bảng **kiểm thử thủ công / UAT** (Mã TC, Chức năng, Bước thực hiện, Kết quả mong đợi, Kết quả thực tế, Đạt/Không) — 6 dòng trống.
39. `add_todo_box`: **ảnh chụp màn hình sản phẩm** — lưới 6 ô viền đứt có caption sẵn: Dashboard, Chi tiết vị trí + Leaderboard, Copilot chat, Shortlisting, Phỏng vấn, Cổng quản trị.
40. `add_todo_box`: **số liệu hiệu năng** (thời gian chấm 1 CV, xử lý ZIP 15 CV, độ trễ một lượt chat, token/CV) — bảng rỗng.
41. Hạn chế & hướng phát triển (CV scan/ảnh chưa OCR; free tier LLM giới hạn quota; MCP token dùng chung cấp hệ thống chứ chưa cấp riêng từng client; chưa có tìm kiếm ngữ nghĩa/vector; chưa phân quyền theo phòng ban).
42. Kết luận + Q&A.

Ưu tiên **đủ nội dung** hơn là đủ đúng con số slide.

Bắt đầu viết code và tạo file ngay, không cần hỏi lại tôi. Đặt tên file `HireWise_BaoCao.pptx`.

---
