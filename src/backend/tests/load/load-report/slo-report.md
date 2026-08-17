# Báo cáo SLO thời gian phản hồi — HireWise

<<<<<<< HEAD
*Sinh lúc 2026-08-17T22:22:58+07:00. Mọi con số tính bằng mili-giây; kết luận dựa trên phân vị 95.*
=======
*Sinh lúc 2026-08-17T21:42:24+07:00. Mọi con số tính bằng mili-giây; kết luận dựa trên phân vị 95.*
>>>>>>> ea2aecef4b3bd642178893aa4d8773da6f74a43a

**Kết luận chung: ĐẠT** — đo 25 endpoint, đạt 25, không đạt 0.


## A · tra cứu tức thời

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
<<<<<<< HEAD
| `GET /agent/sessions` | 34 | 5 | 8 | 8 | 8 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /auth/me` | 20 | 10 | 15 | 15 | 15 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /email-templates` | 15 | 6 | 11 | 11 | 11 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds` | 151 | 6 | 16 | 17 | 18 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/trash` | 29 | 5 | 7 | 8 | 8 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}` | 102 | 5 | 8 | 13 | 14 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}/shortlists` | 94 | 6 | 16 | 20 | 20 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}/uploads` | 31 | 6 | 8 | 9 | 9 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /notifications` | 138 | 4 | 8 | 9 | 11 | 300 | 0.0% | 0.0% | ĐẠT |
=======
| `GET /agent/sessions` | 67 | 5 | 8 | 17 | 17 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /auth/me` | 20 | 8 | 25 | 25 | 25 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /email-templates` | 25 | 7 | 10 | 11 | 11 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds` | 169 | 7 | 20 | 34 | 35 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/trash` | 20 | 7 | 25 | 25 | 25 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}` | 179 | 6 | 9 | 16 | 17 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}/shortlists` | 133 | 7 | 18 | 22 | 23 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /jds/{id}/uploads` | 59 | 6 | 10 | 16 | 16 | 300 | 0.0% | 0.0% | ĐẠT |
| `GET /notifications` | 166 | 4 | 7 | 14 | 15 | 300 | 0.0% | 0.0% | ĐẠT |
>>>>>>> ea2aecef4b3bd642178893aa4d8773da6f74a43a

## B · truy vấn tổng hợp

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
<<<<<<< HEAD
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
=======
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
>>>>>>> ea2aecef4b3bd642178893aa4d8773da6f74a43a

## C · ghi dữ liệu

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
<<<<<<< HEAD
| `DELETE /shortlists/{id}` | 48 | 8 | 11 | 16 | 16 | 1000 | 0.0% | 0.0% | ĐẠT |
| `DELETE /shortlists/{id}/items/{item}` | 48 | 6 | 8 | 9 | 9 | 1000 | 0.0% | 0.0% | ĐẠT |
| `PATCH /shortlists/{id}/items/{item}` | 48 | 59 | 67 | 72 | 72 | 1000 | 0.0% | 0.0% | ĐẠT |
| `POST /jds/{id}/shortlists` | 48 | 13 | 58 | 64 | 64 | 1000 | 0.0% | 0.0% | ĐẠT |
| `POST /shortlists/{id}/items` | 48 | 56 | 66 | 67 | 67 | 1000 | 0.0% | 0.0% | ĐẠT |
=======
| `DELETE /shortlists/{id}` | 66 | 9 | 13 | 19 | 19 | 1000 | 0.0% | 0.0% | ĐẠT |
| `DELETE /shortlists/{id}/items/{item}` | 66 | 6 | 9 | 11 | 11 | 1000 | 0.0% | 0.0% | ĐẠT |
| `PATCH /shortlists/{id}/items/{item}` | 66 | 55 | 60 | 65 | 65 | 1000 | 0.0% | 0.0% | ĐẠT |
| `POST /jds/{id}/shortlists` | 66 | 13 | 53 | 55 | 55 | 1000 | 0.0% | 0.0% | ĐẠT |
| `POST /shortlists/{id}/items` | 66 | 54 | 61 | 106 | 106 | 1000 | 0.0% | 0.0% | ĐẠT |
>>>>>>> ea2aecef4b3bd642178893aa4d8773da6f74a43a

## D · xác thực (bcrypt)

| Endpoint | n | p50 | p95 | p99 | max | Ngân sách | Vượt SLO | Lỗi HTTP | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
<<<<<<< HEAD
| `POST /auth/login` | 20 | 213 | 231 | 231 | 231 | 1200 | 0.0% | 0.0% | ĐẠT |
=======
| `POST /auth/login` | 20 | 228 | 263 | 263 | 263 | 1200 | 0.0% | 0.0% | ĐẠT |
>>>>>>> ea2aecef4b3bd642178893aa4d8773da6f74a43a

## Ghi chú

- `GET /auth/me` — giải mã JWT + 1 truy vấn theo email
- `GET /jds` — danh sách dự án + đếm ứng viên gộp 1 query
- `GET /notifications` — chuông thông báo, gọi mỗi lần đổi trang
- `GET /candidates/{id}` — kèm raw_text CV + đánh giá chi tiết
- `GET /interviews/candidate/{id}` — 404 khi chưa có buổi PV là hợp lệ
- `GET /jds/{id}/candidates` — giao diện POLL endpoint này khi đang upload
- `PATCH /shortlists/{id}/items/{item}` — HR chốt nhận/loại
- `POST /auth/login` — bcrypt 12 vòng nằm trong đường đi
