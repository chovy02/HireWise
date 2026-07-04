import { useEffect, useState } from 'react'
import {
  X,
  Pencil,
  Save,
  Target,
  CheckCircle2,
  AlertTriangle,
  Github,
  FolderGit2,
  Sparkles,
  FileText,
  Loader2,
} from 'lucide-react'
import { Tag, Badge, ProgressBar, PrimaryButton, SecondaryButton } from './ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { getCandidate, overrideEvaluation, getCandidateCv } from '../api/jds.js'

const STATUS_BADGE = {
  COMPLETED: { variant: 'completed', label: 'Hoàn tất' },
  PENDING: { variant: 'processing', label: 'Đang xử lý' },
  FAILED: { variant: 'error', label: 'Lỗi' },
}

const BREAKDOWN_LABEL = {
  skills_match: 'Kỹ năng',
  experience_match: 'Kinh nghiệm',
  education_match: 'Học vấn',
}

const clampScore = (v) => Math.max(0, Math.min(100, Number(v) || 0))

// Nhúng file PDF gốc của ứng viên: fetch kèm token -> blob URL -> <iframe>.
// (iframe không tự gửi được header Authorization nên phải fetch rồi tạo blob URL.)
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
      .catch((e) => !cancelled && setError(e.message || 'Không tải được CV.'))
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
          Không hiển thị được CV gốc (PDF)
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

// Modal chi tiết ứng viên — dữ liệu THẬT từ backend. Cột phải nhúng file PDF gốc;
// bằng chứng điểm mạnh/yếu hiển thị nguyên văn (trích dẫn) ở cột trái.
export default function CandidateDetailModal({ candidateId, onClose, onOverridden }) {
  const toast = useToast()
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [draftScore, setDraftScore] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    getCandidate(candidateId)
      .then((d) => {
        if (cancelled) return
        setDetail(d)
        setDraftScore(d.evaluation ? String(d.evaluation.score) : '')
      })
      .catch((e) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [candidateId])

  async function saveOverride() {
    const evaluation = detail?.evaluation
    if (!evaluation) return
    if (!reason.trim()) {
      toast('Nhập lý do chỉnh điểm trước khi lưu.')
      return
    }
    const newScore = clampScore(draftScore)
    setSaving(true)
    try {
      const updated = await overrideEvaluation(evaluation.id, {
        new_score: newScore,
        reason: reason.trim(),
      })
      setDetail((d) => ({
        ...d,
        evaluation: { ...d.evaluation, score: updated.score, is_overridden: true },
      }))
      onOverridden?.(candidateId, { score: updated.score, is_overridden: true })
      setEditing(false)
      setReason('')
      toast('Đã cập nhật điểm — bảng xếp hạng được cập nhật.')
    } catch (e) {
      toast(e.message || 'Cập nhật điểm thất bại.')
    } finally {
      setSaving(false)
    }
  }

  const name = detail?.name || 'Ứng viên chưa rõ tên'
  const statusMeta = STATUS_BADGE[detail?.status] || STATUS_BADGE.PENDING
  const evaluation = detail?.evaluation
  const evidence = evaluation?.evidence || {}
  const strengths = evidence.strengths_evidence || {}
  const weaknesses = evidence.weaknesses_evidence || {}

  const inputCls =
    'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

  // 1 thẻ nhận định (điểm mạnh/yếu) có thể hover để soi bằng chứng trong CV.
  function EvidenceCard({ stmt, quote, tone }) {
    const styles =
      tone === 'strength'
        ? 'border-slate-200'
        : 'border-amber-200 bg-amber-50'
    const titleCls = tone === 'strength' ? 'text-slate-800' : 'text-amber-800'
    return (
      <div className={`rounded-lg border p-4 ${styles}`}>
        <p className={`text-sm font-semibold ${titleCls}`}>{stmt}</p>
        {quote ? (
          <p className="mt-2 border-l-2 border-indigo-300 pl-2 text-xs italic leading-relaxed text-slate-500">
            <Sparkles size={12} className="mr-1 inline text-indigo-500" />
            “{quote}”
          </p>
        ) : (
          <p className="mt-1 text-xs italic text-slate-400">
            Không tìm thấy bằng chứng nguyên văn.
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
        onClick={onClose}
      />

      <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-indigo-50 text-base font-semibold text-indigo-600">
              {name[0]}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-slate-900">{name}</h2>
                <Badge variant={statusMeta.variant} upper={false}>
                  {statusMeta.label}
                </Badge>
                {evaluation?.is_overridden && (
                  <Badge variant="new" upper={false}>
                    Đã chỉnh
                  </Badge>
                )}
              </div>
              <p className="text-xs text-slate-400">
                {detail?.email || 'Chưa có email'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {evaluation && !editing && (
              <button
                onClick={() => {
                  setDraftScore(String(evaluation.score))
                  setEditing(true)
                }}
                className="rounded-lg border border-slate-200 p-2 text-slate-500 transition hover:bg-slate-50"
                title="Chỉnh điểm (Override)"
              >
                <Pencil size={16} />
              </button>
            )}
            <button
              onClick={onClose}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              title="Đóng"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Body: score band + override editor stay fixed; on desktop each column
            scrolls independently (own scrollbar), on mobile the whole body scrolls. */}
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:overflow-hidden">
          {error && (
            <p className="px-6 py-8 text-sm text-red-500">Lỗi tải chi tiết: {error}</p>
          )}
          {!detail && !error && (
            <p className="px-6 py-8 text-sm text-slate-400">Đang tải chi tiết…</p>
          )}

          {detail && !evaluation && (
            <p className="px-6 py-8 text-sm text-slate-500">
              Ứng viên này chưa được chấm điểm (trạng thái: {statusMeta.label}).
            </p>
          )}

          {detail && evaluation && (
            <>
              {/* Score band + breakdown */}
              <div className="border-b border-slate-100 bg-slate-50/60 px-6 py-4">
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
                        value={draftScore}
                        onChange={(e) => setDraftScore(e.target.value)}
                        className="w-24 rounded-lg border border-indigo-300 px-2.5 py-1.5 text-2xl font-bold text-slate-900 outline-none focus:ring-2 focus:ring-indigo-100"
                      />
                      <span className="text-sm text-slate-400">/100</span>
                    </div>
                  ) : (
                    <p className="mt-1 text-3xl font-bold text-slate-900">
                      {evaluation.score}
                      <span className="text-base font-medium text-slate-400">
                        /100
                      </span>
                    </p>
                  )}
                </div>

                {/* Breakdown bars */}
                <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {Object.entries(evaluation.score_breakdown || {}).map(
                    ([key, val]) => (
                      <div key={key}>
                        <div className="flex items-center justify-between text-xs text-slate-500">
                          <span>{BREAKDOWN_LABEL[key] || key}</span>
                          <span className="font-semibold text-slate-700">{val}</span>
                        </div>
                        <div className="mt-1">
                          <ProgressBar value={Number(val) || 0} />
                        </div>
                      </div>
                    )
                  )}
                </div>
              </div>

              {/* Override editor */}
              {editing && (
                <div className="border-b border-slate-100 bg-indigo-50/50 px-6 py-4">
                  <p className="text-xs font-bold uppercase tracking-wide text-indigo-700">
                    Lý do chỉnh điểm (bắt buộc)
                  </p>
                  <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    rows={2}
                    placeholder="Vd: AI đánh giá thấp kinh nghiệm thực tế của ứng viên…"
                    className={`mt-2 resize-none ${inputCls}`}
                  />
                  <div className="mt-3 flex justify-end gap-2">
                    <SecondaryButton
                      className="px-3 py-2"
                      onClick={() => {
                        setEditing(false)
                        setReason('')
                        setDraftScore(String(evaluation.score))
                      }}
                      disabled={saving}
                    >
                      Hủy
                    </SecondaryButton>
                    <PrimaryButton className="px-3 py-2" onClick={saveOverride} disabled={saving}>
                      {saving ? (
                        <>
                          <Loader2 size={15} className="animate-spin" /> Đang lưu…
                        </>
                      ) : (
                        <>
                          <Save size={15} /> Lưu
                        </>
                      )}
                    </PrimaryButton>
                  </div>
                </div>
              )}

              {/* Two-column: đánh giá (trái) + CV gốc để đối chiếu (phải).
                  Mỗi cột tự cuộn trên desktop (grid-rows-1 -> row = minmax(0,1fr)
                  để cột bị giới hạn chiều cao và cuộn riêng, không kéo cột kia). */}
              <div className="grid grid-cols-1 lg:min-h-0 lg:flex-1 lg:grid-cols-2 lg:grid-rows-1">
                {/* Left — own scrollbar on desktop */}
                <div className="px-6 py-5 lg:min-h-0 lg:overflow-y-auto lg:border-r lg:border-slate-100">
                  {evaluation.explanation && (
                    <div className="mb-5">
                      <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
                        <Target size={14} /> Giải thích
                      </h3>
                      <p className="mt-2 text-sm leading-relaxed text-slate-600">
                        {evaluation.explanation}
                      </p>
                    </div>
                  )}

                  {Object.keys(strengths).length > 0 && (
                    <>
                      <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-emerald-600">
                        <CheckCircle2 size={14} /> Điểm mạnh &amp; bằng chứng
                      </h3>
                      <div className="mt-3 space-y-3">
                        {Object.entries(strengths).map(([stmt, quote]) => (
                          <EvidenceCard key={stmt} stmt={stmt} quote={quote} tone="strength" />
                        ))}
                      </div>
                    </>
                  )}

                  {Object.keys(weaknesses).length > 0 && (
                    <>
                      <h3 className="mt-6 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-amber-600">
                        <AlertTriangle size={14} /> Điểm còn thiếu
                      </h3>
                      <div className="mt-3 space-y-3">
                        {Object.entries(weaknesses).map(([stmt, quote]) => (
                          <EvidenceCard key={stmt} stmt={stmt} quote={quote} tone="weakness" />
                        ))}
                      </div>
                    </>
                  )}

                  {evidence.evidence_error && (
                    <p className="mt-4 text-xs text-slate-400">
                      Không sinh được bằng chứng cho ứng viên này (
                      {evidence.evidence_error}).
                    </p>
                  )}

                  {detail.skills?.length > 0 && (
                    <div className="mt-6">
                      <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
                        Kỹ năng trích xuất
                      </h3>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {detail.skills.map((s) => (
                          <Tag key={s.id} className="bg-indigo-50 text-indigo-700">
                            {s.skill_name}
                          </Tag>
                        ))}
                      </div>
                    </div>
                  )}

                  {detail.projects?.length > 0 && (
                    <div className="mt-6">
                      <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
                        <FolderGit2 size={14} /> Dự án
                      </h3>
                      <div className="mt-3 space-y-3">
                        {detail.projects.map((p) => (
                          <div key={p.id} className="rounded-lg border border-slate-200 p-4">
                            <div className="flex items-center justify-between gap-2">
                              <p className="text-sm font-semibold text-slate-800">
                                {p.name}
                              </p>
                              {p.github_url && (
                                <a
                                  href={p.github_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700"
                                >
                                  <Github size={13} /> GitHub
                                </a>
                              )}
                            </div>
                            {p.description && (
                              <p className="mt-1 text-xs leading-relaxed text-slate-500">
                                {p.description}
                              </p>
                            )}
                            {p.tech_stack?.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {p.tech_stack.map((t, i) => (
                                  <Tag key={i}>{t}</Tag>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Right: file PDF gốc — own scrollbar on desktop */}
                <div className="px-6 py-5 lg:min-h-0 lg:overflow-y-auto">
                  <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
                    <FileText size={14} /> CV gốc (PDF)
                  </h3>
                  <CvPdf candidateId={candidateId} />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
