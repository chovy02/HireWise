import { useState } from 'react'
import {
  ShieldCheck,
  Activity,
  Server,
  SlidersHorizontal,
  AlertTriangle,
  Users,
  Plus,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  Segmented,
  Toggle,
  PrimaryButton,
  DarkButton,
} from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import {
  adminStats,
  llmInvocations,
  llmLimit,
  errorLogs,
  rbacRoles,
  rbacPermissions,
} from '../data/mockData.js'

export default function AdminGateway() {
  const [tab, setTab] = useState('Agent Monitor')

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
              Manage AI agents, system resources, and access control.
            </p>
          </div>
          {/* SWITCH: Agent Monitor | Access Control */}
          <Segmented
            options={['Agent Monitor', 'Access Control (RBAC)']}
            value={tab}
            onChange={setTab}
          />
        </div>

        {tab === 'Agent Monitor' ? <AgentMonitor /> : <AccessControl />}
      </main>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Agent Monitor tab                                                   */
/* ------------------------------------------------------------------ */
function AgentMonitor() {
  const toast = useToast()

  return (
    <>
      {/* Stat cards (data: GET /api/admin/metrics) */}
      <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <AdminStat
          icon={Activity}
          iconClass="bg-indigo-50 text-indigo-600"
          label="System Status"
          value={adminStats.systemStatus}
          valueClass="text-emerald-600"
        />
        <AdminStat
          icon={Server}
          iconClass="bg-blue-50 text-blue-600"
          label="API Calls (24h)"
          value={adminStats.apiCalls}
          suffix={` / ${adminStats.apiLimit}`}
        />
        <AdminStat
          icon={SlidersHorizontal}
          iconClass="bg-violet-50 text-violet-600"
          label="Active Agents"
          value={adminStats.activeAgents}
          suffix=" Running"
          suffixClass="text-emerald-600"
        />
        <AdminStat
          icon={AlertTriangle}
          iconClass="bg-red-50 text-red-600"
          label="Error Rate"
          value={adminStats.errorRate}
          suffix=" Normal"
        />
      </div>

      {/* Charts */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* LLM Tool Invocations */}
        <Card className="p-6 lg:col-span-2">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-base font-semibold text-slate-900">
                LLM Tool Invocations
              </h2>
              <p className="mt-0.5 text-sm text-slate-500">
                API usage vs. Rate Limits over 24 hours
              </p>
            </div>
            {/* CONTROL: time range -> GET /api/admin/metrics?range=… */}
            <select
              onChange={(e) =>
                toast(`Range: ${e.target.value} → GET /api/admin/metrics`)
              }
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600 outline-none focus:border-indigo-500"
            >
              <option>Last 24 Hours</option>
              <option>Last 7 Days</option>
              <option>Last 30 Days</option>
            </select>
          </div>
          <AreaChart data={llmInvocations} limit={llmLimit} />
        </Card>

        {/* Security & Error Logs */}
        <Card className="flex flex-col p-6">
          <h2 className="text-base font-semibold text-slate-900">
            Security &amp; Error Logs
          </h2>
          <p className="mt-0.5 text-sm text-slate-500">
            Distribution of failed operations
          </p>
          <div className="mt-6 flex-1 space-y-5">
            {errorLogs.map((e) => (
              <div key={e.label} className="flex items-center gap-3">
                <span className="w-20 flex-shrink-0 text-right text-xs text-slate-500">
                  {e.label}
                </span>
                <div className="h-5 flex-1">
                  <div
                    className="h-full rounded bg-rose-500"
                    style={{ width: `${e.value}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
          {/* BUTTON: View Full Logs -> GET /api/admin/logs */}
          <button
            onClick={() => toast('View Full Logs → GET /api/admin/logs')}
            className="mt-6 text-center text-sm font-medium text-indigo-600 hover:text-indigo-700"
          >
            View Full Logs →
          </button>
        </Card>
      </div>
    </>
  )
}

function AdminStat({
  icon: Icon,
  iconClass,
  label,
  value,
  valueClass = 'text-slate-900',
  suffix,
  suffixClass = 'text-slate-400',
}) {
  return (
    <Card className="flex items-center gap-4 p-5">
      <div
        className={`flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg ${iconClass}`}
      >
        <Icon size={20} />
      </div>
      <div>
        <p className="text-sm font-medium text-slate-500">{label}</p>
        <p className="mt-0.5 text-xl font-bold">
          <span className={valueClass}>{value}</span>
          {suffix && (
            <span className={`text-sm font-medium ${suffixClass}`}>{suffix}</span>
          )}
        </p>
      </div>
    </Card>
  )
}

// Smooth area chart built with inline SVG (no chart library needed).
function AreaChart({ data, limit }) {
  const W = 700
  const H = 300
  const padL = 40
  const padR = 20
  const padT = 20
  const padB = 30
  const plotW = W - padL - padR
  const plotH = H - padT - padB
  const max = limit

  const points = data.map((d, i) => ({
    x: padL + (i / (data.length - 1)) * plotW,
    y: padT + (1 - d.v / max) * plotH,
    label: d.t,
  }))

  const line = smoothPath(points)
  const area = `${line} L ${points[points.length - 1].x} ${padT + plotH} L ${
    points[0].x
  } ${padT + plotH} Z`

  const yTicks = [0, 250, 500, 750, 1000]
  const limitY = padT + (1 - limit / max) * plotH

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="mt-4 w-full"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6366f1" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#6366f1" stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {/* gridlines + y labels */}
      {yTicks.map((t) => {
        const y = padT + (1 - t / max) * plotH
        return (
          <g key={t}>
            <line
              x1={padL}
              y1={y}
              x2={W - padR}
              y2={y}
              stroke="#eef1f6"
              strokeWidth="1"
            />
            <text x={padL - 8} y={y + 4} textAnchor="end" className="fill-slate-400" fontSize="11">
              {t}
            </text>
          </g>
        )
      })}

      {/* rate-limit dashed line */}
      <line
        x1={padL}
        y1={limitY}
        x2={W - padR}
        y2={limitY}
        stroke="#ef4444"
        strokeWidth="1.5"
        strokeDasharray="6 5"
      />

      {/* area + line */}
      <path d={area} fill="url(#areaFill)" />
      <path d={line} fill="none" stroke="#6366f1" strokeWidth="2.5" />

      {/* x labels (every other point to avoid crowding) */}
      {points.map((p, i) =>
        i % 2 === 0 ? (
          <text
            key={i}
            x={p.x}
            y={H - 8}
            textAnchor="middle"
            className="fill-slate-400"
            fontSize="11"
          >
            {p.label}
          </text>
        ) : null
      )}
    </svg>
  )
}

// Catmull-Rom spline -> cubic bezier path for a smooth curve.
function smoothPath(pts) {
  if (pts.length < 2) return ''
  let d = `M ${pts[0].x} ${pts[0].y}`
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[i + 2] || p2
    const cp1x = p1.x + (p2.x - p0.x) / 6
    const cp1y = p1.y + (p2.y - p0.y) / 6
    const cp2x = p2.x - (p3.x - p1.x) / 6
    const cp2y = p2.y - (p3.y - p1.y) / 6
    d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`
  }
  return d
}

/* ------------------------------------------------------------------ */
/* Access Control (RBAC) tab                                           */
/* ------------------------------------------------------------------ */
const ROLE_ICONS = { shield: ShieldCheck, users: Users }

function AccessControl() {
  const toast = useToast()

  // Seed editable toggle state from mock data.
  const [perms, setPerms] = useState(() =>
    Object.fromEntries(rbacPermissions.map((p) => [p.key, { ...p.values }]))
  )

  function toggle(permKey, roleKey, next) {
    setPerms((prev) => ({
      ...prev,
      [permKey]: { ...prev[permKey], [roleKey]: next },
    }))
  }

  return (
    <Card className="mt-6 p-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-900">
            Role-Based Access Control
          </h2>
          <p className="mt-0.5 text-sm text-slate-500">
            Configure permissions for different user groups.
          </p>
        </div>
        {/* BUTTON: Add New Role -> POST /api/admin/roles */}
        <PrimaryButton onClick={() => toast('Add New Role → POST /api/admin/roles')}>
          <Plus size={16} /> Add New Role
        </PrimaryButton>
      </div>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[640px]">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Permission Level
              </th>
              {rbacRoles.map((r) => {
                const Icon = ROLE_ICONS[r.icon]
                return (
                  <th key={r.key} className="px-4 py-3 text-center">
                    <div className="flex flex-col items-center gap-0.5">
                      <Icon size={16} className="text-indigo-500" />
                      <span className="text-xs font-bold uppercase tracking-wide text-slate-700">
                        {r.name}
                      </span>
                      <span className="text-[11px] font-normal normal-case text-slate-400">
                        {r.subtitle}
                      </span>
                    </div>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rbacPermissions.map((p) => (
              <tr key={p.key}>
                <td className="px-4 py-4">
                  <p className="text-sm font-semibold text-slate-800">{p.label}</p>
                  <p className="text-xs text-slate-400">{p.sub}</p>
                </td>
                {rbacRoles.map((r) => (
                  <td key={r.key} className="px-4 py-4">
                    <div className="flex justify-center">
                      <Toggle
                        checked={perms[p.key][r.key]}
                        // System Admin always has full access -> locked on.
                        disabled={r.key === 'admin'}
                        onChange={(next) => toggle(p.key, r.key, next)}
                      />
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-6 flex justify-end">
        {/* BUTTON: Save Changes -> PUT /api/admin/permissions (sends matrix) */}
        <DarkButton
          onClick={() => toast('Save Changes → PUT /api/admin/permissions')}
        >
          Save Changes
        </DarkButton>
      </div>
    </Card>
  )
}
