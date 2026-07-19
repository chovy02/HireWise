// ---------------------------------------------------------------------------
// Small reusable UI building blocks shared across the dashboard pages.
// Pure presentational components — no data fetching here.
// ---------------------------------------------------------------------------

import { useEffect, useRef, useState } from 'react'
import { ChevronDown, Check } from 'lucide-react'

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
  warning: 'bg-amber-50 text-amber-600',
  success: 'bg-emerald-50 text-emerald-600',
  info: 'bg-sky-50 text-sky-600',
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

// In-content dropdown "view switcher" — thay cho thanh tab (Segmented) khi cần
// chuyển giữa các chế độ xem của trang. Hiện lựa chọn đang chọn + menu xổ xuống.
// options: [{ value, label, icon?, badge? }] (hoặc mảng string).
export function Dropdown({
  options,
  value,
  onChange,
  placeholder = 'Chọn…',
  align = 'left',
  className = '',
  buttonClassName = '',
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    function onDoc(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    function onKey(e) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const norm = options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o))
  const current = norm.find((o) => o.value === value)
  const CurrentIcon = current?.icon

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex w-full items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:bg-slate-50 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 ${buttonClassName}`}
      >
        {CurrentIcon && <CurrentIcon size={16} className="flex-shrink-0 text-indigo-600" />}
        <span className="flex-1 truncate text-left">{current?.label || placeholder}</span>
        {current?.badge != null && current.badge !== '' && (
          <span className="rounded-full bg-indigo-50 px-1.5 py-0.5 text-[11px] font-semibold text-indigo-600">
            {current.badge}
          </span>
        )}
        <ChevronDown
          size={16}
          className={`flex-shrink-0 text-slate-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div
          className={`absolute z-30 mt-2 min-w-full overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg shadow-slate-900/5 ${
            align === 'right' ? 'right-0' : 'left-0'
          }`}
        >
          {norm.map((o) => {
            const Icon = o.icon
            const active = o.value === value
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => {
                  onChange(o.value)
                  setOpen(false)
                }}
                className={`flex w-full items-center gap-2.5 px-3.5 py-2.5 text-sm transition-colors ${
                  active
                    ? 'bg-indigo-50/70 font-semibold text-indigo-700'
                    : 'text-slate-700 hover:bg-slate-50'
                }`}
              >
                {Icon && (
                  <Icon size={16} className={active ? 'text-indigo-600' : 'text-slate-400'} />
                )}
                <span className="flex-1 whitespace-nowrap text-left">{o.label}</span>
                {o.badge != null && o.badge !== '' && (
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[11px] font-semibold ${
                      active ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {o.badge}
                  </span>
                )}
                {active && <Check size={15} className="text-indigo-600" />}
              </button>
            )
          })}
        </div>
      )}
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

// Page header block used across admin sections: icon chip + title + subtitle,
// with an optional action rendered on the right.
export function PageHeader({ icon: Icon, title, subtitle, iconClass, action }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-3.5">
        {Icon && (
          <div
            className={`flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl ${
              iconClass || 'bg-indigo-50 text-indigo-600'
            }`}
          >
            <Icon size={22} />
          </div>
        )}
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

// Shared header strip for a Card acting as a panel.
export function CardHeader({ icon: Icon, iconClass, title, children }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-6 py-3.5">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
        {Icon && <Icon size={16} className={iconClass || 'text-indigo-600'} />}
        {title}
      </h2>
      {children}
    </div>
  )
}

// Compact centered state row for loading / empty / error inside a Card.
export function StateRow({ children, tone = 'muted' }) {
  const cls =
    tone === 'error'
      ? 'text-red-500'
      : tone === 'strong'
        ? 'text-slate-600'
        : 'text-slate-400'
  return <p className={`px-6 py-12 text-center text-sm ${cls}`}>{children}</p>
}
