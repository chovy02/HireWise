import { useEffect, useMemo, useState } from 'react'
import {
  ShieldCheck,
  Users,
  UserPlus,
  Pencil,
  Lock,
  Unlock,
  ScrollText,
  RefreshCw,
  Search,
  X,
  Loader2,
  Cpu,
  Activity,
  Zap,
  AlertTriangle,
  Coins,
  Gauge,
  FileSearch,
  Megaphone,
  Send,
  Download,
  BarChart3,
  Briefcase,
  MessagesSquare,
  ChevronRight,
  FileSpreadsheet,
  Wrench,
  Trash2,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  CardHeader,
  StateRow,
  StatCard,
  Badge,
  ScoreRing,
  ProgressBar,
  Dropdown,
  Segmented,
  PrimaryButton,
  SecondaryButton,
  PageHeader,
} from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { listUsers, createUser, updateUser } from '../api/users.js'
import {
  getSystemLogs,
  getAiMetrics,
  getAiLogs,
  getAgentToolLogs,
  getAuditLogs,
  getAuditFilters,
  getBusinessMetrics,
  getNotifications,
  createNotification,
  deleteNotification,
  downloadExport,
} from '../api/admin.js'

const ROLE_META = {
  admin: { label: 'Admin', variant: 'ai' },
  hr_staff: { label: 'HR Staff', variant: 'processing' },
}
const LEVEL_VARIANT = {
  INFO: 'neutral',
  WARNING: 'warning',
  ERROR: 'error',
  CRITICAL: 'error',
}
const NOTI_VARIANT = {
  info: 'info',
  success: 'success',
  warning: 'warning',
  error: 'error',
}
const inputCls =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'
// Ô lọc trên thanh công cụ (select + input tìm kiếm) — hẹp hơn inputCls, không w-full.
const selectCls =
  'rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400'

// Cửa sổ thời gian dùng chung cho Giám sát AI và Kiểm toán. Giá trị = số giờ,
// chuỗi rỗng = không giới hạn (backend hiểu "bỏ trống" là toàn bộ lịch sử).
const TIME_WINDOWS = [
  { value: '', label: 'Toàn bộ' },
  { value: '24', label: '24 giờ qua' },
  { value: '168', label: '7 ngày qua' },
  { value: '720', label: '30 ngày qua' },
]

// Nhãn tiếng Việt cho action/entity trong audit_logs. Thiếu nhãn thì hiện thẳng mã
// gốc (vd action mới thêm ở backend) chứ không để trống.
const AUDIT_ACTION_LABEL = {
  CREATE_USER: 'Tạo tài khoản',
  UPDATE_USER: 'Cập nhật tài khoản',
  BAN_USER: 'Khóa tài khoản',
  CREATE_JD: 'Tạo vị trí tuyển dụng',
  OVERRIDE_EVALUATION: 'Ghi đè điểm AI',
  DELETE_SHORTLIST: 'Xóa shortlist',
  UPDATE_CANDIDATE_STATUS: 'Đổi trạng thái ứng viên',
  CREATE_NOTIFICATION: 'Phát thông báo',
  DELETE_NOTIFICATION: 'Xóa thông báo',
  // Cơ chế ẩn/hiện đã bỏ; giữ nhãn để các bản ghi kiểm toán CŨ vẫn đọc được.
  TOGGLE_NOTIFICATION: 'Bật/tắt thông báo',
}
const AUDIT_ACTION_VARIANT = {
  BAN_USER: 'error',
  DELETE_SHORTLIST: 'error',
  OVERRIDE_EVALUATION: 'warning',
  UPDATE_USER: 'warning',
  CREATE_USER: 'success',
  CREATE_JD: 'info',
  CREATE_NOTIFICATION: 'info',
  DELETE_NOTIFICATION: 'error',
  TOGGLE_NOTIFICATION: 'neutral',
  UPDATE_CANDIDATE_STATUS: 'processing',
}
const ENTITY_LABEL = {
  user: 'Tài khoản',
  job_description: 'Vị trí tuyển dụng',
  evaluation: 'Đánh giá',
  shortlist: 'Shortlist',
  shortlist_item: 'Ứng viên trong shortlist',
  notification: 'Thông báo',
}

// JSONB trả về có thể là object, mảng, hoặc null -> in đẹp, null thành gạch ngang.
function jsonText(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

// Các mục quản trị — hiển thị dưới dạng dropdown ở sidebar (thay tab cũ).
const SECTIONS = [
  { value: 'users', label: 'Tài khoản', icon: Users, title: 'Quản lý tài khoản', desc: 'RBAC — tạo, sửa, khóa tài khoản người dùng.', hIcon: Users, hClass: 'bg-indigo-50 text-indigo-600' },
  { value: 'analytics', label: 'Phân tích doanh nghiệp', icon: BarChart3, title: 'Phân tích doanh nghiệp', desc: 'Số liệu tổng quan hiệu quả tuyển dụng.', hIcon: BarChart3, hClass: 'bg-violet-50 text-violet-600' },
  { value: 'ai', label: 'Giám sát AI', icon: Cpu, title: 'Giám sát AI', desc: 'Theo dõi request, độ trễ, token và lỗi của các AI agent.', hIcon: Cpu, hClass: 'bg-sky-50 text-sky-600' },
  { value: 'audit', label: 'Kiểm toán & Bảo mật', icon: FileSearch, title: 'Kiểm toán & Bảo mật', desc: 'Ai đã thay đổi gì — nhật ký before/after mọi hành động nhạy cảm.', hIcon: FileSearch, hClass: 'bg-rose-50 text-rose-600' },
  { value: 'notifications', label: 'Trung tâm thông báo', icon: Megaphone, title: 'Trung tâm thông báo', desc: 'Phát thông báo tới toàn bộ người dùng của hệ thống.', hIcon: Megaphone, hClass: 'bg-fuchsia-50 text-fuchsia-600' },
  { value: 'export', label: 'Trung tâm trích xuất', icon: Download, title: 'Trung tâm trích xuất', desc: 'Xuất nhật ký & dữ liệu hệ thống ra file CSV.', hIcon: Download, hClass: 'bg-emerald-50 text-emerald-600' },
  { value: 'logs', label: 'Nhật ký hệ thống', icon: ScrollText, title: 'Nhật ký hệ thống', desc: 'Log đăng nhập và hành động quản trị (NFR-8).', hIcon: ScrollText, hClass: 'bg-slate-100 text-slate-600' },
]

export default function AdminGateway() {
  const [section, setSection] = useState('users')
  const meta = SECTIONS.find((s) => s.value === section) || SECTIONS[0]

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        <PageHeader
          icon={meta.hIcon}
          iconClass={meta.hClass}
          title={meta.title}
          subtitle={meta.desc}
          action={
            <div className="flex items-center gap-2.5">
              <span className="hidden text-sm font-medium text-slate-500 lg:inline">
                Khu vực
              </span>
              <Dropdown
                align="right"
                className="min-w-[230px]"
                value={section}
                onChange={setSection}
                options={SECTIONS.map((s) => ({
                  value: s.value,
                  label: s.label,
                  icon: s.icon,
                }))}
              />
            </div>
          }
        />

        <div className="mt-6">
          {section === 'users' && <UserManagement />}
          {section === 'analytics' && <BusinessAnalytics />}
          {section === 'ai' && <AiMonitoring />}
          {section === 'audit' && <AuditSecurity />}
          {section === 'notifications' && <BroadcastNotifications />}
          {section === 'export' && <ExportCenter />}
          {section === 'logs' && <SystemLogs />}
        </div>
      </main>
    </>
  )
}

/* ================================================================== */
/* Tài khoản (RBAC - FR-1)                                            */
/* ================================================================== */
function UserManagement() {
  const toast = useToast()
  const { user: me } = useAuth()
  const [users, setUsers] = useState(null) // null = đang tải
  const [err, setErr] = useState('')
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState(null) // user obj (sửa) | 'new' (tạo) | null
  const [confirmBan, setConfirmBan] = useState(null) // user sắp bị khóa (chờ xác nhận) | null
  const [banning, setBanning] = useState(false)

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
  // "Đang hoạt động" = đã xác minh (is_active) VÀ không bị khóa (is_banned).
  const active = list.filter((u) => u.is_active && !u.is_banned).length
  const banned = list.filter((u) => u.is_banned).length
  const admins = list.filter((u) => u.role === 'admin').length

  // Áp dụng khóa/mở khóa: đổi is_banned (KHÔNG đụng is_active — vốn là cờ xác minh).
  async function applyBan(u, nextBanned) {
    setBanning(true)
    try {
      await updateUser(u.id, { is_banned: nextBanned })
      toast(nextBanned ? `Đã khóa ${u.email}` : `Đã mở khóa ${u.email}`)
      setConfirmBan(null)
      load()
    } catch (e) {
      toast(e.message)
    } finally {
      setBanning(false)
    }
  }

  // Bấm nút khóa: nếu đang khóa -> mở khóa ngay; nếu chưa -> hỏi xác nhận trước khi khóa.
  function onLockClick(u) {
    if (u.is_banned) applyBan(u, false)
    else setConfirmBan(u)
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Users} label="Tổng tài khoản" value={users == null ? '…' : total} />
        <StatCard
          icon={Unlock}
          iconClass="bg-emerald-50 text-emerald-600"
          label="Đang hoạt động"
          value={users == null ? '…' : active}
        />
        <StatCard
          icon={Lock}
          iconClass="bg-red-50 text-red-600"
          label="Đã khóa"
          value={users == null ? '…' : banned}
        />
        <StatCard
          icon={ShieldCheck}
          iconClass="bg-indigo-50 text-indigo-600"
          label="Admin"
          value={users == null ? '…' : admins}
        />
      </div>

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

      <Card className="mt-5 overflow-hidden">
        {users === null && !err && <StateRow>Đang tải tài khoản…</StateRow>}
        {err && <StateRow tone="error">Lỗi tải: {err}</StateRow>}
        {users && visible.length === 0 && <StateRow>Không có tài khoản phù hợp.</StateRow>}
        {users && visible.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/60 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
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
                        {u.is_banned ? (
                          <Badge variant="error" upper={false}>
                            Đã khóa
                          </Badge>
                        ) : u.is_active ? (
                          <Badge variant="completed" upper={false}>
                            Hoạt động
                          </Badge>
                        ) : (
                          <Badge variant="warning" upper={false}>
                            Chưa xác minh
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
                            onClick={() => onLockClick(u)}
                            disabled={isSelf}
                            className={`rounded-lg border p-2 transition disabled:cursor-not-allowed disabled:opacity-40 ${
                              u.is_banned
                                ? 'border-emerald-200 bg-white text-emerald-600 hover:bg-emerald-50'
                                : 'border-red-200 bg-white text-red-500 hover:bg-red-50'
                            }`}
                            title={
                              isSelf
                                ? 'Không thể tự khóa tài khoản của mình'
                                : u.is_banned
                                  ? 'Mở khóa tài khoản'
                                  : 'Khóa tài khoản'
                            }
                          >
                            {u.is_banned ? <Unlock size={16} /> : <Lock size={16} />}
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

      {confirmBan && (
        <Modal title="Xác nhận khóa tài khoản" onClose={() => (banning ? null : setConfirmBan(null))}>
          <div className="px-6 py-5">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-red-50 text-red-600">
                <Lock size={18} />
              </div>
              <div className="min-w-0">
                <p className="text-sm text-slate-700">
                  Bạn có chắc muốn khóa tài khoản{' '}
                  <span className="font-semibold text-slate-900">{confirmBan.email}</span>?
                </p>
                <p className="mt-1.5 text-sm text-slate-500">
                  Người dùng sẽ không thể đăng nhập cho tới khi được mở khóa. Hệ thống gửi email
                  báo cho họ biết kèm hướng dẫn khiếu nại. Bạn có thể mở khóa lại bất cứ lúc nào.
                </p>
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4">
            <SecondaryButton className="px-3 py-2" onClick={() => setConfirmBan(null)} disabled={banning}>
              Hủy
            </SecondaryButton>
            <button
              onClick={() => applyBan(confirmBan, true)}
              disabled={banning}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {banning ? (
                <>
                  <Loader2 size={15} className="animate-spin" /> Đang khóa…
                </>
              ) : (
                <>
                  <Lock size={15} /> Khóa tài khoản
                </>
              )}
            </button>
          </div>
        </Modal>
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
    <Modal title={isNew ? 'Thêm tài khoản' : 'Sửa tài khoản'} onClose={onClose}>
      <div className="space-y-4 px-6 py-5">
        <Field label="Họ tên">
          <input value={username} onChange={(e) => setUsername(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Email">
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} />
        </Field>
        <Field label={isNew ? 'Mật khẩu (≥ 8 ký tự)' : 'Mật khẩu mới (để trống nếu giữ nguyên)'}>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={isNew ? '' : '••••••••'}
            className={inputCls}
          />
        </Field>
        <Field label="Vai trò">
          <select value={role} onChange={(e) => setRole(e.target.value)} className={inputCls}>
            <option value="hr_staff">HR Staff</option>
            <option value="admin">Admin</option>
          </select>
        </Field>
        {!isNew && (
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            Đã xác minh (kích hoạt email)
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
    </Modal>
  )
}

/* ================================================================== */
/* Phân tích doanh nghiệp (Business Analytics)                        */
/* ================================================================== */
function BusinessAnalytics() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')

  function load() {
    setErr('')
    setData(null)
    getBusinessMetrics()
      .then(setData)
      .catch((e) => setErr(e.message))
  }
  useEffect(load, [])

  if (err) return <Card><StateRow tone="error">Lỗi tải số liệu: {err}</StateRow></Card>
  if (!data) return <Card><StateRow>Đang tải số liệu doanh nghiệp…</StateRow></Card>

  const jdFillPct = data.total_jds ? Math.round((data.active_jds / data.total_jds) * 100) : 0
  const avgScore = Math.round(data.avg_candidate_score || 0)

  const bars = [
    { label: 'Tổng vị trí (JD)', value: data.total_jds, color: 'indigo', icon: Briefcase },
    { label: 'Vị trí đang mở', value: data.active_jds, color: 'green', icon: Activity },
    { label: 'Tổng ứng viên', value: data.total_candidates, color: 'indigo', icon: Users },
    { label: 'Tổng phỏng vấn', value: data.total_interviews, color: 'green', icon: MessagesSquare },
  ]
  const maxBar = Math.max(1, ...bars.map((b) => b.value))

  return (
    <>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Briefcase} iconClass="bg-indigo-50 text-indigo-600" label="Vị trí tuyển dụng" value={data.total_jds} footnote={`${data.active_jds} đang mở`} />
        <StatCard icon={Users} iconClass="bg-violet-50 text-violet-600" label="Tổng ứng viên" value={data.total_candidates} footnote="Đã tiếp nhận & chấm điểm" />
        <StatCard icon={MessagesSquare} iconClass="bg-sky-50 text-sky-600" label="Buổi phỏng vấn AI" value={data.total_interviews} footnote="Đã thực hiện" />
        <StatCard icon={Gauge} iconClass="bg-emerald-50 text-emerald-600" label="Điểm phù hợp TB" value={avgScore} footnote="Trên thang 100" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="p-6 lg:col-span-2">
          <h3 className="text-base font-semibold text-slate-900">Tổng quan hoạt động</h3>
          <p className="mt-1 text-sm text-slate-500">So sánh các chỉ số tuyển dụng chính.</p>
          <div className="mt-5 space-y-4">
            {bars.map((b) => (
              <div key={b.label}>
                <div className="mb-1.5 flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-slate-600">
                    <b.icon size={15} className="text-slate-400" /> {b.label}
                  </span>
                  <span className="font-semibold text-slate-800">{b.value}</span>
                </div>
                <ProgressBar value={(b.value / maxBar) * 100} color={b.color} />
              </div>
            ))}
          </div>
        </Card>

        <Card className="flex flex-col items-center justify-center p-6 text-center">
          <h3 className="text-base font-semibold text-slate-900">Điểm phù hợp trung bình</h3>
          <div className="my-5">
            <ScoreRing value={avgScore} size={120} />
          </div>
          <p className="text-sm text-slate-500">
            Chất lượng ứng viên trung bình do AI đánh giá trên toàn hệ thống.
          </p>
          <div className="mt-4 w-full rounded-lg bg-slate-50 px-4 py-3 text-left">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-500">Tỷ lệ vị trí đang mở</span>
              <span className="font-semibold text-slate-800">{jdFillPct}%</span>
            </div>
            <div className="mt-2">
              <ProgressBar value={jdFillPct} color="green" />
            </div>
          </div>
        </Card>
      </div>
    </>
  )
}

/* ================================================================== */
/* Giám sát AI (AI Monitoring)                                        */
/* ================================================================== */
function AiMonitoring() {
  // 'llm'   = lượt gọi model sinh chữ (bảng ai_logs)
  // 'tools' = lượt Agent gọi tool nghiệp vụ (bảng agent_tool_logs)
  const [view, setView] = useState('llm')
  const [hours, setHours] = useState('')   // '' = toàn bộ lịch sử
  const [nonce, setNonce] = useState(0)    // bấm "Tải lại" -> ép chạy lại effect

  const [metrics, setMetrics] = useState(null)
  const [logs, setLogs] = useState(null)
  const [toolLogs, setToolLogs] = useState(null)
  const [err, setErr] = useState('')

  const [agent, setAgent] = useState('')
  const [tool, setTool] = useState('')
  const [toolOptions, setToolOptions] = useState([])
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')

  const [openLog, setOpenLog] = useState(null)
  const [openTool, setOpenTool] = useState(null)

  // Gõ tới đâu gọi API tới đó sẽ bắn một request mỗi phím; đợi 400ms ngừng gõ.
  useEffect(() => {
    const id = setTimeout(() => setQ(search.trim()), 400)
    return () => clearTimeout(id)
  }, [search])

  const win = hours || undefined

  useEffect(() => {
    setMetrics(null)
    getAiMetrics({ hours: win })
      .then(setMetrics)
      .catch((e) => setErr(e.message))
  }, [hours, nonce])

  useEffect(() => {
    if (view !== 'llm') return
    setLogs(null)
    setErr('')
    getAiLogs({ limit: 200, hours: win, agentName: agent, status, q })
      .then(setLogs)
      .catch((e) => setErr(e.message))
  }, [view, hours, agent, status, q, nonce])

  useEffect(() => {
    if (view !== 'tools') return
    setToolLogs(null)
    setErr('')
    getAgentToolLogs({ limit: 200, hours: win, toolName: tool, status })
      .then(setToolLogs)
      .catch((e) => setErr(e.message))
  }, [view, hours, tool, status, nonce])

  // Chỉ cập nhật danh sách tool khi KHÔNG lọc theo tool, nếu không dropdown sẽ co
  // lại còn đúng mục đang chọn và không thoát ra được.
  useEffect(() => {
    if (tool || !Array.isArray(toolLogs)) return
    setToolOptions(
      Array.from(new Set(toolLogs.map((l) => l.tool_name).filter(Boolean))).sort()
    )
  }, [toolLogs, tool])

  const agentOptions = metrics?.by_agent?.map((a) => a.agent_name) || []
  const errorTone = metrics && metrics.error_rate > 5
  const num = (n) => (n || 0).toLocaleString('vi-VN')

  return (
    <>
      {/* Thanh điều khiển: cửa sổ thời gian + chế độ xem */}
      <Card className="flex flex-wrap items-center gap-3 p-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Gauge size={18} className="text-sky-500" /> Phạm vi giám sát
        </div>
        <Dropdown
          className="min-w-[170px]"
          value={hours}
          onChange={setHours}
          options={TIME_WINDOWS}
        />
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Segmented
            value={view}
            onChange={setView}
            options={[
              { value: 'llm', label: 'Lượt gọi LLM' },
              { value: 'tools', label: 'Tool của Agent' },
            ]}
          />
          <button
            onClick={() => setNonce((n) => n + 1)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-50"
          >
            <RefreshCw size={14} /> Tải lại
          </button>
        </div>
      </Card>

      {/* Số liệu tổng quan */}
      <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={Activity}
          iconClass="bg-sky-50 text-sky-600"
          label="Lượt gọi LLM"
          value={metrics == null ? '…' : num(metrics.total_requests)}
          footnote={metrics == null ? undefined : `${num(metrics.tool_calls)} lượt gọi tool`}
        />
        <StatCard
          icon={AlertTriangle}
          iconClass={errorTone ? 'bg-red-50 text-red-600' : 'bg-emerald-50 text-emerald-600'}
          label="Tỷ lệ lỗi"
          value={metrics == null ? '…' : `${metrics.error_rate}%`}
          footnote={metrics == null ? undefined : `${num(metrics.tool_errors)} tool lỗi`}
        />
        <StatCard
          icon={Zap}
          iconClass="bg-amber-50 text-amber-600"
          label="Độ trễ TB"
          value={metrics == null ? '…' : `${num(Math.round(metrics.avg_latency_ms))} ms`}
          footnote={metrics == null ? undefined : `Chậm nhất ${num(Math.round(metrics.max_latency_ms))} ms`}
        />
        <StatCard
          icon={Coins}
          iconClass="bg-violet-50 text-violet-600"
          label="Tổng token"
          value={metrics == null ? '…' : num(metrics.total_tokens)}
        />
      </div>

      {/* Bóc tách theo agent — biết agent nào đắt/chậm/hay lỗi */}
      {metrics?.by_agent?.length > 0 && (
        <Card className="mt-6 overflow-hidden">
          <CardHeader icon={Cpu} title="Theo từng agent" />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/60 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  <th className="px-6 py-3">Agent</th>
                  <th className="px-6 py-3 text-right">Lượt gọi</th>
                  <th className="px-6 py-3">Tỷ lệ lỗi</th>
                  <th className="px-6 py-3 text-right">Độ trễ TB</th>
                  <th className="px-6 py-3 text-right">Token</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {metrics.by_agent.map((a) => (
                  <tr key={a.agent_name} className="hover:bg-slate-50/60">
                    <td className="px-6 py-3">
                      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-700">
                        <Cpu size={14} className="text-indigo-500" /> {a.agent_name}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-right text-sm text-slate-600">{num(a.requests)}</td>
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-24">
                          <ProgressBar value={a.error_rate} color={a.error_rate > 5 ? 'red' : 'green'} />
                        </div>
                        <span className={`text-xs font-medium ${a.error_rate > 5 ? 'text-red-600' : 'text-slate-500'}`}>
                          {a.error_rate}%
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-3 text-right text-sm text-slate-600">
                      {num(Math.round(a.avg_latency_ms))} ms
                    </td>
                    <td className="px-6 py-3 text-right text-sm text-slate-600">{num(a.total_tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Bộ lọc + bảng nhật ký */}
      <Card className="mt-6 overflow-hidden">
        <CardHeader icon={view === 'llm' ? Cpu : Wrench} title={view === 'llm' ? 'Lịch sử gọi LLM' : 'Lịch sử gọi tool'}>
          <div className="flex flex-wrap items-center gap-2">
            {view === 'llm' ? (
              <>
                <select
                  value={agent}
                  onChange={(e) => setAgent(e.target.value)}
                  className={selectCls}
                >
                  <option value="">Tất cả agent</option>
                  {agentOptions.map((a) => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
                <div className="relative">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Tìm trong prompt / kết quả…"
                    className={`${selectCls} w-56 pl-8`}
                  />
                </div>
              </>
            ) : (
              <select
                value={tool}
                onChange={(e) => setTool(e.target.value)}
                className={selectCls}
              >
                <option value="">Tất cả tool</option>
                {toolOptions.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            )}
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className={selectCls}
            >
              <option value="">Mọi trạng thái</option>
              <option value="success">Thành công</option>
              <option value="error">Lỗi</option>
            </select>
          </div>
        </CardHeader>

        {err && <StateRow tone="error">Lỗi tải: {err}</StateRow>}

        {view === 'llm' ? (
          <>
            {logs === null && !err && <StateRow>Đang tải lịch sử AI…</StateRow>}
            {logs && logs.length === 0 && (
              <StateRow>
                {agent || status || q
                  ? 'Không có lượt gọi nào khớp bộ lọc.'
                  : 'Chưa có lượt gọi AI nào được ghi nhận.'}
              </StateRow>
            )}
            {logs && logs.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[820px] text-left">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50/60 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      <th className="px-6 py-3">Thời gian</th>
                      <th className="px-6 py-3">Agent</th>
                      <th className="px-6 py-3 text-right">Token</th>
                      <th className="px-6 py-3 text-right">Độ trễ</th>
                      <th className="px-6 py-3">Trạng thái</th>
                      <th className="px-6 py-3 text-right"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {logs.map((l) => (
                      <tr key={l.id} className="cursor-pointer hover:bg-slate-50/60" onClick={() => setOpenLog(l)}>
                        <td className="whitespace-nowrap px-6 py-3 text-xs text-slate-500">
                          {new Date(l.created_at).toLocaleString('vi-VN')}
                        </td>
                        <td className="px-6 py-3">
                          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-700">
                            <Cpu size={14} className="text-indigo-500" /> {l.agent_name || '(không rõ)'}
                          </span>
                        </td>
                        <td className="px-6 py-3 text-right text-sm text-slate-600">{num(l.total_tokens)}</td>
                        <td className="px-6 py-3 text-right text-sm text-slate-600">
                          {num(Math.round(l.latency_ms))} ms
                        </td>
                        <td className="px-6 py-3">
                          {l.is_error ? (
                            <Badge variant="error" upper={false}>Lỗi</Badge>
                          ) : (
                            <Badge variant="success" upper={false}>Thành công</Badge>
                          )}
                        </td>
                        <td className="px-6 py-3 text-right">
                          <ChevronRight size={16} className="ml-auto text-slate-300" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : (
          <>
            {toolLogs === null && !err && <StateRow>Đang tải lịch sử tool…</StateRow>}
            {toolLogs && toolLogs.length === 0 && (
              <StateRow>
                {tool || status
                  ? 'Không có lượt gọi tool nào khớp bộ lọc.'
                  : 'Chưa có lượt gọi tool nào được ghi nhận.'}
              </StateRow>
            )}
            {toolLogs && toolLogs.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[820px] text-left">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50/60 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      <th className="px-6 py-3">Thời gian</th>
                      <th className="px-6 py-3">Tool</th>
                      <th className="px-6 py-3">Người dùng</th>
                      <th className="px-6 py-3">Trạng thái</th>
                      <th className="px-6 py-3 text-right"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {toolLogs.map((l) => (
                      <tr key={l.id} className="cursor-pointer hover:bg-slate-50/60" onClick={() => setOpenTool(l)}>
                        <td className="whitespace-nowrap px-6 py-3 text-xs text-slate-500">
                          {new Date(l.created_at).toLocaleString('vi-VN')}
                        </td>
                        <td className="px-6 py-3">
                          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-700">
                            <Wrench size={14} className="text-sky-500" /> {l.tool_name}
                          </span>
                        </td>
                        <td className="px-6 py-3 text-sm text-slate-600">{l.user_email || 'Hệ thống'}</td>
                        <td className="px-6 py-3">
                          <Badge variant={l.status === 'success' ? 'success' : 'error'} upper={false}>
                            {l.status === 'success' ? 'Thành công' : l.status}
                          </Badge>
                        </td>
                        <td className="px-6 py-3 text-right">
                          <ChevronRight size={16} className="ml-auto text-slate-300" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Card>

      {openLog && (
        <Modal title="Chi tiết lượt gọi AI" onClose={() => setOpenLog(null)} wide>
          <div className="space-y-4 px-6 py-5">
            <div className="flex flex-wrap gap-2">
              <Badge variant="ai" upper={false}>{openLog.agent_name || '(không rõ)'}</Badge>
              <Badge variant={openLog.is_error ? 'error' : 'success'} upper={false}>
                {openLog.is_error ? 'Lỗi' : 'Thành công'}
              </Badge>
              <Badge variant="neutral" upper={false}>{num(openLog.total_tokens)} token</Badge>
              <Badge variant="neutral" upper={false}>{num(Math.round(openLog.latency_ms))} ms</Badge>
              <Badge variant="neutral" upper={false}>
                {new Date(openLog.created_at).toLocaleString('vi-VN')}
              </Badge>
            </div>
            {openLog.error_message && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {openLog.error_message}
              </div>
            )}
            <CodeBlock label="Prompt" text={openLog.prompt} />
            <CodeBlock label="Completion" text={openLog.completion} />
          </div>
        </Modal>
      )}

      {openTool && (
        <Modal title="Chi tiết lượt gọi tool" onClose={() => setOpenTool(null)} wide>
          <div className="space-y-4 px-6 py-5">
            <div className="flex flex-wrap gap-2">
              <Badge variant="ai" upper={false}>{openTool.tool_name}</Badge>
              <Badge variant={openTool.status === 'success' ? 'success' : 'error'} upper={false}>
                {openTool.status}
              </Badge>
              <Badge variant="neutral" upper={false}>{openTool.user_email || 'Hệ thống'}</Badge>
              <Badge variant="neutral" upper={false}>
                {new Date(openTool.created_at).toLocaleString('vi-VN')}
              </Badge>
            </div>
            <CodeBlock label="Tham số đầu vào" text={jsonText(openTool.input_params)} />
            <CodeBlock label="Kết quả trả về" text={jsonText(openTool.result)} />
          </div>
        </Modal>
      )}
    </>
  )
}

/* ================================================================== */
/* Kiểm toán & Bảo mật (Audit & Security)                             */
/* ================================================================== */
function AuditSecurity() {
  const [logs, setLogs] = useState(null)
  const [filters, setFilters] = useState({ actions: [], entity_types: [] })
  const [err, setErr] = useState('')
  const [entityType, setEntityType] = useState('')
  const [action, setAction] = useState('')
  const [hours, setHours] = useState('')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [nonce, setNonce] = useState(0)
  const [openLog, setOpenLog] = useState(null)

  useEffect(() => {
    const id = setTimeout(() => setQ(search.trim()), 400)
    return () => clearTimeout(id)
  }, [search])

  // Lấy danh sách action/entity từ BACKEND chứ không suy ra từ kết quả đang hiển
  // thị: nếu suy ra, khi đã lọc thì dropdown chỉ còn đúng mục đang chọn.
  useEffect(() => {
    getAuditFilters()
      .then(setFilters)
      .catch(() => {
        /* dropdown rỗng vẫn dùng được, không cần chặn cả trang */
      })
  }, [nonce])

  useEffect(() => {
    setLogs(null)
    setErr('')
    getAuditLogs({ limit: 200, entityType, action, hours: hours || undefined, q })
      .then(setLogs)
      .catch((e) => setErr(e.message))
  }, [entityType, action, hours, q, nonce])

  const stats = useMemo(() => {
    const list = logs || []
    return {
      total: list.length,
      actions: new Set(list.map((l) => l.action)).size,
      actors: new Set(list.map((l) => l.user_email || 'system')).size,
      latest: list[0] ? new Date(list[0].created_at).toLocaleString('vi-VN') : '—',
    }
  }, [logs])

  const filtering = entityType || action || hours || q

  return (
    <>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={FileSearch}
          iconClass="bg-rose-50 text-rose-600"
          label="Bản ghi hiển thị"
          value={logs == null ? '…' : stats.total}
          footnote="Tối đa 200 bản ghi mới nhất"
        />
        <StatCard
          icon={ShieldCheck}
          iconClass="bg-indigo-50 text-indigo-600"
          label="Loại hành động"
          value={logs == null ? '…' : stats.actions}
        />
        <StatCard
          icon={Users}
          iconClass="bg-violet-50 text-violet-600"
          label="Người thực hiện"
          value={logs == null ? '…' : stats.actors}
        />
        <StatCard
          icon={Activity}
          iconClass="bg-emerald-50 text-emerald-600"
          label="Gần nhất"
          value={logs == null ? '…' : stats.latest}
        />
      </div>

      <Card className="mt-6 flex flex-wrap items-center gap-3 p-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <FileSearch size={18} className="text-rose-500" /> Nhật ký kiểm toán
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <select value={action} onChange={(e) => setAction(e.target.value)} className={selectCls}>
            <option value="">Tất cả hành động</option>
            {filters.actions.map((a) => (
              <option key={a} value={a}>{AUDIT_ACTION_LABEL[a] || a}</option>
            ))}
          </select>
          <select value={entityType} onChange={(e) => setEntityType(e.target.value)} className={selectCls}>
            <option value="">Tất cả đối tượng</option>
            {filters.entity_types.map((t) => (
              <option key={t} value={t}>{ENTITY_LABEL[t] || t}</option>
            ))}
          </select>
          <Dropdown className="min-w-[150px]" value={hours} onChange={setHours} options={TIME_WINDOWS} />
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Email hoặc ID đối tượng…"
              className={`${selectCls} w-52 pl-8`}
            />
          </div>
          <button
            onClick={() => setNonce((n) => n + 1)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-50"
          >
            <RefreshCw size={14} /> Tải lại
          </button>
        </div>
      </Card>

      <Card className="mt-4 overflow-hidden">
        {logs === null && !err && <StateRow>Đang tải nhật ký kiểm toán…</StateRow>}
        {err && <StateRow tone="error">Lỗi tải: {err}</StateRow>}
        {logs && logs.length === 0 && (
          <StateRow>
            {filtering
              ? 'Không có bản ghi nào khớp bộ lọc.'
              : 'Chưa có bản ghi kiểm toán nào. Các hành động nhạy cảm (đổi quyền, khóa tài khoản, ghi đè điểm AI…) sẽ được ghi lại ở đây.'}
          </StateRow>
        )}
        {logs && logs.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/60 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  <th className="px-6 py-3">Thời gian</th>
                  <th className="px-6 py-3">Hành động</th>
                  <th className="px-6 py-3">Đối tượng</th>
                  <th className="px-6 py-3">Người thực hiện</th>
                  <th className="px-6 py-3 text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {logs.map((l) => {
                  const hasDiff = l.old_data || l.new_data
                  return (
                    <tr
                      key={l.id}
                      className={`${hasDiff ? 'cursor-pointer' : ''} hover:bg-slate-50/60`}
                      onClick={hasDiff ? () => setOpenLog(l) : undefined}
                    >
                      <td className="whitespace-nowrap px-6 py-3 text-xs text-slate-500">
                        {new Date(l.created_at).toLocaleString('vi-VN')}
                      </td>
                      <td className="px-6 py-3">
                        <Badge variant={AUDIT_ACTION_VARIANT[l.action] || 'ai'} upper={false}>
                          {AUDIT_ACTION_LABEL[l.action] || l.action}
                        </Badge>
                      </td>
                      <td className="px-6 py-3 text-sm text-slate-600">
                        {ENTITY_LABEL[l.entity_type] || l.entity_type}
                        {l.entity_id && (
                          <span className="ml-1 text-xs text-slate-400">#{String(l.entity_id).slice(0, 8)}</span>
                        )}
                      </td>
                      <td className="px-6 py-3 text-sm text-slate-600">{l.user_email || 'Hệ thống'}</td>
                      <td className="px-6 py-3 text-right">
                        {hasDiff && <ChevronRight size={16} className="ml-auto text-slate-300" />}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {openLog && (
        <Modal title="Chi tiết thay đổi (trước / sau)" onClose={() => setOpenLog(null)} wide>
          <div className="space-y-4 px-6 py-5">
            <div className="flex flex-wrap gap-2">
              <Badge variant={AUDIT_ACTION_VARIANT[openLog.action] || 'ai'} upper={false}>
                {AUDIT_ACTION_LABEL[openLog.action] || openLog.action}
              </Badge>
              <Badge variant="neutral" upper={false}>
                {ENTITY_LABEL[openLog.entity_type] || openLog.entity_type}
              </Badge>
              <Badge variant="neutral" upper={false}>{openLog.user_email || 'Hệ thống'}</Badge>
              <Badge variant="neutral" upper={false}>
                {new Date(openLog.created_at).toLocaleString('vi-VN')}
              </Badge>
            </div>
            {openLog.entity_id && (
              <p className="text-xs text-slate-500">
                ID đối tượng: <span className="font-mono">{openLog.entity_id}</span>
              </p>
            )}
            <DiffTable oldData={openLog.old_data} newData={openLog.new_data} />
          </div>
        </Modal>
      )}
    </>
  )
}

// Bảng so sánh từng trường. old_data/new_data từ backend CHỈ chứa các trường thực
// sự đổi, nên bảng này đọc thẳng ra "cái gì đã đổi" mà không phải dò 2 khối JSON.
function DiffTable({ oldData, newData }) {
  const keys = Array.from(
    new Set([...Object.keys(oldData || {}), ...Object.keys(newData || {})])
  )

  if (!keys.length) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <CodeBlock label="Trước" text={jsonText(oldData)} />
        <CodeBlock label="Sau" text={jsonText(newData)} />
      </div>
    )
  }

  const fmt = (v) => {
    if (v === null || v === undefined) return '—'
    if (typeof v === 'boolean') return v ? 'Có' : 'Không'
    if (typeof v === 'object') return JSON.stringify(v)
    return String(v)
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="bg-slate-50/60 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            <th className="px-4 py-2.5">Trường</th>
            <th className="px-4 py-2.5">Trước</th>
            <th className="px-4 py-2.5">Sau</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {keys.map((k) => (
            <tr key={k}>
              <td className="px-4 py-2.5 font-medium text-slate-700">{k}</td>
              <td className="px-4 py-2.5 text-slate-500 line-through decoration-slate-300">
                {fmt(oldData?.[k])}
              </td>
              <td className="px-4 py-2.5 font-medium text-slate-900">{fmt(newData?.[k])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ================================================================== */
/* Trung tâm thông báo (Broadcast Notifications)                      */
/* ================================================================== */
function BroadcastNotifications() {
  const toast = useToast()
  const [list, setList] = useState(null)
  const [err, setErr] = useState('')

  const [title, setTitle] = useState('')
  const [message, setMessage] = useState('')
  const [type, setType] = useState('info')
  const [sending, setSending] = useState(false)
  // Thông báo đang chờ xác nhận xóa. Xóa là không hoàn tác được nên phải hỏi lại.
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  function load() {
    setErr('')
    getNotifications()
      .then(setList)
      .catch((e) => setErr(e.message))
  }
  useEffect(load, [])

  async function send() {
    if (!title.trim() || !message.trim()) {
      toast('Nhập tiêu đề và nội dung thông báo.')
      return
    }
    setSending(true)
    try {
      await createNotification({ title: title.trim(), message: message.trim(), type, is_active: true })
      toast('Đã phát thông báo.')
      setTitle('')
      setMessage('')
      setType('info')
      load()
    } catch (e) {
      toast(e.message || 'Gửi thất bại.')
    } finally {
      setSending(false)
    }
  }

  async function remove() {
    if (!confirmDelete) return
    setDeleting(true)
    try {
      await deleteNotification(confirmDelete.id)
      toast('Đã xóa thông báo.')
      setConfirmDelete(null)
      load()
    } catch (e) {
      toast(e.message || 'Xóa thất bại.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <>
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
      {/* Composer */}
      <Card className="p-6 lg:col-span-2">
        <h3 className="flex items-center gap-2 text-base font-semibold text-slate-900">
          <Megaphone size={18} className="text-fuchsia-500" /> Soạn thông báo
        </h3>
        <p className="mt-1 text-sm text-slate-500">Thông báo sẽ hiển thị cho toàn bộ người dùng.</p>

        <div className="mt-5 space-y-4">
          <Field label="Tiêu đề">
            <input value={title} onChange={(e) => setTitle(e.target.value)} className={inputCls} placeholder="vd: Bảo trì hệ thống" />
          </Field>
          <Field label="Nội dung">
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={4}
              className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              placeholder="Nội dung chi tiết…"
            />
          </Field>
          <Field label="Loại">
            <div className="flex flex-wrap gap-2">
              {['info', 'success', 'warning', 'error'].map((t) => (
                <button
                  key={t}
                  onClick={() => setType(t)}
                  className={`rounded-full border px-3 py-1.5 text-sm capitalize transition ${
                    type === t
                      ? 'border-indigo-400 bg-indigo-50 font-medium text-indigo-700'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-indigo-300'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </Field>
          <PrimaryButton onClick={send} disabled={sending} className="w-full">
            {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            Phát thông báo
          </PrimaryButton>
        </div>
      </Card>

      {/* List */}
      <Card className="overflow-hidden lg:col-span-3">
        <CardHeader icon={Megaphone} title="Thông báo đã phát" iconClass="text-fuchsia-500">
          <button
            onClick={load}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-50"
          >
            <RefreshCw size={14} /> Tải lại
          </button>
        </CardHeader>

        {list === null && !err && <StateRow>Đang tải thông báo…</StateRow>}
        {err && <StateRow tone="error">Lỗi tải: {err}</StateRow>}
        {list && list.length === 0 && <StateRow>Chưa có thông báo nào.</StateRow>}
        {list && list.length > 0 && (
          <div className="divide-y divide-slate-100">
            {list.map((n) => (
              <div key={n.id} className="flex items-start gap-3 px-6 py-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Badge variant={NOTI_VARIANT[n.type] || 'neutral'} upper={false}>{n.type}</Badge>
                    <span className="truncate text-sm font-semibold text-slate-900">{n.title}</span>
                    {!n.is_active && (
                      <Badge variant="neutral" upper={false}>Đã ẩn</Badge>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-slate-600">{n.message}</p>
                  <p className="mt-1 text-xs text-slate-400">
                    {new Date(n.created_at).toLocaleString('vi-VN')}
                  </p>
                </div>
                <button
                  onClick={() => setConfirmDelete(n)}
                  className="flex-shrink-0 rounded-lg border border-slate-200 bg-white p-2 text-slate-400 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                  title="Xóa thông báo"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>

    {confirmDelete && (
      <Modal title="Xác nhận xóa thông báo" onClose={() => (deleting ? null : setConfirmDelete(null))}>
        <div className="px-6 py-5">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-red-50 text-red-600">
              <Trash2 size={18} />
            </div>
            <div className="min-w-0">
              <p className="text-sm text-slate-700">
                Xóa thông báo{' '}
                <span className="font-semibold text-slate-900">{confirmDelete.title}</span>?
              </p>
              <p className="mt-1.5 text-sm text-slate-500">
                Thông báo sẽ bị gỡ khỏi hệ thống và biến mất khỏi chuông thông báo của mọi
                người dùng. Thao tác này không hoàn tác được.
              </p>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4">
          <SecondaryButton className="px-3 py-2" onClick={() => setConfirmDelete(null)} disabled={deleting}>
            Hủy
          </SecondaryButton>
          <button
            onClick={remove}
            disabled={deleting}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {deleting ? (
              <>
                <Loader2 size={15} className="animate-spin" /> Đang xóa…
              </>
            ) : (
              <>
                <Trash2 size={15} /> Xóa thông báo
              </>
            )}
          </button>
        </div>
      </Modal>
    )}
    </>
  )
}

/* ================================================================== */
/* Trung tâm trích xuất (Export Center)                               */
/* ================================================================== */
const EXPORTS = [
  { kind: 'system-logs', file: 'system_logs.csv', title: 'Nhật ký hệ thống', desc: 'Log đăng nhập & hành động quản trị.', icon: ScrollText, cls: 'bg-slate-100 text-slate-600' },
  { kind: 'ai-logs', file: 'ai_logs.csv', title: 'Nhật ký giám sát AI', desc: 'Prompt, completion, token & độ trễ.', icon: Cpu, cls: 'bg-sky-50 text-sky-600' },
  { kind: 'audit-logs', file: 'audit_logs.csv', title: 'Nhật ký kiểm toán', desc: 'Ai đã thay đổi gì, kèm giá trị trước/sau.', icon: FileSearch, cls: 'bg-rose-50 text-rose-600' },
  { kind: 'agent-tool-logs', file: 'agent_tool_logs.csv', title: 'Nhật ký tool của Agent', desc: 'AI Agent đã gọi tool nào, tham số & kết quả.', icon: Wrench, cls: 'bg-indigo-50 text-indigo-600' },
]

function ExportCenter() {
  const toast = useToast()
  const [busy, setBusy] = useState(null)

  async function handleExport(item) {
    setBusy(item.kind)
    try {
      await downloadExport(item.kind, item.file)
      toast(`Đã xuất ${item.title} (CSV).`)
    } catch (e) {
      toast(e.message || 'Xuất thất bại.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {EXPORTS.map((item) => (
        <Card key={item.kind} className="flex flex-col p-6">
          <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${item.cls}`}>
            <item.icon size={22} />
          </div>
          <h3 className="mt-4 text-base font-semibold text-slate-900">{item.title}</h3>
          <p className="mt-1 flex-1 text-sm text-slate-500">{item.desc}</p>
          <div className="mt-4 flex items-center gap-2 text-xs text-slate-400">
            <FileSpreadsheet size={14} /> Định dạng CSV (UTF-8)
          </div>
          <PrimaryButton
            className="mt-4 w-full"
            onClick={() => handleExport(item)}
            disabled={busy === item.kind}
          >
            {busy === item.kind ? (
              <><Loader2 size={16} className="animate-spin" /> Đang xuất…</>
            ) : (
              <><Download size={16} /> Tải CSV</>
            )}
          </PrimaryButton>
        </Card>
      ))}
    </div>
  )
}

/* ================================================================== */
/* Nhật ký hệ thống (NFR-8)                                           */
/* ================================================================== */
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
    <Card className="overflow-hidden">
      <CardHeader icon={ScrollText} title="Nhật ký hệ thống">
        <button
          onClick={load}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-50"
        >
          <RefreshCw size={14} /> Tải lại
        </button>
      </CardHeader>

      {logs === null && !err && <StateRow>Đang tải nhật ký…</StateRow>}
      {err && <StateRow tone="error">Lỗi tải: {err}</StateRow>}
      {logs && logs.length === 0 && <StateRow>Chưa có nhật ký nào.</StateRow>}
      {logs && logs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/60 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
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

/* ================================================================== */
/* Shared bits                                                        */
/* ================================================================== */
function Modal({ title, onClose, children, wide = false }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={onClose} />
      <div
        className={`relative flex max-h-[90vh] w-full flex-col overflow-hidden rounded-2xl bg-white shadow-2xl ${
          wide ? 'max-w-3xl' : 'max-w-md'
        }`}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-base font-bold text-slate-900">{title}</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={18} />
          </button>
        </div>
        <div className="overflow-y-auto">{children}</div>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </label>
      {children}
    </div>
  )
}

function CodeBlock({ label, text }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2.5 font-mono text-xs leading-relaxed text-slate-700">
        {text || '—'}
      </pre>
    </div>
  )
}
