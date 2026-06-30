import { Navigate, useLocation } from 'react-router-dom'
import { getToken } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'

// Guards the dashboard routes. If there's no token, bounce to /login.
export default function ProtectedRoute({ children }) {
  const location = useLocation()
  const { loading } = useAuth()

  // Don't redirect while a stored token is still being verified against
  // /auth/me — otherwise a valid session would flash to /login on reload.
  if (loading) return null

  if (!getToken()) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  return children
}
