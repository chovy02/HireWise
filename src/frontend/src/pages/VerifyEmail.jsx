import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { Loader2, AlertCircle, CheckCircle2, MailCheck } from 'lucide-react'
import AuthLayout from '../components/AuthLayout.jsx'
import { verifyEmail } from '../api/auth.js'

const inputClass =
  'w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

export default function VerifyEmail() {
  const navigate = useNavigate()
  const location = useLocation()
  const email = location.state?.email

  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  // BUTTON: "Verify account" -> POST /auth/verify-email (exists in backend)
  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      const res = await verifyEmail(token.trim())
      setSuccess(res?.message || 'Account verified! You can now sign in.')
      setTimeout(() => navigate('/login'), 1500)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Verify your email"
      subtitle={
        email
          ? `We sent a verification code to ${email}. Paste it below to activate your account.`
          : 'Paste the verification code from your email to activate your account.'
      }
    >
      <div className="mb-6 flex items-start gap-3 rounded-lg border border-indigo-100 bg-indigo-50 px-3.5 py-3 text-sm text-indigo-700">
        <MailCheck size={18} className="mt-0.5 flex-shrink-0" />
        <span>
          The code expires in 15 minutes. Check your spam folder if you don&apos;t
          see it.
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
            Verification code
          </label>
          <textarea
            required
            rows={4}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste the long code from your email here…"
            className={`${inputClass} resize-none font-mono text-xs`}
          />
        </div>

        <button
          type="submit"
          disabled={loading || !token.trim()}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading && <Loader2 size={16} className="animate-spin" />}
          {loading ? 'Verifying…' : 'Verify account'}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-500">
        Back to{' '}
        <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-700">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  )
}
