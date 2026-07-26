import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, Navigate, useSearchParams } from 'react-router-dom'
import {
  Bot,
  CheckCircle2,
  ArrowLeft,
  Users,
  UploadCloud,
  Plus,
  X,
  RefreshCw,
  AlertTriangle,
  XCircle,
  FileText,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  StatCard,
  Badge,
  ProgressBar,
  PrimaryButton,
  SecondaryButton,
} from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { useProjects } from '../context/ProjectContext.jsx'
import { getCandidates, getJd, uploadCvs } from '../api/jds.js'
import { listShortlists } from '../api/shortlists.js'
import CandidateDetailModal from '../components/CandidateDetailModal.jsx'
import { formatName } from '../utils/formatName.js'

// Chỉ còn một cách nạp hồ sơ (tải file .zip). Giữ map để các project cũ trong
// state vẫn render được icon, nhưng mọi method lạ đều rơi về UploadCloud.
const METHOD_ICON = { upload: UploadCloud }

// Trạng thái xử lý CV thật (khớp models.Candidate.status ở backend).
const STATUS_META = {
  PENDING: { icon: RefreshCw, cls: 'text-indigo-500', variant: 'processing', label: 'Đang xử lý' },
  COMPLETED: { icon: CheckCircle2, cls: 'text-emerald-500', variant: 'completed', label: 'Hoàn tất' },
  FAILED: { icon: XCircle, cls: 'text-red-500', variant: 'error', label: 'Lỗi' },
}

const UPLOAD_LABEL = 'Tải lên trực tiếp'

// Minimal markdown renderer for the generated JD (headings, bullets, tables).
// Render inline Markdown **bold** thành <strong>, giữ nguyên phần còn lại.
function renderInline(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, k) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={k} className="font-semibold text-slate-900">
          {part.slice(2, -2)}
        </strong>
      )
    }
    return part
  })
}

function GeneratedJD({ markdown }) {
  const lines = markdown.split('\n')
  const blocks = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('# ')) {
      blocks.push(
        <h1 key={i} className="text-xl font-bold text-slate-900">
          {line.slice(2)}
        </h1>
      )
      i++
    } else if (line.startsWith('## ')) {
      blocks.push(
        <h2
          key={i}
          className="mt-5 text-sm font-bold uppercase tracking-wide text-slate-500"
        >
          {line.slice(3)}
        </h2>
      )
      i++
    } else if (line.startsWith('- ')) {
      const items = []
      while (i < lines.length && lines[i].startsWith('- ')) {
        items.push(lines[i].slice(2))
        i++
      }
      blocks.push(
        <ul key={i} className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
          {items.map((it, k) => (
            <li key={k}>{renderInline(it)}</li>
          ))}
        </ul>
      )
    } else if (line.startsWith('|')) {
      const rows = []
      while (i < lines.length && lines[i].startsWith('|')) {
        rows.push(lines[i])
        i++
      }
      const parseRow = (r) =>
        r
          .split('|')
          .slice(1, -1)
          .map((c) => c.trim())
      const header = parseRow(rows[0])
      const body = rows.slice(2).map(parseRow) // skip the |---| divider
      blocks.push(
        <table key={i} className="mt-3 w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase text-slate-400">
              {header.map((h, k) => (
                <th key={k} className="py-2 pr-4">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, r) => (
              <tr key={r} className="border-b border-slate-100">
                {row.map((c, k) => (
                  <td key={k} className="py-2 pr-4 text-slate-700">
                    {renderInline(c)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )
    } else if (line.trim() === '') {
      i++
    } else {
      blocks.push(
        <p key={i} className="mt-2 text-sm leading-relaxed text-slate-600">
          {renderInline(line)}
        </p>
      )
      i++
    }
  }
  return <div>{blocks}</div>
}

// Poll GET /jds/{id}/candidates để hiển thị tiến độ chấm điểm CV thật (do Celery
// worker xử lý nền). Tự dừng poll khi không còn CV nào ở trạng thái PENDING.
function LiveProcessing({ jdId, refreshKey, onOpenCandidate, highlightIds }) {
  const [rows, setRows] = useState(null) // null = đang tải lần đầu
  const [error, setError] = useState('')

  useEffect(() => {
    let stopped = false
    let timer

    async function poll() {
      try {
        const data = await getCandidates(jdId)
        if (stopped) return
        setRows(data)
        setError('')
        if (data.some((c) => c.status === 'PENDING')) {
          timer = setTimeout(poll, 3000) // còn CV đang xử lý -> poll tiếp
        }
      } catch (e) {
        if (stopped) return
        setError(e.message)
        timer = setTimeout(poll, 5000)
      }
    }

    poll()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [jdId, refreshKey])

  if (rows === null && !error) {
    return <p className="mt-4 text-sm text-slate-400">Đang tải trạng thái xử lý…</p>
  }

  const list = rows || []
  const total = list.length
  const completed = list.filter((c) => c.status === 'COMPLETED').length
  const pending = list.filter((c) => c.status === 'PENDING').length
  const failed = list.filter((c) => c.status === 'FAILED').length
  const pct = total ? Math.round((completed / total) * 100) : 0

  return (
    <div className="mt-4">
      {error && (
        <p className="mb-3 text-xs text-red-500">Lỗi tải trạng thái: {error}</p>
      )}

      {total === 0 ? (
        <p className="text-sm text-slate-400">
          Chưa có CV nào cho vị trí này. Tải file ZIP ở bước tạo dự án để bắt đầu.
        </p>
      ) : (
        <>
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>
              {completed}/{total} xong
              {pending > 0 && ` • ${pending} đang xử lý`}
              {failed > 0 && ` • ${failed} lỗi`}
            </span>
            <span className="font-semibold text-slate-700">{pct}%</span>
          </div>
          <div className="mt-2">
            <ProgressBar value={pct} />
          </div>

          <div className="mt-4 space-y-2">
            {list.map((c) => {
              const meta = STATUS_META[c.status] || STATUS_META.PENDING
              const Icon = meta.icon
              // Ứng viên đã chấm xong -> click để mở popup chi tiết đánh giá ngay
              // tại trang này (không cần sang trang Shortlisting).
              const clickable = c.status === 'COMPLETED'
              // LC2: AI Copilot search -> tô sáng đúng những ứng viên khớp.
              const highlighted = highlightIds?.has(c.id)
              return (
                <div
                  key={c.id}
                  onClick={clickable ? () => onOpenCandidate?.(c.id) : undefined}
                  role={clickable ? 'button' : undefined}
                  tabIndex={clickable ? 0 : undefined}
                  onKeyDown={
                    clickable
                      ? (e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            onOpenCandidate?.(c.id)
                          }
                        }
                      : undefined
                  }
                  title={clickable ? 'Xem chi tiết đánh giá' : undefined}
                  className={`flex items-center justify-between rounded-lg border px-3 py-2 ${
                    highlighted
                      ? 'border-indigo-400 bg-indigo-50 ring-2 ring-indigo-300'
                      : 'border-slate-200'
                  } ${
                    clickable
                      ? 'cursor-pointer transition hover:border-indigo-300 hover:bg-indigo-50/40'
                      : ''
                  }`}
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <Icon
                      size={14}
                      className={`${meta.cls} ${c.status === 'PENDING' ? 'animate-spin' : ''}`}
                    />
                    <span className="truncate text-sm text-slate-700">
                      {formatName(c.name) || 'Đang trích xuất…'}
                    </span>
                  </div>
                  <div className="flex flex-shrink-0 items-center gap-2">
                    {highlighted && (
                      <Badge variant="ai" upper={false}>
                        AI đề xuất
                      </Badge>
                    )}
                    <Badge variant={meta.variant} upper={false}>
                      {meta.label}
                    </Badge>
                    {c.score != null && (
                      <span className="text-sm font-semibold text-slate-800">
                        {c.score}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

export default function ProjectDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { getProject, loading, setProjectDetail } = useProjects()
  const [showAddSource, setShowAddSource] = useState(false)
  // Tăng để buộc LiveProcessing poll lại sau khi upload thêm nguồn CV mới.
  const [liveKey, setLiveKey] = useState(0)
  // Số liệu THẬT cho stat cards (null = đang tải).
  const [candidateCount, setCandidateCount] = useState(null)
  const [shortlistedCount, setShortlistedCount] = useState(null)
  // Ứng viên đang mở popup chi tiết đánh giá (ngay trên trang này).
  const [openCandidateId, setOpenCandidateId] = useState(null)
  const project = getProject(id)

  // AI Copilot điều khiển trang này qua query param:
  //   ?open=<candidateId>       -> LC1: bật popup chi tiết ứng viên
  //   ?highlight=<id1,id2,...>  -> LC2: tô sáng các ứng viên khớp search
  const [searchParams] = useSearchParams()
  const openParam = searchParams.get('open')
  const highlightParam = searchParams.get('highlight')
  const highlightIds = useMemo(
    () => new Set((highlightParam || '').split(',').filter(Boolean)),
    [highlightParam]
  )
  useEffect(() => {
    if (openParam) setOpenCandidateId(openParam)
  }, [openParam])

  // Project được hydrate từ listJds() không kèm jd_markdown -> fetch đầy đủ 1 lần.
  useEffect(() => {
    if (project && !project.jdMarkdown) {
      getJd(id)
        .then((jd) =>
          setProjectDetail(id, { jdMarkdown: jd.jd_markdown, jdInput: jd.raw_text })
        )
        .catch(() => {})
    }
  }, [id, project, setProjectDetail])

  // Đếm số ứng viên thật + số đã đưa vào shortlist (không dùng mock). Chạy lại khi
  // upload thêm CV (liveKey đổi) để số cập nhật.
  useEffect(() => {
    if (!id) return
    let cancelled = false
    getCandidates(id)
      .then((data) => !cancelled && setCandidateCount(data.length))
      .catch(() => {})
    listShortlists(id)
      .then((sls) =>
        !cancelled &&
        setShortlistedCount(sls.reduce((n, s) => n + (s.item_count || 0), 0))
      )
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [id, liveKey])

  // Chưa tìm thấy project: nếu đang nạp từ backend (vd reload deep-link) thì chờ,
  // đừng redirect vội về dashboard.
  if (!project) {
    if (loading) {
      return (
        <>
          <Topbar />
          <main className="flex-1 px-8 py-7">
            <p className="text-sm text-slate-400">Đang tải dự án…</p>
          </main>
        </>
      )
    }
    return <Navigate to="/" replace />
  }

  const totalIngested = project.sources.reduce((n, s) => n + (s.count || 0), 0)

  const stats = [
    {
      key: 'candidates',
      icon: Users,
      cls: 'bg-indigo-50 text-indigo-600',
      label: 'Ứng viên',
      value: candidateCount == null ? '…' : String(candidateCount),
      footnote: 'Ranked for this role',
    },
    {
      key: 'shortlisted',
      icon: CheckCircle2,
      cls: 'bg-emerald-50 text-emerald-600',
      label: 'Đã rút gọn',
      value: shortlistedCount == null ? '…' : String(shortlistedCount),
      footnote: 'Proceeded to next step',
    },
    {
      key: 'sources',
      icon: UploadCloud,
      cls: 'bg-violet-50 text-violet-600',
      label: 'Lượt tải lên',
      value: String(project.sources.length),
      footnote: `Đã nạp ${totalIngested} CV`,
    },
  ]

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/')}
              className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100"
              title="Quay lại bảng điều khiển"
            >
              <ArrowLeft size={18} />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-slate-900">
                {project.title}
              </h1>
              <p className="mt-1 text-sm text-slate-500">
                Tổng quan dự án & bản mô tả công việc do AI tạo.
              </p>
            </div>
          </div>
          <PrimaryButton
            onClick={() =>
              navigate('/shortlisting', { state: { projectId: project.id } })
            }
          >
            <Users size={16} /> Xem danh sách rút gọn
          </PrimaryButton>
        </div>

        {/* Stat cards */}
        <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-3">
          {stats.map((s) => (
            <StatCard
              key={s.key}
              icon={s.icon}
              iconClass={s.cls}
              label={s.label}
              value={s.value}
              footnote={s.footnote}
            />
          ))}
        </div>

        {/* Two-column grid */}
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* ---- Left: generated Job Description ---- */}
          <div className="space-y-6">
            <Card className="p-6">
              <div className="flex items-center gap-2">
                <Bot size={20} className="text-indigo-600" />
                <h2 className="text-base font-semibold text-slate-900">
                  Mô tả công việc bằng ngôn ngữ tự nhiên
                </h2>
                <Badge variant="ai">AI Generated</Badge>
              </div>
              <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50/50 p-5">
                {project.jdMarkdown ? (
                  <GeneratedJD markdown={project.jdMarkdown} />
                ) : (
                  <p className="text-sm text-slate-400">Đang tải mô tả công việc…</p>
                )}
              </div>
            </Card>
          </div>

          {/* ---- Right: sources + ingestion + alerts ---- */}
          <div className="space-y-6">
            {/* Ingested sources */}
            <Card className="p-6">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-slate-900">
                  Hồ sơ đã tải lên
                </h2>
                <SecondaryButton
                  className="px-3 py-2"
                  onClick={() => setShowAddSource(true)}
                >
                  <Plus size={15} /> Tải thêm CV
                </SecondaryButton>
              </div>
              <p className="mt-1 text-sm text-slate-500">
                Mọi lượt tải đã đưa ứng viên vào dự án này.
              </p>
              <div className="mt-4 space-y-3">
                {project.sources.map((s) => {
                  const Icon = METHOD_ICON[s.method] || UploadCloud
                  return (
                    <div
                      key={s.id}
                      className="flex items-start gap-3 rounded-xl border border-slate-200 p-4"
                    >
                      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                        <Icon size={16} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-slate-800">
                          {s.label}
                        </p>
                        <p className="truncate text-xs text-slate-400">
                          {s.value || 'Không có thông tin file'}
                        </p>
                      </div>
                      <Badge variant="neutral">
                        <FileText size={11} /> {s.count || 0} CVs
                      </Badge>
                    </div>
                  )
                })}
              </div>
            </Card>

            {/* Ingestion Queue */}
            <Card className="p-6">
              <h2 className="text-base font-semibold text-slate-900">
                CV Processing (live)
              </h2>
              <LiveProcessing
                jdId={project.id}
                refreshKey={liveKey}
                onOpenCandidate={setOpenCandidateId}
                highlightIds={highlightIds}
              />
            </Card>
          </div>
        </div>
      </main>

      {showAddSource && (
        <AddSourceModal
          projectId={project.id}
          onClose={() => setShowAddSource(false)}
          onUploaded={() => setLiveKey((k) => k + 1)}
        />
      )}

      {/* Popup chi tiết đánh giá ứng viên — mở ngay tại trang dự án. */}
      {openCandidateId && (
        <CandidateDetailModal
          candidateId={openCandidateId}
          onClose={() => setOpenCandidateId(null)}
          onOverridden={() => setLiveKey((k) => k + 1)}
        />
      )}
    </>
  )
}

// Modal nạp thêm CV cho một dự án đã có (chỉ còn đường tải file .zip).
function AddSourceModal({ projectId, onClose, onUploaded }) {
  const toast = useToast()
  const { addSource } = useProjects()
  const [value, setValue] = useState('')
  const [file, setFile] = useState(null) // File ZIP thật để upload lên backend
  const [submitting, setSubmitting] = useState(false)
  const fileInputRef = useRef(null)

  // Chọn file ZIP (input hoặc kéo-thả): giữ File thật + hiện tên, chặn định dạng sai.
  function pickFile(f) {
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.zip')) {
      toast('Chỉ chấp nhận file .zip chứa nhiều CV PDF.')
      return
    }
    setFile(f)
    setValue(f.name)
  }

  // GỬI FILE ZIP THẬT lên backend -> mỗi CV được Celery chấm điểm nền.
  async function handleAdd() {
    if (!file) {
      toast('Chọn file .zip chứa CV trước.')
      return
    }
    setSubmitting(true)
    try {
      const summary = await uploadCvs(projectId, file)
      addSource(projectId, {
        method: 'upload',
        label: UPLOAD_LABEL,
        value: file.name,
        count: summary.processing ?? 0,
      })
      toast(`Đã nhận ${summary.processing ?? 0} CV — đang xử lý nền.`)
      onUploaded?.() // buộc LiveProcessing poll lại để thấy CV mới
      onClose()
    } catch (err) {
      toast(err.message || 'Upload thất bại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-base font-bold text-slate-900">Tải thêm CV</h2>
          <button
            onClick={onClose}
            aria-label="Đóng"
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-5">
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              if (e.dataTransfer.files?.length) pickFile(e.dataTransfer.files[0])
            }}
            className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50/50 px-6 py-8 text-center"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600">
              <UploadCloud size={22} />
            </div>
            <p className="mt-3 text-sm font-semibold text-slate-700">
              {value || 'Kéo thả tệp .zip chứa CV vào đây'}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              File .zip chứa nhiều CV PDF
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.length) pickFile(e.target.files[0])
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
            >
              Chọn tệp
            </button>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4">
          <SecondaryButton onClick={onClose} disabled={submitting}>
            Huỷ
          </SecondaryButton>
          <PrimaryButton onClick={handleAdd} disabled={submitting}>
            {submitting ? (
              <>
                <RefreshCw size={16} className="animate-spin" /> Đang tải lên…
              </>
            ) : (
              <>
                <Plus size={16} /> Tải lên
              </>
            )}
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}
