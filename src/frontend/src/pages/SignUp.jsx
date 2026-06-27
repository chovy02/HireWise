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

  // BUTTON: "Create account" -> POST /auth/register (exists in backend)
  // The confirm-password match is verified HERE, in the browser only.
  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    if (!passwordLongEnough) {
      setError(`Password must be at least ${MIN_PASSWORD} characters.`)
      return
    }
    if (form.password !== form.confirm) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      await register({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
      })
      // Backend emails a verification token; send the user to the verify page.
      navigate('/verify', { state: { email: form.email.trim() } })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Start automating your hiring in minutes."
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
            Full name
          </label>
          <input
            type="text"
            required
            autoComplete="name"
            value={form.name}
            onChange={update('name')}
            placeholder="Sarah Jenkins"
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
            placeholder="you@company.com"
            className={inputClass}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Password
          </label>
          <input
            type="password"
            required
            autoComplete="new-password"
            value={form.password}
            onChange={update('password')}
            placeholder="At least 8 characters"
            className={inputClass}
          />
          {form.password.length > 0 && (
            <p
              className={`mt-1.5 flex items-center gap-1.5 text-xs ${
                passwordLongEnough ? 'text-emerald-600' : 'text-slate-400'
              }`}
            >
              {passwordLongEnough ? <Check size={13} /> : <X size={13} />}
              At least {MIN_PASSWORD} characters
            </p>
          )}
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Confirm password
          </label>
          <input
            type="password"
            required
            autoComplete="new-password"
            value={form.confirm}
            onChange={update('confirm')}
            placeholder="Re-enter your password"
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
              {passwordsMatch ? 'Passwords match' : 'Passwords do not match'}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={!canSubmit}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading && <Loader2 size={16} className="animate-spin" />}
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-500">
        Already have an account?{' '}
        <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-700">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  )
}
