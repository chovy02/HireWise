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

  // Keep the cached user object in sync with localStorage.
  useEffect(() => {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
    else localStorage.removeItem(USER_KEY)
  }, [user])

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

  const value = {
    user,
    isAuthenticated: Boolean(getToken()),
    signIn,
    signOut,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
