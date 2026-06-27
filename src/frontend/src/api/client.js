// Tiny fetch wrapper around the FastAPI backend.
//
// In dev, requests go to relative paths (e.g. "/auth/login") which Vite proxies
// to http://localhost:8000 (see vite.config.js). In prod set VITE_API_BASE.
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

const TOKEN_KEY = 'autorecruit_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

/**
 * Make a JSON request to the API.
 * Throws an Error with a readable `.message` (from FastAPI's `detail`) on failure.
 */
export async function apiFetch(path, { method = 'GET', body, auth = false } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  let res
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (networkErr) {
    throw new Error(
      'Cannot reach the server. Make sure the backend is running on port 8000.'
    )
  }

  let data = null
  const text = await res.text()
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { detail: text }
    }
  }

  if (!res.ok) {
    const detail = data?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg).join(', ')
          : `Request failed (${res.status})`
    throw new Error(message)
  }

  return data
}
