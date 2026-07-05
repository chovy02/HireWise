import { apiFetch } from './client.js'

// ---- Giám sát hệ thống (Admin). Maps tới src/backend/app/routers/admin.py ----

// GET /admin/system-logs?limit=N -> [SystemLogResponse]
// Log đăng nhập + hành động quản trị (NFR-8), mới nhất trước.
export function getSystemLogs(limit = 200) {
  return apiFetch(`/admin/system-logs?limit=${limit}`, { auth: true })
}
