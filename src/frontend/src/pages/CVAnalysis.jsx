import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Download,
  Sparkles,
  Target,
  CheckCircle2,
  ShieldAlert,
  AlertTriangle,
} from 'lucide-react'
import { Tag, PrimaryButton, SecondaryButton } from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { cvAnalysis } from '../data/mockData.js'

// Which CV bullet(s) each AI deduction points at, so "highlight source" works.
const DEDUCTION_SOURCES = {
  'Strong Leadership Experience': ['exp-0-0', 'exp-0-2'],
  'Deep React/TS Ecosystem Knowledge': ['exp-0-0', 'exp-1-0'],
}

export default function CVAnalysis() {
  const navigate = useNavigate()
  const toast = useToast()
  const cv = cvAnalysis

  const [highlighted, setHighlighted] = useState([])
  const [dismissedFlags, setDismissedFlags] = useState([])

  const isHot = (key) => highlighted.includes(key)
  const visibleFlags = cv.flags.filter((f) => !dismissedFlags.includes(f.title))

  return (
    <div className="flex h-full flex-col">
      {/* ---- Custom header (replaces the standard Topbar) ---- */}
      <header className="flex h-16 flex-shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
        <div className="flex items-center gap-3">
          {/* BUTTON: back -> previous page (shortlisting) */}
          <button
            onClick={() => navigate(-1)}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100"
            title="Back"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <p className="text-sm font-semibold text-slate-900">{cv.fileName}</p>
            <p className="text-xs text-slate-400">{cv.processedBy}</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          {/* BUTTON: Original PDF -> GET /api/candidates/:id/file (download) */}
          <SecondaryButton
            onClick={() => toast('Original PDF → GET /api/candidates/:id/file')}
          >
            <Download size={15} /> Original PDF
          </SecondaryButton>
          {/* BUTTON: Approve Candidate -> POST /api/shortlist/:itemId/approve */}
          <PrimaryButton
            onClick={() =>
              toast('Approve Candidate → POST /api/shortlist/:itemId/approve')
            }
          >
            Approve Candidate
          </PrimaryButton>
        </div>
      </header>

      {/* ---- Body split: CV document | Intelligence Brief ---- */}
      <div className="flex flex-1 flex-col overflow-hidden lg:flex-row">
        {/* CV document */}
        <div className="flex-1 overflow-y-auto bg-slate-100 p-6 lg:p-10">
          <div className="mx-auto max-w-2xl rounded-md bg-white p-10 shadow-sm ring-1 ring-slate-200/60">
            <h1 className="font-serif text-4xl font-bold text-slate-900">
              {cv.resume.name}
            </h1>
            <p className="mt-2 text-slate-500">{cv.resume.headline}</p>
            <hr className="my-6 border-slate-200" />

            <section>
              <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">
                Experience
              </h2>
              <div className="mt-4 space-y-6">
                {cv.resume.experience.map((job, ji) => (
                  <div key={ji}>
                    <div className="flex items-baseline justify-between">
                      <h3 className="font-bold text-slate-900">{job.role}</h3>
                      <span className="text-sm text-slate-500">
                        {job.company} • {job.period}
                      </span>
                    </div>
                    <ul className="mt-2 space-y-1.5">
                      {job.bullets.map((b, bi) => {
                        const key = `exp-${ji}-${bi}`
                        return (
                          <li
                            key={bi}
                            className={`flex gap-2 rounded px-1 text-sm leading-relaxed text-slate-700 transition-colors ${
                              isHot(key) ? 'bg-amber-100' : ''
                            }`}
                          >
                            <span className="mt-1.5 h-1 w-1 flex-shrink-0 rounded-full bg-slate-400" />
                            <span>{b}</span>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            </section>

            <section className="mt-8">
              <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">
                Education
              </h2>
              <div className="mt-4 space-y-3">
                {cv.resume.education.map((ed, i) => (
                  <div key={i}>
                    <h3 className="font-bold text-slate-900">{ed.degree}</h3>
                    <p className="text-sm text-slate-500">
                      {ed.school} • {ed.period}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>

        {/* Intelligence Brief */}
        <aside className="w-full flex-shrink-0 overflow-y-auto border-l border-slate-200 bg-white p-6 lg:w-[440px]">
          {/* Header */}
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 text-white">
              <Sparkles size={20} />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">
                Intelligence Brief
              </h2>
              <div className="mt-1 flex items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-600">
                  <Target size={12} /> {cv.matchScore}% MATCH
                </span>
                <span className="text-xs text-slate-400">
                  Processed in {cv.processedIn}
                </span>
              </div>
            </div>
          </div>

          {/* Extracted profile */}
          <div className="mt-7">
            <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
              <FileIcon /> Extracted Profile
            </h3>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <div className="rounded-lg border border-slate-200 p-3">
                <p className="text-xs text-slate-400">Total Experience</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">
                  {cv.profile.totalExperience}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 p-3">
                <p className="text-xs text-slate-400">Highest Education</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">
                  {cv.profile.highestEducation}
                </p>
              </div>
            </div>
            <p className="mt-4 text-xs text-slate-400">Verified Skills</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {cv.profile.verifiedSkills.map((s) => (
                <Tag key={s} className="bg-indigo-50 text-indigo-700">
                  {s}
                </Tag>
              ))}
            </div>
          </div>

          {/* AI deductions */}
          <div className="mt-7">
            <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
              AI Deductions &amp; Evidence
            </h3>
            <div className="mt-3 space-y-3">
              {cv.deductions.map((d) => (
                <div
                  key={d.title}
                  className="rounded-lg border border-slate-200 p-4"
                >
                  <div className="flex items-start gap-2">
                    <CheckCircle2
                      size={16}
                      className="mt-0.5 flex-shrink-0 text-slate-400"
                    />
                    <div>
                      <p className="text-sm font-semibold text-slate-800">
                        {d.title}
                      </p>
                      <p className="mt-1 text-xs leading-relaxed text-slate-500">
                        {d.evidence}
                      </p>
                      {/* HOVER: highlight the cited bullet(s) in the CV.
                          Backend source maps to Evaluation.evidence offsets. */}
                      <button
                        onMouseEnter={() =>
                          setHighlighted(DEDUCTION_SOURCES[d.title] || [])
                        }
                        onMouseLeave={() => setHighlighted([])}
                        className="mt-2 flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-700"
                      >
                        <Sparkles size={13} /> Hover to highlight source in
                        document
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Missing / flagged */}
          {visibleFlags.length > 0 && (
            <div className="mt-7">
              <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-amber-600">
                <ShieldAlert size={14} /> Missing / Flagged Information
              </h3>
              <div className="mt-3 space-y-3">
                {visibleFlags.map((f) => (
                  <div
                    key={f.title}
                    className="rounded-lg border border-amber-200 bg-amber-50 p-4"
                  >
                    <div className="flex items-start gap-2">
                      <AlertTriangle
                        size={16}
                        className="mt-0.5 flex-shrink-0 text-amber-500"
                      />
                      <div>
                        <p className="text-sm font-semibold text-amber-800">
                          {f.title}
                        </p>
                        <p className="mt-1 text-xs leading-relaxed text-amber-700">
                          {f.detail}
                        </p>
                        {/* BUTTON: Acknowledge & Dismiss -> PATCH /api/evaluations/:id
                            (mark flag acknowledged). Hidden client-side for now. */}
                        <button
                          onClick={() =>
                            setDismissedFlags((list) => [...list, f.title])
                          }
                          className="mt-2 text-xs font-semibold text-amber-800 underline hover:text-amber-900"
                        >
                          Acknowledge &amp; Dismiss
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

// Tiny inline file glyph for the "Extracted Profile" heading.
function FileIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  )
}
