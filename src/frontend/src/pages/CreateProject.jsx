import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bot,
  Plus,
  UploadCloud,
  Link2,
  Mail,
  ArrowLeft,
  Check,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import { Card, PrimaryButton, SecondaryButton } from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { useProjects } from '../context/ProjectContext.jsx'

const INGEST_TABS = [
  { key: 'upload', label: 'Direct Upload', icon: UploadCloud },
  { key: 'link', label: 'Link Sync', icon: Link2 },
  { key: 'email', label: 'Email Listener', icon: Mail },
]

export default function CreateProject() {
  const navigate = useNavigate()
  const toast = useToast()
  const { addProject } = useProjects()

  const [jobText, setJobText] = useState('')
  const [activeTab, setActiveTab] = useState('upload')
  const [sourceValue, setSourceValue] = useState('')
  const fileInputRef = useRef(null)

  function handleAdd() {
    if (!jobText.trim()) {
      toast('Add a job description first so the AI can generate the JD.')
      return
    }
    const ingestion = {
      method: activeTab,
      label: INGEST_TABS.find((t) => t.key === activeTab).label,
      source: sourceValue || undefined,
      // Mock count so the project's source list shows ingested volume.
      count: sourceValue ? Math.floor(Math.random() * 30) + 5 : 0,
    }
    addProject({ jdInput: jobText, ingestion })
    toast('Project created — JD generated.')
    navigate('/') // back to the dashboard, where the new card now appears
  }

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        {/* Header */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100"
            title="Back to dashboard"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">New Project</h1>
            <p className="mt-1 text-sm text-slate-500">
              Describe the role and choose how to ingest candidates.
            </p>
          </div>
        </div>

        {/* Two-column layout */}
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* ---- Left: Natural Language Job Description ---- */}
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
              rows={12}
              placeholder="e.g. We are looking for a Senior Frontend Engineer who has deep experience with React, TypeScript, and performance optimization. They should have led a team before and be comfortable mentoring juniors. Knowledge of GraphQL is a big plus..."
              className="mt-4 w-full resize-none rounded-lg border border-slate-200 bg-white px-3.5 py-3 text-sm text-slate-700 placeholder-slate-400 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            />
          </Card>

          {/* ---- Right: Multi-Channel Ingestion Hub ---- */}
          <Card className="p-6">
            <h2 className="text-base font-semibold text-slate-900">
              Multi-Channel Ingestion Hub
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Select how you want to ingest candidate profiles for this project.
            </p>

            {/* Tabs */}
            <div className="mt-4 flex border-b border-slate-200">
              {INGEST_TABS.map(({ key, label, icon: Icon }) => (
                <button
                  key={key}
                  onClick={() => {
                    setActiveTab(key)
                    setSourceValue('')
                  }}
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
                    if (e.dataTransfer.files?.length) {
                      setSourceValue(e.dataTransfer.files[0].name)
                      toast(`File ready: ${e.dataTransfer.files[0].name}`)
                    }
                  }}
                  className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center"
                >
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600">
                    <UploadCloud size={22} />
                  </div>
                  <p className="mt-3 text-sm font-semibold text-slate-700">
                    {sourceValue || 'Drop ZIP file of CVs here'}
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
                        setSourceValue(e.target.files[0].name)
                        toast(`File ready: ${e.target.files[0].name}`)
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
                  <input
                    type="url"
                    value={sourceValue}
                    onChange={(e) => setSourceValue(e.target.value)}
                    placeholder="https://forms.gle/…"
                    className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                  />
                </div>
              )}

              {activeTab === 'email' && (
                <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-5">
                  <label className="block text-sm font-medium text-slate-700">
                    Shared inbox to listen on
                  </label>
                  <input
                    type="email"
                    value={sourceValue}
                    onChange={(e) => setSourceValue(e.target.value)}
                    placeholder="careers@company.com"
                    className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                  />
                </div>
              )}

              {sourceValue && (
                <p className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600">
                  <Check size={14} /> Source configured
                </p>
              )}
            </div>
          </Card>
        </div>

        {/* ---- Bottom: Add button ---- */}
        <div className="mt-6 flex justify-end gap-3">
          <SecondaryButton onClick={() => navigate('/')}>Cancel</SecondaryButton>
          <PrimaryButton onClick={handleAdd}>
            <Plus size={16} /> Add
          </PrimaryButton>
        </div>
      </main>
    </>
  )
}
