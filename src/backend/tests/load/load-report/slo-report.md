# Báo cáo SLO thời gian phản hồi — HireWise

*Sinh lúc 2026-08-17T22:22:58+07:00. Mọi con số tính bằng mili-giây; kết luận dựa trên phân vị 95.*

**Kết luận chung: ĐẠT** — đo 25 endpoint, đạt 25, không đạt 0.


## A · tra cứu tức thời

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| `GET /agent/sessions` | 34 | 5 | 8 | 8 | 8 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /auth/me` | 20 | 10 | 15 | 15 | 15 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /email-templates` | 15 | 6 | 11 | 11 | 11 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds` | 151 | 6 | 16 | 17 | 18 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/trash` | 29 | 5 | 7 | 8 | 8 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}` | 102 | 5 | 8 | 13 | 14 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}/shortlists` | 94 | 6 | 16 | 20 | 20 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}/uploads` | 31 | 6 | 8 | 9 | 9 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /notifications` | 138 | 4 | 8 | 9 | 11 | 300 | 0.0% | 0.0% | ĐẠT |

## B · truy vấn tổng hợp

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| `GET /admin/ai-logs` | 12 | 16 | 20 | 20 | 20 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /admin/ai-metrics` | 21 | 10 | 23 | 28 | 28 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /admin/audit-logs` | 6 | 10 | 10 | 10 | 10 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /admin/business-metrics` | 21 | 6 | 20 | 26 | 26 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /admin/system-logs` | 12 | 9 | 23 | 23 | 23 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /candidates/{id}` | 94 | 6 | 9 | 16 | 16 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /interviews/candidate/{id}` | 94 | 5 | 7 | 13 | 13 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}/candidates` | 310 | 10 | 30 | 34 | 38 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /shortlists/{id}` | 51 | 7 | 10 | 14 | 14 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /users` | 5 | 12 | 13 | 13 | 13 | 800 | 0.0% | 0.0% | ĐẠT |

## C · ghi dữ liệu

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| `DELETE /shortlists/{id}` | 48 | 8 | 11 | 16 | 16 | 1000 | 0.0% | 0.0% | ĐẠT |
| `DELETE /shortlists/{id}/items/{item}` | 48 | 6 | 8 | 9 | 9 | 1000 | 0.0% | 0.0% | ĐẠT |
| `PATCH /shortlists/{id}/items/{item}` | 48 | 59 | 67 | 72 | 72 | 1000 | 0.0% | 0.0% | ĐẠT |
| `POST /jds/{id}/shortlists` | 48 | 13 | 58 | 64 | 64 | 1000 | 0.0% | 0.0% | ĐẠT |
| `POST /shortlists/{id}/items` | 48 | 56 | 66 | 67 | 67 | 1000 | 0.0% | 0.0% | ĐẠT |

## D · xác thực (bcrypt)

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| `POST /auth/login` | 20 | 213 | 231 | 231 | 231 | 1200 | 0.0% | 0.0% | ĐẠT |

## Ghi chú

- `GET /auth/me` — giải mã JWT + 1 truy vấn theo email
- `GET /jds` — danh sách dự án + đếm ứng viên gộp 1 query
- `GET /notifications` — chuông thông báo, gọi mỗi lần đổi trang
- `GET /candidates/{id}` — kèm raw_text CV + đánh giá chi tiết
- `GET /interviews/candidate/{id}` — 404 khi chưa có buổi PV là hợp lệ
- `GET /jds/{id}/candidates` — giao diện POLL endpoint này khi đang upload
- `PATCH /shortlists/{id}/items/{item}` — HR chốt nhận/loại
- `POST /auth/login` — bcrypt 12 vòng nằm trong đường đi
