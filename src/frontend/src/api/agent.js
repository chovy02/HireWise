import { apiFetch } from './client.js'

// ---- AI Agent (copilot) API. Maps to src/backend/app/routers/agent.py ----

// POST /agent/chat  { message, history } -> { reply, tool_calls, steps, ui_actions }
// `history`: mảng { role: 'user'|'assistant', content } của các lượt trước để nối phiên.
export function chatWithAgent(message, history = []) {
  return apiFetch('/agent/chat', {
    method: 'POST',
    body: { message, history },
    auth: true,
  })
}
