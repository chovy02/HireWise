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
 * Fetch a binary response (e.g. a PDF) as a Blob, sending the Bearer token.
 * Used for embedding files an <iframe> can't auth for on its own.
 */
export async function apiFetchBlob(path, { auth = true } = {}) {
  const headers = {}
  if (auth) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  let res
  try {
    res = await fetch(`${API_BASE}${path}`, { headers })
  } catch {
    throw new Error(
      'Cannot reach the server. Make sure the backend is running on port 8000.'
    )
  }

  if (!res.ok) {
    // Lỗi thường trả JSON { detail }, thử đọc để hiện thông báo dễ hiểu.
    let detail = `Request failed (${res.status})`
    try {
      const data = await res.json()
      if (typeof data?.detail === 'string') detail = data.detail
    } catch {
      /* body không phải JSON — giữ message mặc định */
    }
    throw new Error(detail)
  }

  return res.blob()
}

/**
 * Make a JSON request to the API.
 * Throws an Error with a readable `.message` (from FastAPI's `detail`) on failure.
 */
export async function apiFetch(path, { method = 'GET', body, auth = false } = {}) {
  // FormData (file upload) must NOT be JSON-stringified; the browser sets its own
  // multipart Content-Type with a boundary, so we leave the header off.
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData

  const headers = {}
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  if (auth) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  let res
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
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
