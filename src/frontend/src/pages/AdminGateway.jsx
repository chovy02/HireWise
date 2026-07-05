import { useEffect, useState } from 'react'
import {
  ShieldCheck,
  Users,
  UserCog,
  UserPlus,
  Pencil,
  Lock,
  Unlock,
  ScrollText,
  RefreshCw,
  Search,
  X,
  Loader2,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  StatCard,
  Badge,
  Segmented,
  PrimaryButton,
  SecondaryButton,
} from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { listUsers, createUser, updateUser } from '../api/users.js'
import { getSystemLogs } from '../api/admin.js'

const ROLE_META = {
  admin: { label: 'Admin', variant: 'ai' },
  hr_staff: { label: 'HR Staff', variant: 'processing' },
}
const LEVEL_VARIANT = {
  INFO: 'neutral',
  WARNING: 'processing',
  ERROR: 'error',
  CRITICAL: 'error',
}
const inputCls =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

export default function AdminGateway() {
  const [tab, setTab] = useState('users')

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900">
              <ShieldCheck size={24} className="text-indigo-600" />
              Admin Gateway
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Quản lý tài khoản người dùng và giám sát hoạt động hệ thống.
            </p>
          </div>
          <Segmented
            options={[
              { value: 'users', label: 'Tài khoản' },
              { value: 'logs', label: 'Nhật ký hệ thống' },
            ]}
            value={tab}
            onChange={setTab}
          />
        </div>

        {tab === 'users' ? <UserManagement /> : <SystemLogs />}
      </main>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Tab 1: User Management (RBAC - FR-1)                                 */
/* ------------------------------------------------------------------ */
function UserManagement() {
  const toast = useToast()
  const { user: me } = useAuth()
  const [users, setUsers] = useState(null) // null = đang tải
  const [err, setErr] = useState('')
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState(null) // user obj (sửa) | 'new' (tạo) | null

  function load() {
    setErr('')
    listUsers()
      .then(setUsers)
      .catch((e) => setErr(e.message))
  }
  useEffect(load, [])

  const list = users || []
  const visible = list.filter((u) =>
    query.trim()
      ? `${u.name || ''} ${u.email}`.toLowerCase().includes(query.trim().toLowerCase())
      : true
  )
  const total = list.length
  const active = list.filter((u) => u.is_active).length
  const admins = list.filter((u) => u.role === 'admin').length
  const hrStaff = list.filter((u) => u.role === 'hr_staff').length

  async function toggleActive(u) {
    try {
      await updateUser(u.id, { is_active: !u.is_active })
      toast(u.is_active ? `Đã khóa ${u.email}` : `Đã mở khóa ${u.email}`)
      load()
    } catch (e) {
      toast(e.message)
    }
  }

  return (
    <>
      {/* Stats (dữ liệu THẬT từ /users) */}
      <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Users} label="Tổng tài khoản" value={users == null ? '…' : total} />
        <StatCard
          icon={Unlock}
          iconClass="bg-emerald-50 text-emerald-600"
          label="Đang hoạt động"
          value={users == null ? '…' : active}
        />
        <StatCard
          icon={ShieldCheck}
          iconClass="bg-indigo-50 text-indigo-600"
          label="Admin"
          value={users == null ? '…' : admins}
        />
        <StatCard
          icon={UserCog}
          iconClass="bg-violet-50 text-violet-600"
          label="HR Staff"
          value={users == null ? '…' : hrStaff}
        />
      </div>

      {/* Toolbar */}
      <Card className="mt-6 flex flex-wrap items-center gap-3 p-3">
        <div className="flex flex-1 items-center gap-2">
          <Search size={18} className="ml-2 flex-shrink-0 text-slate-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tìm theo tên hoặc email…"
            className="w-full flex-1 bg-transparent text-sm text-slate-700 placeholder-slate-400 outline-none"
          />
        </div>
        <PrimaryButton onClick={() => setEditing('new')}>
          <UserPlus size={16} /> Thêm tài khoản
        </PrimaryButton>
      </Card>

      {/* Table */}
      <Card className="mt-5 overflow-hidden">
        {users === null && !err && (
          <p className="px-6 py-10 text-sm text-slate-400">Đang tải tài khoản…</p>
        )}
        {err && <p className="px-6 py-10 text-sm text-red-500">Lỗi tải: {err}</p>}
        {users && visible.length === 0 && (
          <p className="px-6 py-10 text-sm text-slate-400">Không có tài khoản phù hợp.</p>
        )}
        {users && visible.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left">
              <thead>
                <tr className="border-b border-slate-200 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  <th className="px-6 py-3">Tài khoản</th>
                  <th className="px-6 py-3">Vai trò</th>
                  <th className="px-6 py-3">Trạng thái</th>
                  <th className="px-6 py-3 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {visible.map((u) => {
                  const role = ROLE_META[u.role] || { label: u.role, variant: 'neutral' }
                  const isSelf = me?.id === u.id
                  return (
                    <tr key={u.id} className="hover:bg-slate-50/60">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-indigo-50 text-sm font-semibold text-indigo-600">
                            {(u.name || u.email || '?')[0].toUpperCase()}
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="truncate text-sm font-semibold text-slate-900">
                                {u.name || '—'}
                              </span>
                              {isSelf && (
                                <Badge variant="neutral" upper={false}>
                                  Bạn
                                </Badge>
                              )}
                            </div>
                            <p className="truncate text-xs text-slate-400">{u.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <Badge variant={role.variant} upper={false}>
                          {role.label}
                        </Badge>
                      </td>
                      <td className="px-6 py-4">
                        {u.is_active ? (
                          <Badge variant="completed" upper={false}>
                            Hoạt động
                          </Badge>
                        ) : (
                          <Badge variant="error" upper={false}>
                            Đã khóa
                          </Badge>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => setEditing(u)}
                            className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 transition hover:bg-slate-50"
                            title="Sửa tài khoản"
                          >
                            <Pencil size={16} />
                          </button>
                          <button
                            onClick={() => toggleActive(u)}
                            disabled={isSelf}
                            className={`rounded-lg border p-2 transition disabled:cursor-not-allowed disabled:opacity-40 ${
                              u.is_active
                                ? 'border-red-200 bg-white text-red-500 hover:bg-red-50'
                                : 'border-emerald-200 bg-white text-emerald-600 hover:bg-emerald-50'
                            }`}
                            title={
                              isSelf
                                ? 'Không thể tự khóa tài khoản của mình'
                                : u.is_active
                                  ? 'Khóa tài khoản'
                                  : 'Mở khóa tài khoản'
                            }
                          >
                            {u.is_active ? <Lock size={16} /> : <Unlock size={16} />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {editing && (
        <UserFormModal
          user={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            load()
          }}
        />
      )}
    </>
  )
}

function UserFormModal({ user, onClose, onSaved }) {
  const toast = useToast()
  const isNew = !user
  const [username, setUsername] = useState(user?.name || '')
  const [email, setEmail] = useState(user?.email || '')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState(user?.role || 'hr_staff')
  const [isActive, setIsActive] = useState(user?.is_active ?? true)
  const [saving, setSaving] = useState(false)

  async function save() {
    if (!username.trim() || !email.trim()) {
      toast('Nhập đủ tên và email.')
      return
    }
    if (isNew && password.length < 8) {
      toast('Mật khẩu tối thiểu 8 ký tự.')
      return
    }
    if (!isNew && password && password.length < 8) {
      toast('Mật khẩu mới tối thiểu 8 ký tự.')
      return
    }
    setSaving(true)
    try {
      if (isNew) {
        await createUser({ username: username.trim(), email: email.trim(), password, role })
        toast('Đã tạo tài khoản.')
      } else {
        const patch = { username: username.trim(), email: email.trim(), role, is_active: isActive }
        if (password) patch.password = password
        await updateUser(user.id, patch)
        toast('Đã cập nhật tài khoản.')
      }
      onSaved()
    } catch (e) {
      toast(e.message || 'Lưu thất bại.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-base font-bold text-slate-900">
            {isNew ? 'Thêm tài khoản' : 'Sửa tài khoản'}
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Họ tên
            </label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} className={`mt-1.5 ${inputCls}`} />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={`mt-1.5 ${inputCls}`}
            />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {isNew ? 'Mật khẩu (≥ 8 ký tự)' : 'Mật khẩu mới (để trống nếu giữ nguyên)'}
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isNew ? '' : '••••••••'}
              className={`mt-1.5 ${inputCls}`}
            />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Vai trò
            </label>
            <select value={role} onChange={(e) => setRole(e.target.value)} className={`mt-1.5 ${inputCls}`}>
              <option value="hr_staff">HR Staff</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          {!isNew && (
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              Tài khoản đang hoạt động
            </label>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4">
          <SecondaryButton className="px-3 py-2" onClick={onClose} disabled={saving}>
            Hủy
          </SecondaryButton>
          <PrimaryButton className="px-3 py-2" onClick={save} disabled={saving}>
            {saving ? (
              <>
                <Loader2 size={15} className="animate-spin" /> Đang lưu…
              </>
            ) : isNew ? (
              'Tạo tài khoản'
            ) : (
              'Lưu thay đổi'
            )}
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Tab 2: System Logs (NFR-8)                                          */
/* ------------------------------------------------------------------ */
function SystemLogs() {
  const [logs, setLogs] = useState(null)
  const [err, setErr] = useState('')

  function load() {
    setErr('')
    setLogs(null)
    getSystemLogs()
      .then(setLogs)
      .catch((e) => setErr(e.message))
  }
  useEffect(load, [])

  return (
    <Card className="mt-6 overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <ScrollText size={16} className="text-indigo-600" /> Nhật ký hệ thống
        </h2>
        <button
          onClick={load}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-50"
        >
          <RefreshCw size={14} /> Tải lại
        </button>
      </div>

      {logs === null && !err && (
        <p className="px-6 py-10 text-sm text-slate-400">Đang tải nhật ký…</p>
      )}
      {err && <p className="px-6 py-10 text-sm text-red-500">Lỗi tải: {err}</p>}
      {logs && logs.length === 0 && (
        <p className="px-6 py-10 text-sm text-slate-400">Chưa có nhật ký nào.</p>
      )}
      {logs && logs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left">
            <thead>
              <tr className="border-b border-slate-200 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                <th className="px-6 py-3">Thời gian</th>
                <th className="px-6 py-3">Mức</th>
                <th className="px-6 py-3">Module</th>
                <th className="px-6 py-3">Nội dung</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {logs.map((l) => (
                <tr key={l.id} className="hover:bg-slate-50/60">
                  <td className="whitespace-nowrap px-6 py-3 text-xs text-slate-500">
                    {new Date(l.created_at).toLocaleString('vi-VN')}
                  </td>
                  <td className="px-6 py-3">
                    <Badge variant={LEVEL_VARIANT[l.level] || 'neutral'} upper={false}>
                      {l.level}
                    </Badge>
                  </td>
                  <td className="px-6 py-3 text-sm text-slate-600">{l.module}</td>
                  <td className="px-6 py-3 text-sm text-slate-700">{l.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
