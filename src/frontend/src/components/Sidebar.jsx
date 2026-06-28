import { NavLink, Link } from 'react-router-dom'
import { useState } from 'react'
import {
  LayoutDashboard,
  Users,
  ShieldCheck,
  Settings,
  LogOut,
  LogIn,
  UserPlus,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext.jsx'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/shortlisting', label: 'Shortlisting', icon: Users },
  { to: '/admin', label: 'Admin Gateway', icon: ShieldCheck },
]

export default function Sidebar() {
  const { user, signOut } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)

  const displayName = user?.name || 'User'
  const initials = displayName
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <aside className="flex h-screen w-60 flex-shrink-0 flex-col bg-sidebar text-slate-300">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 text-lg font-bold text-white">
          A
        </div>
        <span className="text-[15px] font-semibold text-white">HireWise</span>
      </div>

      {/* Nav */}
      <nav className="mt-2 flex-1 space-y-1 px-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
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
          <>
            {menuOpen && (
              <div className="absolute bottom-16 left-3 right-3 overflow-hidden rounded-lg border border-white/10 bg-sidebar-hover shadow-lg">
                <button
                  onClick={signOut}
                  className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5"
                >
                  <LogOut size={16} /> Sign out
                </button>
              </div>
            )}
            <div className="flex items-center gap-3 rounded-lg px-2 py-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-700 text-xs font-semibold text-white">
                {initials}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-white">
                  {displayName}
                </p>
                <p className="truncate text-xs text-slate-500">
                  {user.email || 'HR Director'}
                </p>
              </div>
              <button
                onClick={() => setMenuOpen((v) => !v)}
                className="rounded-md p-1.5 text-slate-400 hover:bg-white/5 hover:text-white"
                title="Account settings"
              >
                <Settings size={18} />
              </button>
            </div>
          </>
        ) : (
          <div className="space-y-2">
            <Link
              to="/login"
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700"
            >
              <LogIn size={16} /> Sign in
            </Link>
            <Link
              to="/signup"
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-white/10 px-3 py-2.5 text-sm font-medium text-slate-300 transition-colors hover:bg-white/5 hover:text-white"
            >
              <UserPlus size={16} /> Sign up
            </Link>
          </div>
        )}
      </div>
    </aside>
  )
}
