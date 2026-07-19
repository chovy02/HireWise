import { apiFetch, apiFetchBlob } from './client.js'

// ---- Giám sát & quản trị hệ thống (Admin). Maps tới src/backend/app/routers/admin.py ----
// Mọi endpoint yêu cầu role admin (backend chặn 403 nếu không phải admin).

// GET /admin/system-logs?limit=N -> [SystemLogResponse]
// Log đăng nhập + hành động quản trị (NFR-8), mới nhất trước.
export function getSystemLogs(limit = 200) {
  return apiFetch(`/admin/system-logs?limit=${limit}`, { auth: true })
}

// ---- Giám sát AI (AI Monitoring) ----

// GET /admin/ai-metrics -> { total_requests, error_rate, avg_latency_ms, total_tokens }
export function getAiMetrics() {
  return apiFetch('/admin/ai-metrics', { auth: true })
}

// GET /admin/ai-logs?limit=N -> [AILogResponse]
export function getAiLogs(limit = 100) {
  return apiFetch(`/admin/ai-logs?limit=${limit}`, { auth: true })
}

// ---- Cấu hình hệ thống động (System Configuration) ----

// GET /admin/settings -> [SystemSettingResponse]
export function getSystemSettings() {
  return apiFetch('/admin/settings', { auth: true })
}

// PUT /admin/settings/{key} { value } -> SystemSettingResponse
export function updateSystemSetting(key, value) {
  return apiFetch(`/admin/settings/${encodeURIComponent(key)}`, {
    method: 'PUT',
    body: { value },
    auth: true,
  })
}

// ---- Kiểm toán & bảo mật (Audit Logs) ----

// GET /admin/audit-logs?limit=N&entity_type=... -> [AuditLogResponse]
export function getAuditLogs(limit = 100, entityType) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (entityType) params.set('entity_type', entityType)
  return apiFetch(`/admin/audit-logs?${params.toString()}`, { auth: true })
}

// ---- Phân tích doanh nghiệp (Business Analytics) ----

// GET /admin/business-metrics -> { total_jds, active_jds, total_candidates, total_interviews, avg_candidate_score }
export function getBusinessMetrics() {
  return apiFetch('/admin/business-metrics', { auth: true })
}

// ---- Trung tâm thông báo (Broadcast Notifications) ----

// GET /admin/notifications -> [NotificationResponse]
export function getNotifications() {
  return apiFetch('/admin/notifications', { auth: true })
}

// POST /admin/notifications { title, message, type, is_active } -> NotificationResponse
export function createNotification(payload) {
  return apiFetch('/admin/notifications', {
    method: 'POST',
    body: payload,
    auth: true,
  })
}

// PUT /admin/notifications/{id}/toggle -> NotificationResponse
export function toggleNotification(id) {
  return apiFetch(`/admin/notifications/${id}/toggle`, {
    method: 'PUT',
    auth: true,
  })
}

// ---- Trung tâm trích xuất (Export Center) ----
// Tải file CSV về máy (kèm Bearer token qua blob rồi trigger download).
export async function downloadExport(kind, filename) {
  const blob = await apiFetchBlob(`/admin/export/${kind}`, { auth: true })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
