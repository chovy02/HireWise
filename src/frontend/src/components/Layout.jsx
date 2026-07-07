import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar.jsx'
import CopilotChat from './CopilotChat.jsx'
import { useAuth } from '../context/AuthContext.jsx'

// App shell: app bình thường (Sidebar + nội dung) ở bên trái | AI Copilot ở cột
// phải ~1/5 (chỉ khi đã đăng nhập). Chat bên phải điều khiển/điều hướng phần app
// bên trái, nhưng HR vẫn thao tác trực tiếp bên trái như thường.
export default function Layout() {
  const { user } = useAuth()
  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col overflow-hidden">
          <Outlet />
        </div>
      </div>
      {user && <CopilotChat />}
    </div>
  )
}
