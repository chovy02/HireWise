# Báo cáo SLO thời gian phản hồi — HireWise

*Sinh lúc 2026-08-17T21:42:24+07:00. Mọi con số tính bằng mili-giây; kết luận dựa trên phân vị 95.*

**Kết luận chung: ĐẠT** — đo 25 endpoint, đạt 25, không đạt 0.


## A · tra cứu tức thời

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| `GET /agent/sessions` | 67 | 5 | 8 | 17 | 17 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /auth/me` | 20 | 8 | 25 | 25 | 25 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /email-templates` | 25 | 7 | 10 | 11 | 11 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds` | 169 | 7 | 20 | 34 | 35 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/trash` | 20 | 7 | 25 | 25 | 25 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}` | 179 | 6 | 9 | 16 | 17 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}/shortlists` | 133 | 7 | 18 | 22 | 23 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}/uploads` | 59 | 6 | 10 | 16 | 16 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /notifications` | 166 | 4 | 7 | 14 | 15 | 300 | 0.0% | 0.0% | ĐẠT |

## B · truy vấn tổng hợp

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| `GET /admin/ai-logs` | 17 | 32 | 51 | 51 | 51 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /admin/ai-metrics` | 26 | 11 | 19 | 51 | 51 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /admin/audit-logs` | 8 | 10 | 15 | 15 | 15 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /admin/business-metrics` | 26 | 6 | 9 | 31 | 31 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /admin/system-logs` | 17 | 8 | 18 | 18 | 18 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /candidates/{id}` | 145 | 7 | 10 | 13 | 18 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /interviews/candidate/{id}` | 145 | 5 | 7 | 9 | 13 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}/candidates` | 495 | 23 | 52 | 99 | 107 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /shortlists/{id}` | 181 | 15 | 22 | 26 | 30 | 800 | 0.0% | 0.0% | ĐẠT |
| `GET /users` | 15 | 7 | 18 | 18 | 18 | 800 | 0.0% | 0.0% | ĐẠT |

## C · ghi dữ liệu

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| `DELETE /shortlists/{id}` | 66 | 9 | 13 | 19 | 19 | 1000 | 0.0% | 0.0% | ĐẠT |
| `DELETE /shortlists/{id}/items/{item}` | 66 | 6 | 9 | 11 | 11 | 1000 | 0.0% | 0.0% | ĐẠT |
| `PATCH /shortlists/{id}/items/{item}` | 66 | 55 | 60 | 65 | 65 | 1000 | 0.0% | 0.0% | ĐẠT |
| `POST /jds/{id}/shortlists` | 66 | 13 | 53 | 55 | 55 | 1000 | 0.0% | 0.0% | ĐẠT |
| `POST /shortlists/{id}/items` | 66 | 54 | 61 | 106 | 106 | 1000 | 0.0% | 0.0% | ĐẠT |

## D · xác thực (bcrypt)

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| `POST /auth/login` | 20 | 228 | 263 | 263 | 263 | 1200 | 0.0% | 0.0% | ĐẠT |

## Ghi chú

- `GET /auth/me` — giải mã JWT + 1 truy vấn theo email
- `GET /jds` — danh sách dự án + đếm ứng viên gộp 1 query
- `GET /notifications` — chuông thông báo, gọi mỗi lần đổi trang
- `GET /candidates/{id}` — kèm raw_text CV + đánh giá chi tiết
- `GET /interviews/candidate/{id}` — 404 khi chưa có buổi PV là hợp lệ
- `GET /jds/{id}/candidates` — giao diện POLL endpoint này khi đang upload
- `PATCH /shortlists/{id}/items/{item}` — HR chốt nhận/loại
- `POST /auth/login` — bcrypt 12 vòng nằm trong đường đi
