import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Search,
  ArrowUpDown,
  ExternalLink,
  Lightbulb,
  Trophy,
  GitCompare,
  FolderPlus,
  Plus,
  Briefcase,
  ArrowRight,
  ArrowLeft,
  RefreshCw,
  X,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  Badge,
  Tag,
  ScoreRing,
  SecondaryButton,
  PrimaryButton,
} from '../components/ui.jsx'
import CandidateDetailModal from '../components/CandidateDetailModal.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { useProjects } from '../context/ProjectContext.jsx'
import { getCandidates } from '../api/jds.js'

const STATUS_BADGE = {
  COMPLETED: { variant: 'completed', label: 'Hoàn tất' },
  PENDING: { variant: 'processing', label: 'Đang xử lý' },
  FAILED: { variant: 'error', label: 'Lỗi' },
}

// COMPLETED (có điểm) xếp trước theo điểm giảm dần; PENDING/FAILED (không điểm) xếp cuối.
function sortRows(rows) {
  return [...rows].sort(
    (a, b) => (a.score == null) - (b.score == null) || (b.score ?? 0) - (a.score ?? 0)
  )
}

export default function Shortlisting() {
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()
  const { projects } = useProjects()

  const initialId =
    location.state?.projectId &&
    projects.some((p) => p.id === location.state.projectId)
      ? location.state.projectId
      : projects.length === 1
        ? projects[0].id
        : null
  const [projectId, setProjectId] = useState(initialId)

  const [query, setQuery] = useState('')
  const [openId, setOpenId] = useState(null)
  const [compareMode, setCompareMode] = useState(false)
  const [selected, setSelected] = useState([])
  const [showCompare, setShowCompare] = useState(false)

  // Ứng viên THẬT của JD đang chọn (GET /jds/{id}/candidates).
  const [rows, setRows] = useState(null) // null = chưa tải
  const [loadErr, setLoadErr] = useState('')

  useEffect(() => {
    if (!projectId) {
      setRows(null)
      return
    }
    let cancelled = false
    setRows(null)
    setLoadErr('')
    getCandidates(projectId)
      .then((data) => !cancelled && setRows(sortRows(data)))
      .catch((e) => !cancelled && setLoadErr(e.message))
    return () => {
      cancelled = true
    }
  }, [projectId])

  // ---- No projects ----
  if (projects.length === 0) {
    return (
      <>
        <Topbar />
        <main className="flex-1 overflow-y-auto px-8 py-7">
          <h1 className="text-2xl font-bold text-slate-900">
            Candidate Shortlisting
          </h1>
          <div className="mt-10 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white/60 px-6 py-20 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
              <FolderPlus size={30} />
            </div>
            <h2 className="mt-5 text-lg font-semibold text-slate-900">
              No projects yet
            </h2>
            <p className="mt-1.5 max-w-md text-sm text-slate-500">
              Create a project (job description) first — then candidates can be
              ranked and shortlisted against it.
            </p>
            <PrimaryButton className="mt-6" onClick={() => navigate('/projects/new')}>
              <Plus size={16} /> Create a project
            </PrimaryButton>
          </div>
        </main>
      </>
    )
  }

  const project = projectId ? projects.find((p) => p.id === projectId) : null

  // ---- Project picker ----
  if (!project) {
    return (
      <>
        <Topbar />
        <main className="flex-1 overflow-y-auto px-8 py-7">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              Candidate Shortlisting
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Select a project to shortlist candidates against.
            </p>
          </div>
          <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <button
                key={p.id}
                onClick={() => setProjectId(p.id)}
                className="group flex flex-col text-left"
              >
                <Card className="flex h-full flex-col p-5 transition hover:border-indigo-300 hover:shadow-md">
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                      <Briefcase size={18} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate text-base font-semibold text-slate-900">
                        {p.title}
                      </h3>
                    </div>
                  </div>
                  <p className="mt-3 line-clamp-2 flex-1 text-sm leading-relaxed text-slate-500">
                    {p.jdInput || 'No description provided.'}
                  </p>
                  <div className="mt-4 flex items-center justify-end border-t border-slate-100 pt-3 text-xs">
                    <span className="inline-flex items-center gap-1 font-medium text-indigo-600 group-hover:gap-1.5">
                      Shortlist <ArrowRight size={14} />
                    </span>
                  </div>
                </Card>
              </button>
            ))}
          </div>
        </main>
      </>
    )
  }

  const list = rows || []
  const visible = list.filter((c) =>
    query.trim()
      ? (`${c.name || ''} ${(c.skills || []).join(' ')}`)
          .toLowerCase()
          .includes(query.trim().toLowerCase())
      : true
  )
  const compareList = list.filter((c) => selected.includes(c.id))
  const completedCount = list.filter((c) => c.status === 'COMPLETED').length

  function toggleSelect(id) {
    setSelected((l) => (l.includes(id) ? l.filter((x) => x !== id) : [...l, id]))
  }

  // Sau khi override: cập nhật điểm + cờ trong row rồi xếp lại hạng.
  function handleOverridden(candidateId, { score, is_overridden }) {
    setRows((prev) =>
      sortRows(
        (prev || []).map((c) =>
          c.id === candidateId ? { ...c, score, is_overridden } : c
        )
      )
    )
  }

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            {projects.length > 1 && (
              <button
                onClick={() => {
                  setProjectId(null)
                  setSelected([])
                  setCompareMode(false)
                }}
                className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100"
                title="Change project"
              >
                <ArrowLeft size={18} />
              </button>
            )}
            <div>
              <h1 className="text-2xl font-bold text-slate-900">
                Candidate Shortlisting
              </h1>
              <p className="mt-1 text-sm text-slate-500">
                AI-ranked leaderboard for{' '}
                <span className="font-semibold text-slate-700">
                  {project.title}
                </span>
                .
              </p>
            </div>
          </div>
        </div>

        {/* Search + controls */}
        <Card className="mt-6 flex items-center gap-3 p-3">
          <div className="flex flex-1 items-center gap-2">
            <Search size={18} className="ml-2 flex-shrink-0 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Tìm theo tên hoặc kỹ năng…"
              className="w-full flex-1 bg-transparent text-sm text-slate-700 placeholder-slate-400 outline-none"
            />
          </div>
          <div className="h-7 w-px bg-slate-200" />
          <SecondaryButton onClick={() => toast('Đang sắp theo điểm AI giảm dần.')}>
            <ArrowUpDown size={15} /> Sort: AI Rank
          </SecondaryButton>
          <SecondaryButton
            className={
              compareMode ? 'border-indigo-300 bg-indigo-50 text-indigo-600' : ''
            }
            onClick={() => {
              setCompareMode((v) => !v)
              setSelected([])
            }}
          >
            <GitCompare size={15} /> Compare
          </SecondaryButton>
        </Card>

        {/* Compare action bar */}
        {compareMode && (
          <div className="mt-4 flex items-center justify-between rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3">
            <p className="text-sm text-indigo-700">
              Chọn ứng viên để so sánh ({selected.length} đã chọn).
            </p>
            <PrimaryButton
              className="px-3 py-2"
              disabled={selected.length < 2}
              onClick={() => setShowCompare(true)}
            >
              <GitCompare size={15} /> Compare {selected.length || ''}
            </PrimaryButton>
          </div>
        )}

        {/* Leaderboard */}
        <Card className="mt-5 overflow-hidden">
          <div className="flex items-center gap-2 border-b border-slate-200 px-6 py-3">
            <Trophy size={16} className="text-amber-500" />
            <h2 className="text-sm font-semibold text-slate-800">Leaderboard</h2>
          </div>

          {/* Trạng thái tải */}
          {rows === null && !loadErr && (
            <p className="px-6 py-10 text-sm text-slate-400">Đang tải ứng viên…</p>
          )}
          {loadErr && (
            <p className="px-6 py-10 text-sm text-red-500">
              Lỗi tải ứng viên: {loadErr}
            </p>
          )}
          {rows && list.length === 0 && (
            <p className="px-6 py-10 text-sm text-slate-400">
              Chưa có ứng viên nào cho vị trí này. Tải CV ở trang chi tiết dự án để
              bắt đầu.
            </p>
          )}

          {rows && list.length > 0 && (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-left">
                  <thead>
                    <tr className="border-b border-slate-200 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      {compareMode && <th className="px-6 py-3">Pick</th>}
                      <th className="px-6 py-3">Rank</th>
                      <th className="px-6 py-3">Candidate</th>
                      <th className="px-6 py-3 text-center">Suitability</th>
                      <th className="px-6 py-3">Key Skills</th>
                      <th className="px-6 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {visible.map((c, i) => {
                      const meta = STATUS_BADGE[c.status] || STATUS_BADGE.PENDING
                      return (
                        <tr key={c.id} className="hover:bg-slate-50/60">
                          {compareMode && (
                            <td className="px-6 py-4">
                              <input
                                type="checkbox"
                                checked={selected.includes(c.id)}
                                onChange={() => toggleSelect(c.id)}
                                className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                              />
                            </td>
                          )}
                          <td className="px-6 py-4 text-sm font-semibold text-slate-400">
                            #{i + 1}
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-3">
                              <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-indigo-50 text-sm font-semibold text-indigo-600">
                                {(c.name || '?')[0]}
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="truncate text-sm font-semibold text-slate-900">
                                    {c.name || 'Đang trích xuất…'}
                                  </span>
                                  {c.is_overridden && (
                                    <Badge variant="ai" upper={false}>
                                      Overridden
                                    </Badge>
                                  )}
                                </div>
                                <p className="truncate text-xs text-slate-400">
                                  {c.email || '—'}
                                </p>
                              </div>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center justify-center gap-1.5">
                              {c.score != null ? (
                                <>
                                  <ScoreRing value={c.score} />
                                  <Lightbulb
                                    size={16}
                                    className="text-slate-300"
                                  />
                                </>
                              ) : (
                                <Badge variant={meta.variant} upper={false}>
                                  {c.status === 'PENDING' && (
                                    <RefreshCw size={11} className="animate-spin" />
                                  )}
                                  {meta.label}
                                </Badge>
                              )}
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex flex-wrap gap-1.5">
                              {(c.skills || []).slice(0, 5).map((s) => (
                                <Tag key={s}>{s}</Tag>
                              ))}
                              {(!c.skills || c.skills.length === 0) && (
                                <span className="text-xs text-slate-300">—</span>
                              )}
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex justify-end">
                              <button
                                onClick={() => setOpenId(c.id)}
                                className="rounded-lg border border-indigo-200 bg-indigo-50 p-2 text-indigo-600 transition hover:bg-indigo-100"
                                title="Xem chi tiết ứng viên"
                              >
                                <ExternalLink size={16} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between border-t border-slate-200 px-6 py-3.5 text-sm text-slate-500">
                <span>
                  Hiển thị {visible.length}/{list.length} ứng viên • {completedCount}{' '}
                  đã chấm điểm
                </span>
              </div>
            </>
          )}
        </Card>
      </main>

      {/* Candidate detail popup (real data) */}
      {openId && (
        <CandidateDetailModal
          candidateId={openId}
          onClose={() => setOpenId(null)}
          onOverridden={handleOverridden}
        />
      )}

      {/* Compare popup */}
      {showCompare && compareList.length >= 2 && (
        <CompareModal candidates={compareList} onClose={() => setShowCompare(false)} />
      )}
    </>
  )
}

// So sánh cạnh nhau các ứng viên đã chọn (dữ liệu thật: điểm + kỹ năng).
function CompareModal({ candidates, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
            <GitCompare size={18} className="text-indigo-600" /> Compare Candidates
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={18} />
          </button>
        </div>
        <div className="overflow-auto p-6">
          <div
            className="grid gap-4"
            style={{
              gridTemplateColumns: `repeat(${candidates.length}, minmax(180px, 1fr))`,
            }}
          >
            {candidates.map((c) => (
              <div
                key={c.id}
                className="rounded-xl border border-slate-200 p-4 text-center"
              >
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-base font-semibold text-indigo-600">
                  {(c.name || '?')[0]}
                </div>
                <p className="mt-2 truncate text-sm font-semibold text-slate-900">
                  {c.name || 'Đang trích xuất…'}
                </p>
                <p className="truncate text-xs text-slate-400">{c.email || '—'}</p>
                <div className="mt-3 flex justify-center">
                  {c.score != null ? (
                    <ScoreRing value={c.score} />
                  ) : (
                    <span className="text-xs text-slate-400">Chưa có điểm</span>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap justify-center gap-1.5">
                  {(c.skills || []).slice(0, 6).map((s) => (
                    <Tag key={s}>{s}</Tag>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
