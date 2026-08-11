import { useEffect, useState } from 'react'
import {
  X,
  ArrowLeft,
  Pencil,
  Save,
  Github,
  FolderGit2,
  FileText,
  Loader2,
  MessageSquareText,
  RotateCcw,
  User,
} from 'lucide-react'
import { Tag, Badge, PrimaryButton, SecondaryButton } from './ui.jsx'
import { useAgentReload } from '../utils/useAgentReload.js'
import EvaluationPanel from './EvaluationPanel.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { formatName } from '../utils/formatName.js'
import { humanizeExtractionError } from '../utils/errorMessage.js'
import {
  getCandidate,
  overrideEvaluation,
  getCandidateCv,
  retryCandidate,
} from '../api/jds.js'

const STATUS_BADGE = {
  COMPLETED: { variant: 'completed', label: 'Hoàn tất' },
  PENDING: { variant: 'processing', label: 'Đang xử lý' },
  FAILED: { variant: 'error', label: 'Lỗi' },
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
      <div className="flex h-full min-h-[60vh] flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50/50 p-6 text-center">
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
      <div className="flex h-full min-h-[60vh] items-center justify-center rounded-lg border border-slate-200 bg-slate-50/50">
        <Loader2 size={20} className="animate-spin text-slate-400" />
      </div>
    )
  }
  return (
    <iframe
      src={url}
      title="CV gốc"
      className="h-full min-h-[60vh] w-full rounded-lg border border-slate-200"
    />
  )
}

// Modal chi tiết ứng viên — dữ liệu THẬT từ backend. Cột phải nhúng file PDF gốc;
// bằng chứng điểm mạnh/yếu hiển thị nguyên văn (trích dẫn) ở cột trái.
// - onInterview: chỉ truyền khi ứng viên ĐÃ nằm trong shortlist. Không có prop này
//   thì nút "Phỏng vấn" không hiện — phỏng vấn chỉ mở được từ tab Shortlist.
export default function CandidateDetailModal({
  candidateId,
  onClose,
  onOverridden,
  onRetried,
  onInterview,
}) {
  const toast = useToast()
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [draftScore, setDraftScore] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [retrying, setRetrying] = useState(false)

  // `reloadKey`: điểm và nhận xét trong popup này đổi khi agent chấm lại / sửa điểm.
  // (Effect tải file CV ở trên KHÔNG cần nghe nonce: nội dung CV không đổi theo thao
  // tác của agent, mà tải lại blob PDF mỗi lượt chat thì rất tốn.)
  const reloadKey = useAgentReload()

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
  }, [candidateId, reloadKey])

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

  async function handleRetry() {
    setRetrying(true)
    try {
      await retryCandidate(candidateId)
      // Đổi ngay tại chỗ sang PENDING để HR thấy phản hồi, không phải đóng/mở lại.
      setDetail((d) => (d ? { ...d, status: 'PENDING', error_message: null } : d))
      onRetried?.(candidateId)
      toast('Đã đưa CV vào hàng đợi chấm lại.')
    } catch (e) {
      toast(e.message || 'Không thử lại được.')
    } finally {
      setRetrying(false)
    }
  }

  const realName = formatName(detail?.name)
  const hasName = Boolean(realName)
  const name = realName || 'Ứng viên chưa rõ tên'
  const statusMeta = STATUS_BADGE[detail?.status] || STATUS_BADGE.PENDING
  const isFailed = detail?.status === 'FAILED'
  const failureInfo = humanizeExtractionError(detail?.error_message)
  const evaluation = detail?.evaluation

  const inputCls =
    'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

  return (
    <div className="fixed inset-y-0 right-0 left-60 z-50 flex flex-col bg-white">
      <div className="relative flex h-full w-full flex-col overflow-hidden bg-white">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
              title="Quay lại danh sách"
            >
              <ArrowLeft size={16} /> Quay lại
            </button>
            {/* Chưa trích được tên -> hiện icon người, KHÔNG lấy chữ cái đầu của
                chuỗi thay thế (trước đây ra avatar chữ "Ứ" của "Ứng viên chưa rõ
                tên", trông như tên thật). */}
            <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full bg-indigo-50 text-base font-semibold text-indigo-600">
              {hasName ? name[0].toUpperCase() : <User size={20} />}
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
            {evaluation && onInterview && (
              <SecondaryButton
                className="px-3 py-2"
                onClick={() => onInterview(detail)}
                title="Phỏng vấn ứng viên (AI)"
              >
                <MessageSquareText size={16} /> Phỏng vấn
              </SecondaryButton>
            )}
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

          {/* CV chưa chấm được (FAILED/PENDING): vẫn phải cho HR ĐỌC CV gốc để tự
              đánh giá — trước đây chỗ này chỉ hiện một dòng chữ, coi như CV biến
              mất khỏi hệ thống chỉ vì AI chấm hỏng. */}
          {detail && !evaluation && (
            <div className="flex min-h-0 flex-1 flex-col px-6 py-5">
              <div
                className={`mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 ${
                  isFailed
                    ? 'border-red-200 bg-red-50/60'
                    : 'border-slate-200 bg-slate-50/60'
                }`}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-800">
                    {isFailed ? failureInfo.title : 'CV đang được chấm điểm'}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500">
                    {isFailed
                      ? failureInfo.hint
                      : 'Hệ thống đang xử lý nền, bạn có thể đọc CV gốc bên dưới trong lúc chờ. Nếu chờ quá lâu không xong, bấm "Chạy lại" để đẩy vào hàng đợi lần nữa.'}
                  </p>
                  {/* Nguyên văn lỗi kỹ thuật: gập lại mặc định. HR không cần đọc,
                      nhưng khi báo lỗi cho dev thì phải copy được đầy đủ. */}
                  {isFailed && failureInfo.raw && (
                    <details className="mt-2 group">
                      <summary className="cursor-pointer text-xs font-medium text-slate-400 transition hover:text-slate-600">
                        Chi tiết kỹ thuật
                      </summary>
                      <pre className="mt-1.5 max-h-32 overflow-auto whitespace-pre-wrap break-all rounded-md border border-slate-200 bg-white/70 px-2.5 py-2 font-mono text-[11px] leading-relaxed text-slate-500">
                        {failureInfo.raw}
                      </pre>
                    </details>
                  )}
                </div>
                {/* PENDING cũng cho chạy lại: worker restart giữa chừng làm mất
                    task trong khi CV vẫn ở PENDING, không có nút này thì CV kẹt
                    vĩnh viễn.
                    Lỗi nào thử lại chắc chắn vô ích (hết hạn mức AI, CV là ảnh
                    scan) thì hạ nút xuống kiểu phụ — vẫn bấm được, nhưng không mời
                    gọi HR bấm để rồi lại thất bại. */}
                {isFailed && !failureInfo.retryUseful ? (
                  <SecondaryButton
                    className="flex-shrink-0 px-3 py-2"
                    onClick={handleRetry}
                    disabled={retrying}
                  >
                    {retrying ? (
                      <>
                        <Loader2 size={15} className="animate-spin" /> Đang gửi…
                      </>
                    ) : (
                      <>
                        <RotateCcw size={15} /> Vẫn thử lại
                      </>
                    )}
                  </SecondaryButton>
                ) : (
                  <PrimaryButton
                    className="flex-shrink-0 px-3 py-2"
                    onClick={handleRetry}
                    disabled={retrying}
                  >
                    {retrying ? (
                      <>
                        <Loader2 size={15} className="animate-spin" /> Đang gửi…
                      </>
                    ) : (
                      <>
                        <RotateCcw size={15} /> {isFailed ? 'Thử lại' : 'Chạy lại'}
                      </>
                    )}
                  </PrimaryButton>
                )}
              </div>

              <h3 className="mb-3 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
                <FileText size={14} /> CV gốc
              </h3>
              <div className="min-h-0 flex-1">
                <CvPdf candidateId={candidateId} />
              </div>
            </div>
          )}

          {detail && evaluation && (
            <>
              {/* Two-column: đánh giá + điểm (trái) + CV gốc đối chiếu (phải).
                  Mỗi cột tự cuộn trên desktop (grid-rows-1 -> row = minmax(0,1fr)
                  để cột bị giới hạn chiều cao và cuộn riêng, không kéo cột kia). */}
              <div className="grid grid-cols-1 lg:min-h-0 lg:flex-1 lg:grid-cols-2 lg:grid-rows-1">
                {/* Left — điểm + breakdown + editor + đánh giá; own scrollbar on desktop */}
                <div className="px-6 py-5 lg:min-h-0 lg:overflow-y-auto lg:border-r lg:border-slate-100">
                  {/* Toàn bộ phần đánh giá AI. Con số điểm do modal render (vì HR sửa
                      được tại chỗ), phần còn lại nằm trong EvaluationPanel. */}
                  <EvaluationPanel
                    evaluation={evaluation}
                    scoreNode={
                      editing ? (
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
                      )
                    }
                    /* Ô nhập lý do chỉnh điểm phải nằm NGAY dưới con số vừa sửa —
                       đặt ở cuối cột thì HR bấm bút chì xong không thấy nó đâu. */
                    belowScore={
                      editing && (
                        <div className="mt-4 rounded-xl border border-indigo-100 bg-indigo-50/50 p-4">
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
                            <PrimaryButton
                              className="px-3 py-2"
                              onClick={saveOverride}
                              disabled={saving}
                            >
                              {saving ? (
                                <>
                                  <Loader2 size={15} className="animate-spin" /> Đang
                                  lưu…
                                </>
                              ) : (
                                <>
                                  <Save size={15} /> Lưu
                                </>
                              )}
                            </PrimaryButton>
                          </div>
                        </div>
                      )
                    }
                  />

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

                {/* Right: CV gốc — nhúng file PDF gốc từ backend */}
                <div className="flex flex-col px-6 py-5 lg:min-h-0 lg:overflow-hidden">
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
                      <FileText size={14} /> CV gốc
                    </h3>
                  </div>
                  <div className="min-h-0 flex-1">
                    <CvPdf candidateId={candidateId} />
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

    </div>
  )
}
