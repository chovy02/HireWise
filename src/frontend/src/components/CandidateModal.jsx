import { useEffect, useState } from 'react'
import {
  X,
  Pencil,
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
  Plus,
  Trash2,
  FileText,
  Loader2,
} from 'lucide-react'
import { Tag, PrimaryButton, SecondaryButton, Badge } from './ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { useProjects } from '../context/ProjectContext.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { getCandidateCv } from '../api/jds.js'
import { formatDateTimeWithSeconds } from '../utils/datetime.js'

// Nhúng file PDF gốc của ứng viên: fetch kèm token -> blob URL -> <iframe>.
// (iframe không tự gửi được header Authorization, nên phải fetch rồi tạo blob URL.)
function CvPdf({ candidateId }) {
  const [url, setUrl] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    let objectUrl
    setUrl(null)
    setError('')
    getCandidateCv(candidateId)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || 'Không tải được CV.')
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [candidateId])

  if (error) {
    return (
      <div className="mt-3 flex h-[60vh] flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50/50 p-6 text-center">
        <FileText size={28} className="text-slate-300" />
        <p className="mt-3 text-sm font-medium text-slate-600">
          Không hiển thị được CV gốc
        </p>
        <p className="mt-1 max-w-xs text-xs text-slate-400">{error}</p>
      </div>
    )
  }

  if (!url) {
    return (
      <div className="mt-3 flex h-[60vh] items-center justify-center rounded-lg border border-slate-200 bg-slate-50/50">
        <Loader2 size={20} className="animate-spin text-slate-400" />
      </div>
    )
  }

  return (
    <iframe
      src={url}
      title="CV gốc"
      className="mt-3 h-[72vh] w-full rounded-lg border border-slate-200"
    />
  )
}

// Friendly timestamp for the edit-history log (giờ Việt Nam, tới từng giây).
const fmt = (ts) => formatDateTimeWithSeconds(ts, ts ?? '—')

const clampScore = (v) => Math.max(0, Math.min(100, Number(v) || 0))

// Build an editable draft from a candidate's current AI evaluation.
function makeDraft(candidate) {
  const a = candidate.analysis
  return {
    score: String(candidate.score),
    matchScore: String(a.matchScore),
    totalExperience: a.profile.totalExperience,
    highestEducation: a.profile.highestEducation,
    verifiedSkills: [...a.profile.verifiedSkills],
    deductions: a.deductions.map((d) => ({
      title: d.title,
      evidence: d.evidence,
      sources: d.sources || [],
    })),
    flags: a.flags.map((f) => ({ title: f.title, detail: f.detail })),
    overrideSummary: candidate.overrideSummary || '',
  }
}

// Candidate profile popup. Replaces the old CV Analysis page/tab. Lets HR review
// the AI brief and (via the pen button) override *any* AI-written field.
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
  const [draft, setDraft] = useState(() => makeDraft(candidate))

  if (!candidate) return null
  const a = candidate.analysis

  function startEdit() {
    setDraft(makeDraft(candidate))
    setEditing(true)
  }
  function cancelEdit() {
    setDraft(makeDraft(candidate))
    setEditing(false)
  }

  // Tải file PDF gốc về máy (fetch kèm token -> blob -> anchor download).
  async function downloadCv() {
    try {
      const blob = await getCandidateCv(candidate.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${candidate.name || 'cv'}.pdf`
      link.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      toast(e.message || 'Không tải được CV.')
    }
  }

  // --- draft mutators ---
  const setField = (k, v) => setDraft((d) => ({ ...d, [k]: v }))
  const setSkill = (i, v) =>
    setDraft((d) => ({
      ...d,
      verifiedSkills: d.verifiedSkills.map((s, k) => (k === i ? v : s)),
    }))
  const addSkill = () =>
    setDraft((d) => ({ ...d, verifiedSkills: [...d.verifiedSkills, ''] }))
  const removeSkill = (i) =>
    setDraft((d) => ({
      ...d,
      verifiedSkills: d.verifiedSkills.filter((_, k) => k !== i),
    }))
  const setDeduction = (i, key, v) =>
    setDraft((d) => ({
      ...d,
      deductions: d.deductions.map((x, k) =>
        k === i ? { ...x, [key]: v } : x
      ),
    }))
  const addDeduction = () =>
    setDraft((d) => ({
      ...d,
      deductions: [...d.deductions, { title: '', evidence: '', sources: [] }],
    }))
  const removeDeduction = (i) =>
    setDraft((d) => ({
      ...d,
      deductions: d.deductions.filter((_, k) => k !== i),
    }))
  const setFlag = (i, key, v) =>
    setDraft((d) => ({
      ...d,
      flags: d.flags.map((x, k) => (k === i ? { ...x, [key]: v } : x)),
    }))
  const addFlag = () =>
    setDraft((d) => ({ ...d, flags: [...d.flags, { title: '', detail: '' }] }))
  const removeFlag = (i) =>
    setDraft((d) => ({ ...d, flags: d.flags.filter((_, k) => k !== i) }))

  function saveOverride() {
    const history = []
    const push = (field, oldValue, newValue) => {
      if (String(oldValue) !== String(newValue))
        history.push({ field, oldValue, newValue })
    }

    const newScore = clampScore(draft.score)
    const newMatch = clampScore(draft.matchScore)
    const newSkills = draft.verifiedSkills.map((s) => s.trim()).filter(Boolean)
    const newDeductions = draft.deductions
      .map((d) => ({
        title: d.title.trim(),
        evidence: d.evidence.trim(),
        sources: d.sources || [],
      }))
      .filter((d) => d.title || d.evidence)
    const newFlags = draft.flags
      .map((f) => ({ title: f.title.trim(), detail: f.detail.trim() }))
      .filter((f) => f.title || f.detail)
    const newSummary = draft.overrideSummary.trim()

    push('Suitability score', candidate.score, newScore)
    push('Match %', a.matchScore, newMatch)
    push('Total experience', a.profile.totalExperience, draft.totalExperience)
    push('Highest education', a.profile.highestEducation, draft.highestEducation)
    push(
      'Verified skills',
      a.profile.verifiedSkills.join(', '),
      newSkills.join(', ')
    )
    push(
      'AI deductions',
      a.deductions.map((d) => `${d.title}: ${d.evidence}`).join(' | '),
      newDeductions.map((d) => `${d.title}: ${d.evidence}`).join(' | ')
    )
    push(
      'Flags',
      a.flags.map((f) => `${f.title}: ${f.detail}`).join(' | '),
      newFlags.map((f) => `${f.title}: ${f.detail}`).join(' | ')
    )
    push('Evaluation note', candidate.overrideSummary || '', newSummary)

    if (history.length === 0) {
      setEditing(false)
      return
    }

    const newAnalysis = {
      ...a,
      matchScore: newMatch,
      profile: {
        ...a.profile,
        totalExperience: draft.totalExperience,
        highestEducation: draft.highestEducation,
        verifiedSkills: newSkills,
      },
      deductions: newDeductions,
      flags: newFlags,
    }
    const patch = { score: newScore, analysis: newAnalysis, overrideSummary: newSummary }
    // Keep the leaderboard skill chips in sync when skills were edited.
    if (newSkills.join(', ') !== a.profile.verifiedSkills.join(', '))
      patch.skills = newSkills

    overrideCandidate(project.id, candidate.id, patch, history, editor)
    setEditing(false)
    toast(`Evaluation overridden — leaderboard updated (editor: ${editor}).`)
  }

  const inputCls =
    'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

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
                    Đã ghi đè
                  </Badge>
                )}
                {candidate.shortlisted && (
                  <Badge variant="completed" upper={false}>
                    Đã rút gọn
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
            {editing ? (
              <>
                <SecondaryButton className="px-3 py-2" onClick={cancelEdit}>
                  Huỷ
                </SecondaryButton>
                <PrimaryButton className="px-3 py-2" onClick={saveOverride}>
                  <Save size={15} /> Lưu
                </PrimaryButton>
              </>
            ) : (
              <button
                onClick={startEdit}
                className="rounded-lg border border-slate-200 p-2 text-slate-500 transition hover:bg-slate-50"
                title="Ghi đè đánh giá AI"
              >
                <Pencil size={16} />
              </button>
            )}
            <button
              onClick={onClose}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              title="Đóng" aria-label="Đóng"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Body: score band stays fixed; on desktop each column scrolls
            independently (own scrollbar), on mobile the whole body scrolls. */}
        <div className="flex flex-1 flex-col overflow-y-auto lg:min-h-0 lg:overflow-hidden">
          {/* Score + match band */}
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 bg-slate-50/60 px-6 py-4">
            <div className="flex items-center gap-6">
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400">
                  Điểm phù hợp
                </p>
                {editing ? (
                  <div className="mt-1 flex items-center gap-2">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={draft.score}
                      onChange={(e) => setField('score', e.target.value)}
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
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400">
                  Phù hợp
                </p>
                {editing ? (
                  <div className="mt-1 flex items-center gap-1">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={draft.matchScore}
                      onChange={(e) => setField('matchScore', e.target.value)}
                      className="w-20 rounded-lg border border-indigo-300 px-2.5 py-1.5 text-lg font-bold text-emerald-600 outline-none focus:ring-2 focus:ring-indigo-100"
                    />
                    <span className="text-sm text-slate-400">%</span>
                  </div>
                ) : (
                  <span className="mt-1 inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-600">
                    <Target size={12} /> {a.matchScore}% MATCH
                  </span>
                )}
              </div>
            </div>

            {/* HR actions: leaderboard, compare, proceed */}
            {!editing && (
              <div className="flex flex-wrap gap-2">
                <SecondaryButton
                  className="px-3 py-2"
                  onClick={() => {
                    onViewLeaderboard?.()
                    onClose()
                  }}
                >
                  <Trophy size={15} /> Bảng xếp hạng
                </SecondaryButton>
                <SecondaryButton
                  className="px-3 py-2"
                  onClick={() => {
                    onCompare?.()
                    onClose()
                  }}
                >
                  <GitCompare size={15} /> So sánh
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
            )}
          </div>

          {editing && (
            <div className="border-b border-slate-100 bg-indigo-50/40 px-6 py-3">
              <p className="text-sm font-semibold text-indigo-800">
                Đang sửa đánh giá AI
              </p>
              <p className="mt-0.5 text-xs text-indigo-700/80">
                Adjust any field below. On save the profile is flagged as
                overridden, every change is logged to the edit history, and the
                leaderboard re-ranks.
              </p>
            </div>
          )}

          <div className="grid grid-cols-1 lg:min-h-0 lg:flex-1 lg:grid-cols-2 lg:grid-rows-1">
            {/* Left: editable evaluation — own scrollbar on desktop */}
            <div className="px-6 py-5 lg:min-h-0 lg:overflow-y-auto lg:border-r lg:border-slate-100">
              {/* Evaluation note */}
              {editing ? (
                <div className="mb-5">
                  <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
                    HR Evaluation Note
                  </p>
                  <textarea
                    value={draft.overrideSummary}
                    onChange={(e) => setField('overrideSummary', e.target.value)}
                    rows={2}
                    placeholder="Reason / evaluation note (optional)…"
                    className={`mt-2 resize-none ${inputCls}`}
                  />
                </div>
              ) : (
                candidate.overrideSummary && (
                  <div className="mb-5 rounded-lg border border-indigo-200 bg-indigo-50 p-4">
                    <p className="text-xs font-bold uppercase tracking-wide text-indigo-700">
                      HR Evaluation Note
                    </p>
                    <p className="mt-1 text-sm text-indigo-900">
                      {candidate.overrideSummary}
                    </p>
                  </div>
                )
              )}

              {/* Extracted profile */}
              <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
                Hồ sơ trích xuất
              </h3>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-slate-200 p-3">
                  <p className="text-xs text-slate-400">Tổng kinh nghiệm</p>
                  {editing ? (
                    <input
                      value={draft.totalExperience}
                      onChange={(e) =>
                        setField('totalExperience', e.target.value)
                      }
                      className={`mt-1 ${inputCls}`}
                    />
                  ) : (
                    <p className="mt-1 text-sm font-semibold text-slate-900">
                      {a.profile.totalExperience}
                    </p>
                  )}
                </div>
                <div className="rounded-lg border border-slate-200 p-3">
                  <p className="text-xs text-slate-400">Trình độ cao nhất</p>
                  {editing ? (
                    <input
                      value={draft.highestEducation}
                      onChange={(e) =>
                        setField('highestEducation', e.target.value)
                      }
                      className={`mt-1 ${inputCls}`}
                    />
                  ) : (
                    <p className="mt-1 text-sm font-semibold text-slate-900">
                      {a.profile.highestEducation}
                    </p>
                  )}
                </div>
              </div>

              {/* Verified skills */}
              <p className="mt-4 text-xs text-slate-400">Kỹ năng đã xác minh</p>
              {editing ? (
                <div className="mt-2 space-y-2">
                  {draft.verifiedSkills.map((s, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <input
                        value={s}
                        onChange={(e) => setSkill(i, e.target.value)}
                        className={inputCls}
                      />
                      <button
                        onClick={() => removeSkill(i)}
                        className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-500"
                        title="Xoá kỹ năng"
                      >
                        <X size={15} />
                      </button>
                    </div>
                  ))}
                  <button
                    onClick={addSkill}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-700"
                  >
                    <Plus size={14} /> Thêm kỹ năng
                  </button>
                </div>
              ) : (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {a.profile.verifiedSkills.map((s) => (
                    <Tag key={s} className="bg-indigo-50 text-indigo-700">
                      {s}
                    </Tag>
                  ))}
                </div>
              )}

              {/* AI deductions */}
              <div className="mt-6 flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
                  Điểm trừ &amp; dẫn chứng của AI
                </h3>
                {editing && (
                  <button
                    onClick={addDeduction}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-700"
                  >
                    <Plus size={14} /> Thêm
                  </button>
                )}
              </div>
              <div className="mt-3 space-y-3">
                {editing
                  ? draft.deductions.map((d, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-slate-200 p-3"
                      >
                        <div className="flex items-center gap-2">
                          <input
                            value={d.title}
                            onChange={(e) =>
                              setDeduction(i, 'title', e.target.value)
                            }
                            placeholder="Tiêu đề điểm trừ"
                            className={`${inputCls} font-semibold`}
                          />
                          <button
                            onClick={() => removeDeduction(i)}
                            className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-500"
                            title="Xoá điểm trừ"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                        <textarea
                          value={d.evidence}
                          onChange={(e) =>
                            setDeduction(i, 'evidence', e.target.value)
                          }
                          rows={2}
                          placeholder="Evidence…"
                          className={`mt-2 resize-none ${inputCls}`}
                        />
                      </div>
                    ))
                  : a.deductions.map((d) => (
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

              {/* Flags */}
              <div className="mt-6 flex items-center justify-between">
                <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-amber-600">
                  <ShieldAlert size={14} /> Thiếu / Cần lưu ý
                </h3>
                {editing && (
                  <button
                    onClick={addFlag}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-600 hover:text-amber-700"
                  >
                    <Plus size={14} /> Thêm
                  </button>
                )}
              </div>
              <div className="mt-3 space-y-3">
                {editing
                  ? draft.flags.map((f, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-amber-200 bg-amber-50 p-3"
                      >
                        <div className="flex items-center gap-2">
                          <input
                            value={f.title}
                            onChange={(e) => setFlag(i, 'title', e.target.value)}
                            placeholder="Tiêu đề cảnh báo"
                            className={`${inputCls} border-amber-200 font-semibold`}
                          />
                          <button
                            onClick={() => removeFlag(i)}
                            className="rounded-lg p-2 text-amber-500 hover:bg-amber-100"
                            title="Xoá cảnh báo"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                        <textarea
                          value={f.detail}
                          onChange={(e) => setFlag(i, 'detail', e.target.value)}
                          rows={2}
                          placeholder="Detail…"
                          className={`mt-2 resize-none ${inputCls} border-amber-200`}
                        />
                      </div>
                    ))
                  : a.flags.length > 0
                    ? a.flags.map((f) => (
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
                      ))
                    : (
                        <p className="text-xs text-slate-400">
                          Không có cảnh báo nào.
                        </p>
                      )}
              </div>
            </div>

            {/* Right: original CV + edit history — own scrollbar on desktop */}
            <div className="px-6 py-5 lg:min-h-0 lg:overflow-y-auto">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
                  CV gốc
                </h3>
                <button
                  onClick={downloadCv}
                  className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
                >
                  <Download size={13} /> Tải PDF
                </button>
              </div>

              {/* File PDF gốc của ứng viên (nhúng từ backend). */}
              <CvPdf candidateId={candidate.id} />

              {/* Edit history audit trail */}
              <h3 className="mt-6 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
                <History size={14} /> Lịch sử chỉnh sửa
              </h3>
              {candidate.editHistory.length === 0 ? (
                <p className="mt-2 text-xs text-slate-400">
                  Chưa có chỉnh sửa thủ công nào.
                </p>
              ) : (
                <div className="mt-3 space-y-2">
                  {candidate.editHistory.map((h, k) => (
                    <div
                      key={k}
                      className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-xs"
                    >
                      <p className="font-semibold text-slate-700">
                        {h.field}:{' '}
                        <span className="text-red-500 line-through">
                          {String(h.oldValue ?? '—') || '—'}
                        </span>{' '}
                        →{' '}
                        <span className="text-emerald-600">
                          {String(h.newValue) || '—'}
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
