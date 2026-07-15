import { apiFetch } from './client.js'

// ---- AI Agent (copilot) API. Maps to src/backend/app/routers/agent.py ----

// POST /agent/chat  { message, session_id } -> { reply, tool_calls, steps, ui_actions, session_id }
// Lịch sử hội thoại do BACKEND lưu & dựng lại từ DB (chat_sessions/chat_messages),
// nên frontend chỉ cần gửi session_id — không gửi lại cả cục history nữa.
export function chatWithAgent(message, sessionId = null) {
  return apiFetch('/agent/chat', {
    method: 'POST',
    body: { message, session_id: sessionId },
    auth: true,
  })
}

// GET /agent/sessions -> [{ session_id, title, created_at }]  (mới nhất trước)
export function listChatSessions() {
  return apiFetch('/agent/sessions', { auth: true })
}

// GET /agent/sessions/{id} -> { session_id, messages: [{ role: 'user'|'ai', text }] }
export function getChatSession(sessionId) {
  return apiFetch(`/agent/sessions/${sessionId}`, { auth: true })
}

// DELETE /agent/sessions/{id}
export function deleteChatSession(sessionId) {
  return apiFetch(`/agent/sessions/${sessionId}`, { method: 'DELETE', auth: true })
}
