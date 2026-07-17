import { Outlet, Navigate, useLocation } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import Sidebar from './Sidebar.jsx'
import CopilotChat from './CopilotChat.jsx'
import { useAuth } from '../context/AuthContext.jsx'

// App shell: app bình thường (Sidebar + nội dung) ở bên trái | AI Copilot ở cột
// phải ~1/5. Chat bên phải điều khiển/điều hướng phần app bên trái, nhưng HR vẫn
// thao tác trực tiếp bên trái như thường.
//
// Buộc đăng nhập: mọi trang trong shell đều yêu cầu đã đăng nhập. Chưa đăng nhập
// -> đẩy về /login (nhớ đường đang vào để quay lại sau khi đăng nhập).
export default function Layout() {
  const { user, loading } = useAuth()
  const location = useLocation()

  // Đang xác thực token đã lưu -> chờ, tránh chớp màn hình login rồi lại vào app.
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-canvas text-slate-400">
        <Loader2 size={22} className="mr-2 animate-spin" /> Đang tải…
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col overflow-hidden">
          <Outlet />
        </div>
      </div>
      <CopilotChat />
    </div>
  )
}
