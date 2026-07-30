import { NavLink, Link, useLocation } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import {
  LayoutDashboard,
  Users,
  Mail,
  Trash2,
  ShieldCheck,
  UserCog,
  ChevronUp,
  LogOut,
  LogIn,
  UserPlus,
  X,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext.jsx'

// RBAC: mỗi mục nav chỉ hiện cho đúng role (khớp phân quyền backend).
// HR làm pipeline tuyển dụng (Bảng điều khiển/Danh sách rút gọn); Admin quản trị.
const NAV_ITEMS = [
  { to: '/', label: 'Bảng điều khiển', icon: LayoutDashboard, end: true, roles: ['hr_staff'] },
  { to: '/shortlisting', label: 'Danh sách rút gọn', icon: Users, roles: ['hr_staff'] },
  { to: '/settings/email-templates', label: 'Mẫu email', icon: Mail, roles: ['hr_staff'] },
  { to: '/trash', label: 'Thùng rác', icon: Trash2, roles: ['hr_staff'] },
  { to: '/admin', label: 'Cổng quản trị', icon: ShieldCheck, roles: ['admin'] },
]

export default function Sidebar({ open = false, onClose }) {
  const { user, signOut } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const accountRef = useRef(null)
  const location = useLocation()

  // Bấm ra ngoài / Escape thì đóng menu. Trước đây menu chỉ đóng khi bấm lại đúng
  // nút răng cưa, nên nó nằm đè lên sidebar suốt cả lúc người dùng đã chuyển sang
  // làm việc khác.
  useEffect(() => {
    if (!menuOpen) return
    function onDoc(e) {
      if (accountRef.current && !accountRef.current.contains(e.target)) setMenuOpen(false)
    }
    function onKey(e) {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  // Đổi trang (bấm "Quản lý tài khoản") -> đóng menu, nếu không nó còn treo ở góc
  // sau khi trang mới đã hiện.
  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  // Đã đăng nhập -> chỉ hiện mục hợp role; chưa đăng nhập -> hiện tất cả (landing).
  const navItems = user
    ? NAV_ITEMS.filter((item) => item.roles.includes(user.role))
    : NAV_ITEMS

  const displayName = user?.name || 'Người dùng'
  const initials = displayName
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <aside
      className={[
        'flex h-screen w-60 flex-col bg-sidebar text-slate-300',
        // Mobile: ngăn kéo trượt từ trái, nằm trên nền mờ của Layout.
        'fixed inset-y-0 left-0 z-40 transform transition-transform duration-200',
        open ? 'translate-x-0' : '-translate-x-full',
        // md trở lên: trở lại cột cố định trong luồng, luôn hiện.
        'md:static md:translate-x-0 md:flex-shrink-0',
      ].join(' ')}
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 text-lg font-bold text-white">
          A
        </div>
        <span className="text-[15px] font-semibold text-white">HireWise</span>
        <button
          onClick={onClose}
          aria-label="Đóng menu điều hướng"
          className="ml-auto rounded-md p-1.5 text-slate-400 transition hover:bg-white/5 hover:text-white md:hidden"
        >
          <X size={18} />
        </button>
      </div>

      {/* Nav */}
      <nav className="mt-2 flex-1 space-y-1 px-3">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-sidebar-active text-white'
                  : 'text-slate-400 hover:bg-sidebar-hover hover:text-slate-200',
              ].join(' ')
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  className={isActive ? 'text-brand-light' : ''}
                  size={18}
                  strokeWidth={2}
                />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom: account area (logged out -> Sign in / Sign up) */}
      <div className="relative border-t border-white/5 px-3 py-3">
        {user ? (
          <div ref={accountRef}>
            {/* Menu tài khoản. Trước đây chỗ này chỉ có nút răng cưa mở ra đúng một
                mục "Đăng xuất" — một cái nút riêng cho một hành động, trong khi cả
                khối tên (rộng gấp mười lần) lại không bấm được. Giờ chính khối tên
                là nút, và menu chứa cả "Quản lý tài khoản". */}
            {menuOpen && (
              <div
                role="menu"
                className="absolute bottom-[72px] left-3 right-3 overflow-hidden rounded-lg border border-white/10 bg-sidebar-hover shadow-lg shadow-black/30"
              >
                <NavLink
                  to="/settings/account"
                  role="menuitem"
                  className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5"
                >
                  <UserCog size={16} /> Quản lý tài khoản
                </NavLink>
                <button
                  onClick={signOut}
                  role="menuitem"
                  className="flex w-full items-center gap-2 border-t border-white/5 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5"
                >
                  <LogOut size={16} /> Đăng xuất
                </button>
              </div>
            )}
            <button
              onClick={() => setMenuOpen((v) => !v)}
              title="Tài khoản của tôi"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              className={`flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors ${
                menuOpen ? 'bg-sidebar-active' : 'hover:bg-sidebar-hover'
              }`}
            >
              <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-slate-700 text-xs font-semibold text-white">
                {initials}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-white">
                  {displayName}
                </p>
                <p className="truncate text-xs text-slate-500">{user.email}</p>
              </div>
              <ChevronUp
                size={16}
                className={`flex-shrink-0 text-slate-400 transition-transform duration-200 ${
                  menuOpen ? 'rotate-180' : ''
                }`}
              />
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            <Link
              to="/login"
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700"
            >
              <LogIn size={16} /> Đăng nhập
            </Link>
            <Link
              to="/signup"
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-white/10 px-3 py-2.5 text-sm font-medium text-slate-300 transition-colors hover:bg-white/5 hover:text-white"
            >
              <UserPlus size={16} /> Đăng ký
            </Link>
          </div>
        )}
      </div>
    </aside>
  )
}
