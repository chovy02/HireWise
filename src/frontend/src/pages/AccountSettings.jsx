// Trang "Quản lý tài khoản" — người dùng tự sửa tài khoản CỦA MÌNH.
//
// Khác trang Cổng quản trị (admin sửa tài khoản người khác qua /users): mọi thao tác
// ở đây đi qua /auth/me nên không có cách nào chạm tới tài khoản khác. Vào bằng cách
// bấm khối tên ở góc dưới sidebar -> "Quản lý tài khoản".
import { useEffect, useState } from 'react'
import {
  UserCog,
  User,
  Mail,
  ShieldCheck,
  KeyRound,
  Save,
  Loader2,
  Eye,
  EyeOff,
  LogOut,
  CalendarClock,
  Lock,
  Info,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  CardHeader,
  PageHeader,
  Badge,
  PrimaryButton,
  SecondaryButton,
  StateRow,
} from '../components/ui.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { me as fetchMe, updateProfile, changePassword } from '../api/auth.js'

const ROLE_LABEL = {
  admin: 'Quản trị viên',
  hr_staff: 'Nhân viên HR',
}

// Khớp Field(min_length=8) của schemas.PasswordChange ở backend. Kiểm ở đây để người
// dùng nhận câu tiếng Việt thay vì thông điệp máy của Pydantic ("String should have
// at least 8 characters") sau khi đã bấm Lưu.
const MIN_PASSWORD = 8

function initialsOf(name) {
  return String(name || 'Người dùng')
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

function formatDate(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('vi-VN')
}

// Ô nhập dùng lại cho cả hai thẻ, có nhãn + dòng gợi ý/lỗi bên dưới.
function LabeledInput({ label, icon: Icon, hint, error, trailing, ...rest }) {
  return (
    <label className="block">
      <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {Icon && <Icon size={13} />}
        {label}
      </span>
      <div className="relative mt-1.5">
        <input
          {...rest}
          className={`w-full rounded-lg border bg-white px-3.5 py-2.5 text-sm text-slate-800 transition-colors focus:outline-none focus:ring-2 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500 ${
            error
              ? 'border-red-300 focus:border-red-400 focus:ring-red-100'
              : 'border-slate-200 focus:border-indigo-400 focus:ring-indigo-100'
          } ${trailing ? 'pr-11' : ''}`}
        />
        {trailing && (
          <div className="absolute inset-y-0 right-1.5 flex items-center">{trailing}</div>
        )}
      </div>
      {(error || hint) && (
        <span className={`mt-1.5 block text-xs ${error ? 'text-red-500' : 'text-slate-400'}`}>
          {error || hint}
        </span>
      )}
    </label>
  )
}

// Nút con mắt hiện/ẩn mật khẩu. Gõ mật khẩu mới mà không xem lại được thì rất dễ
// sai âm thầm, rồi lần đăng nhập sau mới phát hiện.
function RevealButton({ shown, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      title={shown ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
      aria-label={shown ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
      className="rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
    >
      {shown ? <EyeOff size={16} /> : <Eye size={16} />}
    </button>
  )
}

function ProfileCard({ account, onSaved }) {
  const { updateUser } = useAuth()
  const toast = useToast()

  const [name, setName] = useState(account.name || '')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  // Nạp lại khi /auth/me trả về sau lần render đầu (lúc đó account còn là bản cache).
  useEffect(() => {
    setName(account.name || '')
  }, [account.name])

  const trimmed = name.trim()
  const dirty = trimmed !== (account.name || '')
  const tooShort = trimmed.length > 0 && trimmed.length < 2

  async function save(e) {
    e.preventDefault()
    if (!dirty || saving) return
    if (trimmed.length < 2) {
      setErr('Tên hiển thị phải có ít nhất 2 ký tự.')
      return
    }

    setSaving(true)
    setErr('')
    try {
      const updated = await updateProfile({ name: trimmed })
      // Cập nhật cả context: sidebar/avatar đọc từ đó, không đồng bộ thì tên cũ còn
      // hiện ở góc dưới cho tới lần F5.
      updateUser({ name: updated.name })
      onSaved(updated)
      toast('Đã cập nhật tên hiển thị.')
    } catch (e2) {
      setErr(e2.message || 'Không lưu được thay đổi.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader icon={User} title="Thông tin tài khoản" />
      <form onSubmit={save} className="space-y-5 px-6 py-5">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 text-lg font-bold text-white">
            {initialsOf(account.name)}
          </div>
          <div className="min-w-0">
            <p className="truncate text-base font-semibold text-slate-900">
              {account.name || 'Người dùng'}
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <Badge variant="ai">
                <ShieldCheck size={11} />
                {ROLE_LABEL[account.role] || account.role}
              </Badge>
              {account.is_banned ? (
                <Badge variant="error">Đã bị khóa</Badge>
              ) : account.is_active ? (
                <Badge variant="success">Đã xác minh</Badge>
              ) : (
                <Badge variant="warning">Chưa xác minh</Badge>
              )}
            </div>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <LabeledInput
            label="Tên hiển thị"
            icon={User}
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={255}
            placeholder="VD: Nguyễn Thị Mai"
            disabled={saving}
            error={tooShort ? 'Tên hiển thị phải có ít nhất 2 ký tự.' : err}
            hint="Tên này hiện ở sidebar và trong nhật ký hoạt động."
          />
          <LabeledInput
            label="Email đăng nhập"
            icon={Mail}
            value={account.email || ''}
            readOnly
            disabled
            trailing={<Lock size={15} className="mr-1.5 text-slate-400" />}
            hint="Email là danh tính phiên đăng nhập nên không tự đổi được — cần admin đổi giúp."
          />
        </div>

        <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-3.5 py-2.5 text-xs text-slate-500">
          <CalendarClock size={14} className="flex-shrink-0 text-slate-400" />
          Ngày tạo tài khoản: {formatDate(account.created_at)}
        </div>

        <div className="flex items-center justify-end gap-2.5">
          {dirty && !saving && (
            <SecondaryButton type="button" onClick={() => { setName(account.name || ''); setErr('') }}>
              Hoàn tác
            </SecondaryButton>
          )}
          <PrimaryButton type="submit" disabled={!dirty || saving || tooShort}>
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            {saving ? 'Đang lưu…' : 'Lưu thay đổi'}
          </PrimaryButton>
        </div>
      </form>
    </Card>
  )
}

function PasswordCard() {
  const toast = useToast()

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [shown, setShown] = useState({ current: false, next: false, confirm: false })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const tooShort = next.length > 0 && next.length < MIN_PASSWORD
  const mismatch = confirm.length > 0 && confirm !== next
  const sameAsOld = next.length > 0 && next === current
  const ready =
    current.length > 0 &&
    next.length >= MIN_PASSWORD &&
    confirm === next &&
    !sameAsOld

  function toggle(key) {
    setShown((s) => ({ ...s, [key]: !s[key] }))
  }

  async function submit(e) {
    e.preventDefault()
    if (!ready || saving) return

    setSaving(true)
    setErr('')
    try {
      await changePassword({ currentPassword: current, newPassword: next })
      // Xoá sạch cả ba ô: để mật khẩu nằm lại trong form sau khi đã đổi thành công
      // là vừa vô nghĩa vừa dễ bị người sau đọc bằng nút con mắt.
      setCurrent('')
      setNext('')
      setConfirm('')
      setShown({ current: false, next: false, confirm: false })
      toast('Đổi mật khẩu thành công.')
    } catch (e2) {
      setErr(e2.message || 'Không đổi được mật khẩu.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader icon={KeyRound} title="Đổi mật khẩu" />
      <form onSubmit={submit} className="space-y-5 px-6 py-5">
        <LabeledInput
          label="Mật khẩu hiện tại"
          icon={Lock}
          type={shown.current ? 'text' : 'password'}
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          autoComplete="current-password"
          disabled={saving}
          trailing={<RevealButton shown={shown.current} onToggle={() => toggle('current')} />}
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <LabeledInput
            label="Mật khẩu mới"
            icon={KeyRound}
            type={shown.next ? 'text' : 'password'}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
            disabled={saving}
            trailing={<RevealButton shown={shown.next} onToggle={() => toggle('next')} />}
            error={
              tooShort
                ? `Mật khẩu mới cần ít nhất ${MIN_PASSWORD} ký tự.`
                : sameAsOld
                  ? 'Mật khẩu mới phải khác mật khẩu hiện tại.'
                  : ''
            }
            hint={`Tối thiểu ${MIN_PASSWORD} ký tự.`}
          />
          <LabeledInput
            label="Nhập lại mật khẩu mới"
            icon={KeyRound}
            type={shown.confirm ? 'text' : 'password'}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            disabled={saving}
            trailing={<RevealButton shown={shown.confirm} onToggle={() => toggle('confirm')} />}
            error={mismatch ? 'Hai mật khẩu không giống nhau.' : ''}
          />
        </div>

        {/* JWT không có danh sách thu hồi: đổi mật khẩu KHÔNG đá các phiên khác ra.
            Nói thẳng ở đây, vì người dùng đổi mật khẩu vì nghi bị lộ sẽ tưởng thiết
            bị lạ đã bị đăng xuất. */}
        <div className="flex items-start gap-2 rounded-lg bg-amber-50/70 px-3.5 py-2.5 text-xs leading-relaxed text-amber-700">
          <Info size={14} className="mt-0.5 flex-shrink-0" />
          Các thiết bị đang đăng nhập sẵn vẫn dùng được phiên hiện tại cho tới khi phiên
          đó hết hạn. Nếu nghi tài khoản bị lộ, hãy báo quản trị viên khóa tài khoản.
        </div>

        {err && (
          <p className="rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-600">{err}</p>
        )}

        <div className="flex justify-end">
          <PrimaryButton type="submit" disabled={!ready || saving}>
            {saving ? <Loader2 size={16} className="animate-spin" /> : <KeyRound size={16} />}
            {saving ? 'Đang đổi…' : 'Đổi mật khẩu'}
          </PrimaryButton>
        </div>
      </form>
    </Card>
  )
}

export default function AccountSettings() {
  const { user, signOut } = useAuth()

  // Bắt đầu từ user trong context (có ngay, không nhấp nháy) rồi làm mới bằng
  // /auth/me: response đăng nhập chỉ có id/name/email/role, thiếu created_at &
  // trạng thái xác minh mà trang này hiển thị.
  const [account, setAccount] = useState(user)
  const [loadErr, setLoadErr] = useState('')

  useEffect(() => {
    let cancelled = false
    fetchMe()
      .then((data) => !cancelled && setAccount(data))
      .catch((e) => !cancelled && setLoadErr(e.message || 'Không tải được thông tin tài khoản.'))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        <PageHeader
          icon={UserCog}
          title="Quản lý tài khoản"
          subtitle="Xem và cập nhật thông tin tài khoản của bạn, đổi mật khẩu hoặc đăng xuất."
        />

        <div className="mt-6 max-w-3xl space-y-5">
          {/* Lỗi tải KHÔNG chặn cả trang: dữ liệu trong context vẫn đủ để đổi tên và
              đổi mật khẩu, chỉ thiếu ngày tạo/trạng thái xác minh. */}
          {loadErr && (
            <p className="rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-600">
              {loadErr}
            </p>
          )}

          {account ? (
            <>
              <ProfileCard account={account} onSaved={setAccount} />
              <PasswordCard />

              <Card className="flex flex-wrap items-center justify-between gap-3 px-6 py-5">
                <div>
                  <p className="text-sm font-semibold text-slate-900">Phiên đăng nhập</p>
                  <p className="mt-1 text-sm text-slate-500">
                    Đăng xuất khỏi thiết bị này. Bạn sẽ cần đăng nhập lại để tiếp tục.
                  </p>
                </div>
                <button
                  onClick={signOut}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-200 bg-white px-4 py-2.5 text-sm font-semibold text-red-600 transition-colors hover:bg-red-50"
                >
                  <LogOut size={16} /> Đăng xuất
                </button>
              </Card>
            </>
          ) : (
            <Card>
              <StateRow>Đang tải thông tin tài khoản…</StateRow>
            </Card>
          )}
        </div>
      </main>
    </>
  )
}
