import { useState } from 'react'
import {
  X,
  Pencil,
  Sparkles,
  Target,
  CheckCircle2,
  ShieldAlert,
  AlertTriangle,
  Download,
  Trophy,
  GitCompare,
  Check,
  History,
  Save,
} from 'lucide-react'
import { Tag, PrimaryButton, SecondaryButton, Badge } from './ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { useProjects } from '../context/ProjectContext.jsx'
import { useAuth } from '../context/AuthContext.jsx'

// Friendly timestamp for the edit-history log.
function fmt(ts) {
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

// Candidate profile popup. Replaces the old CV Analysis page/tab. Lets HR review
// the AI brief and (via the pen button) override the score / evaluation.
export default function CandidateModal({
  project,
  candidate,
  onClose,
  onViewLeaderboard,
  onCompare,
}) {
  const toast = useToast()
  const { overrideCandidate, toggleShortlist } = useProjects()
  const { user } = useAuth()
  const editor = user?.name || user?.email || 'HR'

  const [editing, setEditing] = useState(false)
  const [scoreDraft, setScoreDraft] = useState(String(candidate.score))
  const [summaryDraft, setSummaryDraft] = useState(
    candidate.overrideSummary || ''
  )

  if (!candidate) return null
  const a = candidate.analysis

  function saveOverride() {
    const next = Math.max(0, Math.min(100, Number(scoreDraft) || 0))
    const changes = { score: next }
    if (summaryDraft.trim()) changes.overrideSummary = summaryDraft.trim()
    overrideCandidate(project.id, candidate.id, changes, editor)
    setEditing(false)
    toast(`Evaluation overridden — leaderboard updated (editor: ${editor}).`)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Dialog */}
      <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-indigo-50 text-base font-semibold text-indigo-600">
              {candidate.name[0]}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-slate-900">
                  {candidate.name}
                </h2>
                {candidate.overridden && (
                  <Badge variant="new" upper={false}>
                    Overridden
                  </Badge>
                )}
                {candidate.shortlisted && (
                  <Badge variant="completed" upper={false}>
                    Shortlisted
                  </Badge>
                )}
              </div>
              <p className="text-xs text-slate-400">
                {candidate.title} • {candidate.years} years • Rank #
                {candidate.rank}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* PEN: toggle override edit mode */}
            <button
              onClick={() => setEditing((v) => !v)}
              className={`rounded-lg border p-2 transition ${
                editing
                  ? 'border-indigo-300 bg-indigo-50 text-indigo-600'
                  : 'border-slate-200 text-slate-500 hover:bg-slate-50'
              }`}
              title="Override AI evaluation"
            >
              <Pencil size={16} />
            </button>
            <button
              onClick={onClose}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              title="Close"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto">
          {/* Score + match band */}
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 bg-slate-50/60 px-6 py-4">
            <div className="flex items-center gap-6">
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400">
                  Suitability Score
                </p>
                {editing ? (
                  <div className="mt-1 flex items-center gap-2">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={scoreDraft}
                      onChange={(e) => setScoreDraft(e.target.value)}
                      className="w-20 rounded-lg border border-indigo-300 px-2.5 py-1.5 text-lg font-bold text-slate-900 outline-none focus:ring-2 focus:ring-indigo-100"
                    />
                    <span className="text-sm text-slate-400">/ 100</span>
                  </div>
                ) : (
                  <p className="mt-1 text-2xl font-bold text-slate-900">
                    {candidate.score}
                    <span className="text-base font-medium text-slate-400">
                      /100
                    </span>
                  </p>
                )}
                {candidate.overridden && (
                  <p className="mt-0.5 text-xs text-slate-400">
                    AI original: {candidate.aiScore}
                  </p>
                )}
              </div>
              <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-600">
                <Target size={12} /> {a.matchScore}% MATCH
              </span>
            </div>

            {/* HR actions: open profile (this modal), leaderboard, compare, proceed */}
            <div className="flex flex-wrap gap-2">
              <SecondaryButton
                className="px-3 py-2"
                onClick={() => {
                  onViewLeaderboard?.()
                  onClose()
                }}
              >
                <Trophy size={15} /> Leaderboard
              </SecondaryButton>
              <SecondaryButton
                className="px-3 py-2"
                onClick={() => {
                  onCompare?.()
                  onClose()
                }}
              >
                <GitCompare size={15} /> Compare
              </SecondaryButton>
              <PrimaryButton
                className="px-3 py-2"
                onClick={() => {
                  toggleShortlist(project.id, candidate.id)
                  toast(
                    candidate.shortlisted
                      ? 'Removed from shortlist.'
                      : 'Proceeded to shortlist.'
                  )
                }}
              >
                <Check size={15} />{' '}
                {candidate.shortlisted ? 'Shortlisted' : 'Proceed to Shortlist'}
              </PrimaryButton>
            </div>
          </div>

          {/* Override editor */}
          {editing && (
            <div className="border-b border-slate-100 bg-indigo-50/40 px-6 py-4">
              <p className="text-sm font-semibold text-slate-800">
                Override AI Evaluation
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                Adjust the score and (optionally) add an evaluation note. The
                profile will be flagged as overridden and the change recorded in
                the edit history.
              </p>
              <textarea
                value={summaryDraft}
                onChange={(e) => setSummaryDraft(e.target.value)}
                rows={2}
                placeholder="Reason / evaluation note (optional)…"
                className="mt-3 w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
              <div className="mt-3 flex justify-end gap-2">
                <SecondaryButton
                  className="px-3 py-2"
                  onClick={() => {
                    setEditing(false)
                    setScoreDraft(String(candidate.score))
                    setSummaryDraft(candidate.overrideSummary || '')
                  }}
                >
                  Cancel
                </SecondaryButton>
                <PrimaryButton className="px-3 py-2" onClick={saveOverride}>
                  <Save size={15} /> Save Override
                </PrimaryButton>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-6 px-6 py-5 lg:grid-cols-2">
            {/* Left: extracted profile + deductions + flags */}
            <div>
              {candidate.overrideSummary && (
                <div className="mb-5 rounded-lg border border-indigo-200 bg-indigo-50 p-4">
                  <p className="text-xs font-bold uppercase tracking-wide text-indigo-700">
                    HR Evaluation Note
                  </p>
                  <p className="mt-1 text-sm text-indigo-900">
                    {candidate.overrideSummary}
                  </p>
                </div>
              )}

              <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
                Extracted Profile
              </h3>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-slate-200 p-3">
                  <p className="text-xs text-slate-400">Total Experience</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">
                    {a.profile.totalExperience}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-200 p-3">
                  <p className="text-xs text-slate-400">Highest Education</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">
                    {a.profile.highestEducation}
                  </p>
                </div>
              </div>
              <p className="mt-4 text-xs text-slate-400">Verified Skills</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {a.profile.verifiedSkills.map((s) => (
                  <Tag key={s} className="bg-indigo-50 text-indigo-700">
                    {s}
                  </Tag>
                ))}
              </div>

              <h3 className="mt-6 text-xs font-bold uppercase tracking-wide text-slate-500">
                AI Deductions &amp; Evidence
              </h3>
              <div className="mt-3 space-y-3">
                {a.deductions.map((d) => (
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
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {a.flags.length > 0 && (
                <>
                  <h3 className="mt-6 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-amber-600">
                    <ShieldAlert size={14} /> Missing / Flagged
                  </h3>
                  <div className="mt-3 space-y-3">
                    {a.flags.map((f) => (
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
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Right: resume + edit history */}
            <div>
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
                  Résumé
                </h3>
                <button
                  onClick={() => toast('Original PDF → download (mock)')}
                  className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
                >
                  <Download size={13} /> {a.fileName}
                </button>
              </div>
              <div className="mt-3 rounded-lg border border-slate-200 bg-white p-5">
                <h4 className="font-serif text-2xl font-bold text-slate-900">
                  {a.resume.name}
                </h4>
                <p className="mt-1 text-sm text-slate-500">
                  {a.resume.headline}
                </p>
                <hr className="my-4 border-slate-200" />
                <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
                  Experience
                </p>
                <div className="mt-3 space-y-4">
                  {a.resume.experience.map((job, ji) => (
                    <div key={ji}>
                      <div className="flex items-baseline justify-between">
                        <h5 className="text-sm font-bold text-slate-900">
                          {job.role}
                        </h5>
                        <span className="text-xs text-slate-500">
                          {job.company} • {job.period}
                        </span>
                      </div>
                      <ul className="mt-1.5 space-y-1">
                        {job.bullets.map((b, bi) => (
                          <li
                            key={bi}
                            className="flex gap-2 text-xs leading-relaxed text-slate-600"
                          >
                            <span className="mt-1.5 h-1 w-1 flex-shrink-0 rounded-full bg-slate-400" />
                            <span>{b}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>

              {/* Edit history audit trail */}
              <h3 className="mt-6 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
                <History size={14} /> Edit History
              </h3>
              {candidate.editHistory.length === 0 ? (
                <p className="mt-2 text-xs text-slate-400">
                  No manual overrides yet.
                </p>
              ) : (
                <div className="mt-3 space-y-2">
                  {candidate.editHistory.map((h, k) => (
                    <div
                      key={k}
                      className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-xs"
                    >
                      <p className="font-semibold text-slate-700">
                        {h.field === 'score'
                          ? 'Score'
                          : h.field === 'overrideSummary'
                            ? 'Evaluation note'
                            : h.field}
                        :{' '}
                        <span className="text-red-500 line-through">
                          {String(h.oldValue ?? '—')}
                        </span>{' '}
                        →{' '}
                        <span className="text-emerald-600">
                          {String(h.newValue)}
                        </span>
                      </p>
                      <p className="mt-0.5 text-slate-400">
                        by {h.editor} • {fmt(h.timestamp)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
