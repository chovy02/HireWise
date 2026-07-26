import { useEffect, useState } from 'react'
import { Outlet, Navigate, useLocation } from 'react-router-dom'
import { Loader2, Menu, Sparkles } from 'lucide-react'
import Sidebar from './Sidebar.jsx'
import CopilotChat from './CopilotChat.jsx'
import { useAuth } from '../context/AuthContext.jsx'

// App shell: app bình thường (Sidebar + nội dung) ở bên trái | AI Copilot ở cột
// phải ~1/5. Chat bên phải điều khiển/điều hướng phần app bên trái, nhưng HR vẫn
// thao tác trực tiếp bên trái như thường.
//
// Copilot CHỈ dành cho HR: mọi tool của nó đều là nghiệp vụ tuyển dụng (tạo JD, tra
// ứng viên, mở shortlist) — những việc admin không làm (SRS 2.4). Ở trang Admin nó
// chỉ chiếm 1/5 màn hình mà không dùng được việc gì, nên không render.
//
// MÀN HÌNH HẸP: sidebar (240px) + Copilot (tối thiểu 280px) chiếm hết bề ngang máy
// điện thoại, đẩy toàn bộ nội dung trang ra ngoài khung nhìn. Dưới md sidebar thành
// ngăn kéo trượt, dưới lg Copilot thành lớp phủ toàn màn hình; cả hai mở bằng thanh
// công cụ chỉ hiện trên mobile bên dưới.
//
// Buộc đăng nhập: mọi trang trong shell đều yêu cầu đã đăng nhập. Chưa đăng nhập
// -> đẩy về /login (nhớ đường đang vào để quay lại sau khi đăng nhập).
export default function Layout() {
  const { user, loading } = useAuth()
  const location = useLocation()

  const [navOpen, setNavOpen] = useState(false)
  const [copilotOpen, setCopilotOpen] = useState(false)

  // Chuyển trang (thường là do bấm một mục trong ngăn kéo) -> đóng lớp phủ, nếu
  // không người dùng bị kẹt nhìn menu che mất trang vừa mở.
  useEffect(() => {
    setNavOpen(false)
    setCopilotOpen(false)
  }, [location.pathname])

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

  const showCopilot = user.role !== 'admin'

  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      {/* Nền mờ khi ngăn kéo mở trên mobile — bấm ra ngoài để đóng. */}
      {(navOpen || copilotOpen) && (
        <div
          onClick={() => {
            setNavOpen(false)
            setCopilotOpen(false)
          }}
          className="fixed inset-0 z-30 bg-slate-900/50 md:hidden"
          aria-hidden="true"
        />
      )}

      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Thanh công cụ cho màn hình hẹp: nơi duy nhất mở được sidebar/Copilot khi
            chúng đã bị ẩn. Đặt ở Layout (không phải Topbar) vì CreateProject và
            ProjectDetail tự dựng header riêng, không dùng Topbar.

            Thanh ẩn ở lg (không phải md) vì hai thứ nó mở có hai ngưỡng KHÁC NHAU:
            sidebar quay lại từ md, còn Copilot mãi tới lg. Nếu ẩn cả thanh ở md thì
            khoảng 768–1023px sẽ không có Copilot lẫn nút mở nó — mất hẳn tính năng
            chính trên máy tính bảng. Vì vậy ở md thanh vẫn còn nhưng chỉ giữ nút
            Copilot; nút hamburger tự ẩn khi sidebar đã hiện. */}
        <div
          className={[
            'flex flex-shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-4 py-2.5',
            // Admin không có Copilot -> thanh chỉ phục vụ hamburger, bỏ hẳn từ md.
            // HR còn nút Copilot nên thanh phải sống tới lg (và căn phải khi
            // hamburger đã biến mất, tránh chừa khoảng trống bên trái).
            showCopilot ? 'md:justify-end lg:hidden' : 'md:hidden',
          ].join(' ')}
        >
          <button
            onClick={() => setNavOpen(true)}
            aria-label="Mở menu điều hướng"
            className="rounded-lg p-2 text-slate-600 transition hover:bg-slate-100 md:hidden"
          >
            <Menu size={20} />
          </button>
          <span className="text-sm font-semibold text-slate-900 md:hidden">
            HireWise
          </span>
          {showCopilot && (
            <button
              onClick={() => setCopilotOpen(true)}
              aria-label="Mở AI Copilot"
              className="ml-auto rounded-lg p-2 text-slate-600 transition hover:bg-slate-100 md:ml-0"
            >
              <Sparkles size={20} />
            </button>
          )}
        </div>

        <Outlet />
      </div>

      {showCopilot && (
        <CopilotChat open={copilotOpen} onClose={() => setCopilotOpen(false)} />
      )}
    </div>
  )
}
