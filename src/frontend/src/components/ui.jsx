// ---------------------------------------------------------------------------
// Small reusable UI building blocks shared across the dashboard pages.
// Pure presentational components — no data fetching here.
// ---------------------------------------------------------------------------

export function Card({ className = '', children, ...rest }) {
  return (
    <div
      className={`rounded-xl border border-slate-200 bg-white ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}

// Top-row metric tile: icon chip + label + big value + small footnote.
export function StatCard({ icon: Icon, iconClass, label, value, footnote }) {
  return (
    <Card className="flex items-start gap-4 p-5">
      <div
        className={`flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg ${
          iconClass || 'bg-indigo-50 text-indigo-600'
        }`}
      >
        <Icon size={20} />
      </div>
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-500">{label}</p>
        <p className="mt-0.5 text-2xl font-bold text-slate-900">{value}</p>
        {footnote && (
          <p className="mt-0.5 text-xs text-slate-400">{footnote}</p>
        )}
      </div>
    </Card>
  )
}

const BADGE_VARIANTS = {
  processing: 'bg-indigo-50 text-indigo-600',
  completed: 'bg-emerald-50 text-emerald-600',
  error: 'bg-red-50 text-red-600',
  new: 'bg-blue-50 text-blue-600',
  neutral: 'bg-slate-100 text-slate-600',
  ai: 'bg-indigo-100 text-indigo-700',
}

export function Badge({ variant = 'neutral', upper = true, children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold ${
        upper ? 'uppercase tracking-wide' : ''
      } ${BADGE_VARIANTS[variant] || BADGE_VARIANTS.neutral} ${className}`}
    >
      {children}
    </span>
  )
}

const BAR_COLORS = {
  indigo: 'bg-indigo-500',
  green: 'bg-emerald-500',
  red: 'bg-red-500',
}

export function ProgressBar({ value, color = 'indigo' }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
      <div
        className={`h-full rounded-full ${BAR_COLORS[color] || BAR_COLORS.indigo}`}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  )
}

// Small skill / tag chip.
export function Tag({ children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 ${className}`}
    >
      {children}
    </span>
  )
}

// Circular suitability score ring (used on the Shortlisting table).
export function ScoreRing({ value, size = 46 }) {
  const stroke = 3.5
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const offset = circ * (1 - value / 100)

  const color =
    value >= 90 ? '#10b981' : value >= 80 ? '#6366f1' : '#f59e0b'

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-slate-800">
        {value}
      </span>
    </div>
  )
}

// Segmented control (e.g. "Frontend Eng | Product Mgr", tab switchers).
export function Segmented({ options, value, onChange }) {
  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1">
      {options.map((opt) => {
        const val = typeof opt === 'string' ? opt : opt.value
        const label = typeof opt === 'string' ? opt : opt.label
        const active = val === value
        return (
          <button
            key={val}
            onClick={() => onChange(val)}
            className={`rounded-md px-3.5 py-1.5 text-sm font-medium transition-colors ${
              active
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}

// RBAC permission toggle switch.
export function Toggle({ checked, onChange, disabled = false }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange?.(!checked)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors ${
        checked
          ? disabled
            ? 'bg-indigo-300'
            : 'bg-indigo-600'
          : 'bg-slate-200'
      } ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <span
        className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-5' : 'translate-x-0.5'
        }`}
      />
    </button>
  )
}

// Generic buttons matching the mockups.
export function PrimaryButton({ className = '', children, ...rest }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}

export function DarkButton({ className = '', children, ...rest }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}

export function SecondaryButton({ className = '', children, ...rest }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
