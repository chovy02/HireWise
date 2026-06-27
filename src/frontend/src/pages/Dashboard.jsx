import { useRef, useState } from 'react'
import {
  Bot,
  FileText,
  CheckCircle2,
  Plus,
  UploadCloud,
  Link2,
  Mail,
  RefreshCw,
  AlertTriangle,
  XCircle,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  StatCard,
  Badge,
  ProgressBar,
  DarkButton,
  PrimaryButton,
} from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import {
  dashboardStats,
  ingestionQueue,
  systemAlerts,
} from '../data/mockData.js'

const STAT_ICONS = {
  drives: { icon: Bot, cls: 'bg-indigo-50 text-indigo-600' },
  cvs: { icon: FileText, cls: 'bg-emerald-50 text-emerald-600' },
  insights: { icon: CheckCircle2, cls: 'bg-violet-50 text-violet-600' },
}

const QUEUE_STATUS = {
  processing: { variant: 'processing', icon: RefreshCw },
  completed: { variant: 'completed', icon: CheckCircle2 },
  error: { variant: 'error', icon: XCircle },
}

const ALERT_STYLES = {
  success: { icon: CheckCircle2, cls: 'text-emerald-500' },
  warning: { icon: AlertTriangle, cls: 'text-amber-500' },
  error: { icon: XCircle, cls: 'text-red-500' },
}

const INGEST_TABS = [
  { key: 'upload', label: 'Direct Upload', icon: UploadCloud },
  { key: 'link', label: 'Link Sync', icon: Link2 },
  { key: 'email', label: 'Email Listener', icon: Mail },
]

export default function Dashboard() {
  const toast = useToast()
  const [jobText, setJobText] = useState('')
  const [activeTab, setActiveTab] = useState('upload')
  const fileInputRef = useRef(null)

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        {/* Page header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              Recruitment Dashboard
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Manage active drives and candidate ingestion.
            </p>
          </div>
          {/* BUTTON: New Campaign -> POST /api/job-descriptions (create a drive) */}
          <PrimaryButton
            onClick={() =>
              toast('New Campaign → POST /api/job-descriptions (create a drive)')
            }
          >
            <Plus size={16} /> New Campaign
          </PrimaryButton>
        </div>

        {/* Stat cards */}
        <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-3">
          {dashboardStats.map((s) => {
            const { icon, cls } = STAT_ICONS[s.key]
            return (
              <StatCard
                key={s.key}
                icon={icon}
                iconClass={cls}
                label={s.label}
                value={s.value}
                footnote={s.footnote}
              />
            )
          })}
        </div>

        {/* Two-column grid */}
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* ---- Left column ---- */}
          <div className="space-y-6">
            {/* Natural Language Job Description */}
            <Card className="p-6">
              <div className="flex items-center gap-2">
                <Bot size={20} className="text-indigo-600" />
                <h2 className="text-base font-semibold text-slate-900">
                  Natural Language Job Description
                </h2>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">
                Describe the ideal candidate, required skills, and cultural fit in
                plain English. Our AI will automatically extract requirements and
                build a scoring matrix.
              </p>
              <textarea
                value={jobText}
                onChange={(e) => setJobText(e.target.value)}
                rows={6}
                placeholder="e.g. We are looking for a Senior Frontend Engineer who has deep experience with React, TypeScript, and performance optimization. They should have led a team before and be comfortable mentoring juniors. Knowledge of GraphQL is a big plus..."
                className="mt-4 w-full resize-none rounded-lg border border-slate-200 bg-white px-3.5 py-3 text-sm text-slate-700 placeholder-slate-400 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
              <div className="mt-4 flex justify-end">
                {/* BUTTON: Generate Scoring Matrix -> POST /api/job-descriptions
                    (sends raw_text, AI returns jd_markdown + requirements matrix) */}
                <DarkButton
                  onClick={() =>
                    toast(
                      'Generate Scoring Matrix → POST /api/job-descriptions (AI extracts requirements)'
                    )
                  }
                >
                  Generate Scoring Matrix
                </DarkButton>
              </div>
            </Card>

            {/* Multi-Channel Ingestion Hub */}
            <Card className="p-6">
              <h2 className="text-base font-semibold text-slate-900">
                Multi-Channel Ingestion Hub
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Connect sources to autonomously ingest candidate profiles.
              </p>

              {/* Tabs */}
              <div className="mt-4 flex border-b border-slate-200">
                {INGEST_TABS.map(({ key, label, icon: Icon }) => (
                  <button
                    key={key}
                    onClick={() => setActiveTab(key)}
                    className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
                      activeTab === key
                        ? 'border-indigo-600 text-indigo-600'
                        : 'border-transparent text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    <Icon size={16} /> {label}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <div className="mt-5">
                {activeTab === 'upload' && (
                  <div
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault()
                      // BUTTON/ACTION: drop ZIP -> POST /api/ingestion/upload (multipart)
                      toast(
                        'File dropped → POST /api/ingestion/upload (multipart ZIP/PDF)'
                      )
                    }}
                    className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center"
                  >
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600">
                      <UploadCloud size={22} />
                    </div>
                    <p className="mt-3 text-sm font-semibold text-slate-700">
                      Drop ZIP file of CVs here
                    </p>
                    <p className="mt-1 text-xs text-slate-400">
                      Supports PDF, DOCX, up to 50MB
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".zip,.pdf,.docx"
                      className="hidden"
                      onChange={(e) => {
                        if (e.target.files?.length) {
                          // BUTTON: Browse Files -> POST /api/ingestion/upload (multipart)
                          toast(
                            `Selected "${e.target.files[0].name}" → POST /api/ingestion/upload`
                          )
                        }
                      }}
                    />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                    >
                      Browse Files
                    </button>
                  </div>
                )}

                {activeTab === 'link' && (
                  <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-5">
                    <label className="block text-sm font-medium text-slate-700">
                      Google Forms / sheet URL
                    </label>
                    <div className="mt-2 flex gap-2">
                      <input
                        type="url"
                        placeholder="https://forms.gle/…"
                        className="flex-1 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                      />
                      {/* BUTTON: Connect link -> POST /api/ingestion/link */}
                      <PrimaryButton
                        onClick={() =>
                          toast('Link Sync → POST /api/ingestion/link')
                        }
                      >
                        Connect
                      </PrimaryButton>
                    </div>
                  </div>
                )}

                {activeTab === 'email' && (
                  <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-5">
                    <label className="block text-sm font-medium text-slate-700">
                      Shared inbox to listen on
                    </label>
                    <div className="mt-2 flex gap-2">
                      <input
                        type="email"
                        placeholder="careers@company.com"
                        className="flex-1 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                      />
                      {/* BUTTON: Connect email -> POST /api/ingestion/email */}
                      <PrimaryButton
                        onClick={() =>
                          toast('Email Listener → POST /api/ingestion/email')
                        }
                      >
                        Connect
                      </PrimaryButton>
                    </div>
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* ---- Right column ---- */}
          <Card className="p-6">
            {/* Ingestion Queue (data: GET /api/ingestion/queue) */}
            <h2 className="text-base font-semibold text-slate-900">
              Ingestion Queue
            </h2>
            <div className="mt-4 space-y-3">
              {ingestionQueue.map((item) => {
                const { variant, icon: Icon } = QUEUE_STATUS[item.status]
                return (
                  <div
                    key={item.id}
                    className="rounded-xl border border-slate-200 p-4"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-sm font-semibold text-slate-800">
                          {item.title}
                        </p>
                        <p className="text-xs text-slate-400">{item.source}</p>
                      </div>
                      <Badge variant={variant}>
                        <Icon size={11} /> {item.statusLabel}
                      </Badge>
                    </div>
                    <div className="mt-3 flex items-center justify-between text-xs">
                      <span className="text-slate-500">{item.detail}</span>
                      <span className="font-semibold text-slate-700">
                        {item.progress}%
                      </span>
                    </div>
                    <div className="mt-2">
                      <ProgressBar value={item.progress} color={item.color} />
                    </div>
                  </div>
                )
              })}
            </div>

            {/* System Alerts (data: GET /api/system/alerts) */}
            <h2 className="mt-8 text-base font-semibold text-slate-900">
              System Alerts
            </h2>
            <div className="mt-4 space-y-3">
              {systemAlerts.map((alert) => {
                const { icon: Icon, cls } = ALERT_STYLES[alert.level]
                return (
                  <div key={alert.id} className="flex items-start gap-2.5">
                    <Icon size={16} className={`mt-0.5 flex-shrink-0 ${cls}`} />
                    <p className="text-sm leading-relaxed text-slate-600">
                      {alert.text}
                    </p>
                  </div>
                )
              })}
            </div>
          </Card>
        </div>
      </main>
    </>
  )
}
