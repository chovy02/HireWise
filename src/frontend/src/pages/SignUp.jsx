import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, AlertCircle, Check, X } from 'lucide-react'
import AuthLayout from '../components/AuthLayout.jsx'
import { register } from '../api/auth.js'

const inputClass =
  'w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

const MIN_PASSWORD = 8

export default function SignUp() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    confirm: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function update(field) {
    return (e) => setForm((f) => ({ ...f, [field]: e.target.value }))
  }

  // ---- Client-side validation (no backend round-trip for these) ----
  const passwordLongEnough = form.password.length >= MIN_PASSWORD
  const passwordsMatch =
    form.confirm.length > 0 && form.confirm === form.password
  const showMismatch = form.confirm.length > 0 && !passwordsMatch

  const canSubmit =
    form.name.trim() &&
    form.email.trim() &&
    passwordLongEnough &&
    passwordsMatch &&
    !loading

  // NÚT "Tạo tài khoản" -> POST /auth/register
  // Việc khớp mật khẩu xác nhận được kiểm tra Ở ĐÂY, chỉ trên trình duyệt.
  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    if (!passwordLongEnough) {
      setError(`Mật khẩu phải có ít nhất ${MIN_PASSWORD} ký tự.`)
      return
    }
    if (form.password !== form.confirm) {
      setError('Mật khẩu nhập lại không khớp.')
      return
    }

    setLoading(true)
    try {
      await register({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
      })
      // Backend gửi mã OTP qua email; chuyển người dùng sang trang xác minh.
      navigate('/verify', { state: { email: form.email.trim() } })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Tạo tài khoản"
      subtitle="Bắt đầu tự động hoá tuyển dụng chỉ trong vài phút."
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
            <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Họ và tên
          </label>
          <input
            type="text"
            required
            autoComplete="name"
            value={form.name}
            onChange={update('name')}
            placeholder="Nguyễn Văn An"
            className={inputClass}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Email
          </label>
          <input
            type="email"
            required
            autoComplete="email"
            value={form.email}
            onChange={update('email')}
            placeholder="ban@congty.com"
            className={inputClass}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Mật khẩu
          </label>
          <input
            type="password"
            required
            autoComplete="new-password"
            value={form.password}
            onChange={update('password')}
            placeholder="Tối thiểu 8 ký tự"
            className={inputClass}
          />
          {form.password.length > 0 && (
            <p
              className={`mt-1.5 flex items-center gap-1.5 text-xs ${
                passwordLongEnough ? 'text-emerald-600' : 'text-slate-400'
              }`}
            >
              {passwordLongEnough ? <Check size={13} /> : <X size={13} />}
              Tối thiểu {MIN_PASSWORD} ký tự
            </p>
          )}
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Xác nhận mật khẩu
          </label>
          <input
            type="password"
            required
            autoComplete="new-password"
            value={form.confirm}
            onChange={update('confirm')}
            placeholder="Nhập lại mật khẩu"
            className={`${inputClass} ${
              showMismatch ? 'border-red-300 focus:border-red-400 focus:ring-red-100' : ''
            }`}
          />
          {form.confirm.length > 0 && (
            <p
              className={`mt-1.5 flex items-center gap-1.5 text-xs ${
                passwordsMatch ? 'text-emerald-600' : 'text-red-500'
              }`}
            >
              {passwordsMatch ? <Check size={13} /> : <X size={13} />}
              {passwordsMatch ? 'Mật khẩu khớp' : 'Mật khẩu không khớp'}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={!canSubmit}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading && <Loader2 size={16} className="animate-spin" />}
          {loading ? 'Đang tạo tài khoản…' : 'Tạo tài khoản'}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-500">
        Đã có tài khoản?{' '}
        <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-700">
          Đăng nhập
        </Link>
      </p>
    </AuthLayout>
  )
}
