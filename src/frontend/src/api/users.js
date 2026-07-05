import { apiFetch } from './client.js'

// ---- Quản lý tài khoản (Admin). Maps 1:1 tới src/backend/app/routers/users.py ----
// Mọi endpoint yêu cầu role admin (backend chặn 403 nếu không phải admin).

// GET /users -> [UserResponse]
export function listUsers() {
  return apiFetch('/users', { auth: true })
}

// POST /users  { username, email, password, role } -> UserResponse
export function createUser({ username, email, password, role }) {
  return apiFetch('/users', {
    method: 'POST',
    body: { username, email, password, role },
    auth: true,
  })
}

// PUT /users/{id}  { username?, email?, role?, is_active?, password? } -> UserResponse
export function updateUser(userId, patch) {
  return apiFetch(`/users/${userId}`, { method: 'PUT', body: patch, auth: true })
}

// PATCH /users/{id}/deactivate -> UserResponse
export function deactivateUser(userId) {
  return apiFetch(`/users/${userId}/deactivate`, { method: 'PATCH', auth: true })
}
