import { apiFetch, apiFetchBlob } from './client.js'

// ---- Giám sát & quản trị hệ thống (Admin). Maps tới src/backend/app/routers/admin.py ----
// Mọi endpoint yêu cầu role admin (backend chặn 403 nếu không phải admin).

// GET /admin/system-logs?limit=N -> [SystemLogResponse]
// Log đăng nhập + hành động quản trị (NFR-8), mới nhất trước.
export function getSystemLogs(limit = 200) {
  return apiFetch(`/admin/system-logs?limit=${limit}`, { auth: true })
}

// Bỏ qua các giá trị rỗng/null để không gửi `?agent_name=` (backend sẽ coi chuỗi
// rỗng là một bộ lọc thật và trả về 0 dòng).
function qs(params) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  return sp.toString()
}

// ---- Giám sát AI (AI Monitoring) ----

// GET /admin/ai-metrics?hours=N
// -> { total_requests, error_rate, avg_latency_ms, total_tokens, max_latency_ms,
//      tool_calls, tool_errors, by_agent: [{ agent_name, requests, errors, ... }] }
// `hours` bỏ trống = toàn bộ lịch sử.
export function getAiMetrics({ hours } = {}) {
  return apiFetch(`/admin/ai-metrics?${qs({ hours })}`, { auth: true })
}

// GET /admin/ai-logs?limit&agent_name&status&hours&q -> [AILogResponse]
// status: 'success' | 'error' | bỏ trống (tất cả).
export function getAiLogs({ limit = 100, agentName, status, hours, q } = {}) {
  const query = qs({ limit, agent_name: agentName, status, hours, q })
  return apiFetch(`/admin/ai-logs?${query}`, { auth: true })
}

// GET /admin/agent-tool-logs?limit&tool_name&status&hours -> [AgentToolLogResponse]
// Lượt AI Agent GỌI TOOL nghiệp vụ — khác với lượt gọi LLM ở /admin/ai-logs.
export function getAgentToolLogs({ limit = 100, toolName, status, hours } = {}) {
  const query = qs({ limit, tool_name: toolName, status, hours })
  return apiFetch(`/admin/agent-tool-logs?${query}`, { auth: true })
}

// ---- Kiểm toán & bảo mật (Audit Logs) ----

// GET /admin/audit-logs?limit&entity_type&action&hours&q -> [AuditLogResponse]
// Mỗi bản ghi kèm user_email + old_data/new_data (chỉ các trường thực sự đổi).
export function getAuditLogs({ limit = 100, entityType, action, hours, q } = {}) {
  const query = qs({ limit, entity_type: entityType, action, hours, q })
  return apiFetch(`/admin/audit-logs?${query}`, { auth: true })
}

// GET /admin/audit-filters -> { actions: [], entity_types: [] }
// Giá trị có thật trong bảng, để dropdown lọc không co lại khi đang lọc.
export function getAuditFilters() {
  return apiFetch('/admin/audit-filters', { auth: true })
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
