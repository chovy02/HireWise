import { apiFetch } from './client.js'

// ---- Auth API calls. These map 1:1 to src/backend/app/routers/auth.py ----

// POST /auth/register  -> { message }
// Backend schema (UserCreate): { username, email, password }
export function register({ name, email, password }) {
  return apiFetch('/auth/register', {
    method: 'POST',
    body: { username: name, email, password },
  })
}

// POST /auth/verify-email -> { message }
// Backend schema (VerifyEmail): { email, token }
// `token` là mã OTP 6 chữ số gửi qua email (trước đây là JWT dài). Vì mã ngắn và
// không tự mang danh tính, backend cần `email` đi kèm để biết đối chiếu tài khoản nào.
export function verifyEmail({ email, token }) {
  return apiFetch('/auth/verify-email', {
    method: 'POST',
    body: { email, token },
  })
}

// POST /auth/resend-code -> { message }
// Backend schema (ResendCode): { email }. Trả về cùng một message dù email có tồn
// tại hay không, nên đừng suy ra trạng thái tài khoản từ phản hồi.
export function resendCode(email) {
  return apiFetch('/auth/resend-code', {
    method: 'POST',
    body: { email },
  })
}

// POST /auth/login -> { access_token, token_type, user: { id, name, email } }
// Backend schema (UserLogin): { email, password }
export function login({ email, password }) {
  return apiFetch('/auth/login', {
    method: 'POST',
    body: { email, password },
  })
}

// GET /auth/me -> { id, name, email, role, is_active, created_at }
// Sends the stored Bearer token; used on app load to verify the session is
// still valid (throws if the token is missing, expired, or invalid).
export function me() {
  return apiFetch('/auth/me', { auth: true })
}
