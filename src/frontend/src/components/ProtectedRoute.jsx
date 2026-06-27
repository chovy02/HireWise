import { Navigate, useLocation } from 'react-router-dom'
import { getToken } from '../api/client.js'

// Guards the dashboard routes. If there's no token, bounce to /login.
export default function ProtectedRoute({ children }) {
  const location = useLocation()
  if (!getToken()) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  return children
}
