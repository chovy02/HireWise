import { createContext, useContext, useEffect, useState } from 'react'
import { getToken, setToken } from '../api/client.js'
import * as authApi from '../api/auth.js'

const AuthContext = createContext(null)

const USER_KEY = 'autorecruit_user'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const raw = localStorage.getItem(USER_KEY)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  })

  // While true, a stored token is being verified against the backend.
  const [loading, setLoading] = useState(() => Boolean(getToken()))

  // Keep the cached user object in sync with localStorage.
  useEffect(() => {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
    else localStorage.removeItem(USER_KEY)
  }, [user])

  // On mount: if a token is stored, verify it's still valid by fetching the
  // current user from /auth/me. An expired/invalid token clears the session
  // so the UI never trusts a stale localStorage token.
  useEffect(() => {
    let cancelled = false
    async function verifyToken() {
      if (!getToken()) return
      try {
        const me = await authApi.me()
        if (!cancelled) setUser(me)
      } catch {
        if (!cancelled) {
          setToken(null)
          setUser(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    verifyToken()
    return () => {
      cancelled = true
    }
  }, [])

  async function signIn(credentials) {
    const data = await authApi.login(credentials)
    setToken(data.access_token)
    setUser(data.user)
    return data
  }

  function signOut() {
    setToken(null)
    setUser(null)
  }

  // Trộn thông tin mới vào user đang cache (dùng sau khi tự đổi tên ở trang Quản lý
  // tài khoản). Không gọi lại /auth/me: response của PATCH đã là bản mới nhất, và
  // thiếu bước này thì Sidebar vẫn hiện tên cũ cho tới lần F5 kế tiếp.
  function updateUser(patch) {
    setUser((prev) => (prev ? { ...prev, ...patch } : prev))
  }

  const value = {
    user,
    loading,
    isAuthenticated: Boolean(user),
    signIn,
    signOut,
    updateUser,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
