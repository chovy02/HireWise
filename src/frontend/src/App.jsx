import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Login from './pages/Login.jsx'
import SignUp from './pages/SignUp.jsx'
import VerifyEmail from './pages/VerifyEmail.jsx'
import Dashboard from './pages/Dashboard.jsx'
import CreateProject from './pages/CreateProject.jsx'
import ProjectDetail from './pages/ProjectDetail.jsx'
import Shortlisting from './pages/Shortlisting.jsx'
import AdminGateway from './pages/AdminGateway.jsx'
import { useAuth } from './context/AuthContext.jsx'

// RBAC route guard: nếu đã đăng nhập nhưng SAI role -> đẩy về "nhà" của role đó
// (admin -> /admin, hr -> /). Chưa đăng nhập thì vẫn render (giữ landing công khai);
// backend mới là lớp chặn thật, đây chỉ để tránh vào nhầm trang trống.
function RoleRoute({ allow, children }) {
  const { user } = useAuth()
  if (user && !allow.includes(user.role)) {
    return <Navigate to={user.role === 'admin' ? '/admin' : '/'} replace />
  }
  return children
}

export default function App() {
  return (
    <Routes>
      {/* ---- Public auth routes ---- */}
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<SignUp />} />
      <Route path="/verify" element={<VerifyEmail />} />

      {/* ---- Main app (sidebar shell). Recruitment = HR; Admin Gateway = admin. ---- */}
      <Route element={<Layout />}>
        <Route path="/" element={<RoleRoute allow={['hr_staff']}><Dashboard /></RoleRoute>} />
        <Route path="/projects/new" element={<RoleRoute allow={['hr_staff']}><CreateProject /></RoleRoute>} />
        <Route path="/projects/:id" element={<RoleRoute allow={['hr_staff']}><ProjectDetail /></RoleRoute>} />
        <Route path="/shortlisting" element={<RoleRoute allow={['hr_staff']}><Shortlisting /></RoleRoute>} />
        <Route path="/admin" element={<RoleRoute allow={['admin']}><AdminGateway /></RoleRoute>} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
