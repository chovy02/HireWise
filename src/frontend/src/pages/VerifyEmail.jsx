import { useEffect, useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { Loader2, AlertCircle, CheckCircle2, MailCheck } from 'lucide-react'
import AuthLayout from '../components/AuthLayout.jsx'
import { verifyEmail, resendCode } from '../api/auth.js'

const inputClass =
  'w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

// Giây phải chờ giữa hai lần xin mã, tránh spam hòm thư (và hoá đơn SMTP).
const RESEND_COOLDOWN = 60

export default function VerifyEmail() {
  const navigate = useNavigate()
  const location = useLocation()
  const emailFromSignup = location.state?.email

  // Email đến từ bước đăng ký, nhưng router state MẤT khi người dùng F5 hoặc mở
  // thẳng /verify. Giữ nó trong state và cho sửa được để trang vẫn dùng được.
  const [email, setEmail] = useState(emailFromSignup ?? '')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  const codeComplete = /^\d{6}$/.test(code)

  useEffect(() => {
    if (cooldown <= 0) return
    const id = setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => clearTimeout(id)
  }, [cooldown])

  // NÚT "Kích hoạt tài khoản" -> POST /auth/verify-email { email, token }
  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      const res = await verifyEmail({ email: email.trim(), token: code })
      setSuccess(res?.message || 'Kích hoạt thành công! Bạn có thể đăng nhập ngay.')
      setTimeout(() => navigate('/login'), 1500)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // NÚT "Gửi lại mã" -> POST /auth/resend-code { email }
  async function handleResend() {
    setError('')
    setSuccess('')
    if (!email.trim()) {
      setError('Vui lòng nhập email trước khi xin mã mới.')
      return
    }
    setResending(true)
    try {
      const res = await resendCode(email.trim())
      setSuccess(res?.message || 'Đã gửi mã mới, vui lòng kiểm tra email.')
      setCode('')
      setCooldown(RESEND_COOLDOWN)
    } catch (err) {
      setError(err.message)
    } finally {
      setResending(false)
    }
  }

  return (
    <AuthLayout
      title="Xác minh email"
      subtitle={
        emailFromSignup
          ? `Chúng tôi đã gửi mã 6 chữ số tới ${emailFromSignup}. Nhập mã bên dưới để kích hoạt tài khoản.`
          : 'Nhập email và mã 6 chữ số vừa nhận để kích hoạt tài khoản.'
      }
    >
      <div className="mb-6 flex items-start gap-3 rounded-lg border border-indigo-100 bg-indigo-50 px-3.5 py-3 text-sm text-indigo-700">
        <MailCheck size={18} className="mt-0.5 flex-shrink-0" />
        <span>
          Mã có hiệu lực trong 15 phút. Kiểm tra cả hộp thư rác nếu bạn chưa thấy
          email.
        </span>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
            <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}
        {success && (
          <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-700">
            <CheckCircle2 size={16} className="mt-0.5 flex-shrink-0" />
            <span>{success}</span>
          </div>
        )}

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Email
          </label>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="ban@congty.com"
            className={inputClass}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Mã xác minh
          </label>
          <input
            type="text"
            required
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            // KHÔNG dùng maxLength: trình duyệt cắt chuỗi DÁN VÀO trước khi React kịp
            // lọc, nên dán "123 456" (mã trong email hay kèm dấu cách) chỉ còn "123 45"
            // -> lọc ra "12345", thiếu một số. Cắt bằng JS sau khi đã bỏ ký tự không phải
            // chữ số mới ra đúng 6 chữ số.
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder="000000"
            className={`${inputClass} text-center font-mono text-lg tracking-[0.4em]`}
          />
        </div>

        <button
          type="submit"
          disabled={loading || !codeComplete || !email.trim()}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading && <Loader2 size={16} className="animate-spin" />}
          {loading ? 'Đang kích hoạt…' : 'Kích hoạt tài khoản'}
        </button>
      </form>

      <p className="mt-4 text-center text-sm text-slate-500">
        Chưa nhận được mã?{' '}
        <button
          type="button"
          onClick={handleResend}
          disabled={resending || cooldown > 0}
          className="font-semibold text-indigo-600 transition hover:text-indigo-700 disabled:cursor-not-allowed disabled:text-slate-400"
        >
          {resending
            ? 'Đang gửi…'
            : cooldown > 0
              ? `Gửi lại sau ${cooldown}s`
              : 'Gửi lại mã'}
        </button>
      </p>

      <p className="mt-6 text-center text-sm text-slate-500">
        Quay lại{' '}
        <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-700">
          Đăng nhập
        </Link>
      </p>
    </AuthLayout>
  )
}
