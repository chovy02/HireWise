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
// Backend schema (VerifyEmail): { token }
export function verifyEmail(token) {
  return apiFetch('/auth/verify-email', {
    method: 'POST',
    body: { token },
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
