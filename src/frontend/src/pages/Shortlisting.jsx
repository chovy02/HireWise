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
  ListChecks,
  ListPlus,
  Check,
  Trash2,
  CheckCircle2,
  XCircle,
  Circle,
  MessageSquareText,
  Loader2,
  Sparkles,
  Award,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  Badge,
  Tag,
  ScoreRing,
  Dropdown,
  SecondaryButton,
  PrimaryButton,
} from '../components/ui.jsx'
import CandidateDetailModal from '../components/CandidateDetailModal.jsx'
import { InterviewPanel } from '../components/InterviewModal.jsx'
import Markdown from '../components/Markdown.jsx'
import { formatName } from '../utils/formatName.js'
import { useToast } from '../context/ToastContext.jsx'
import { useProjects } from '../context/ProjectContext.jsx'
import { getCandidates } from '../api/jds.js'
import { compareCandidates } from '../api/compare.js'
import {
  listShortlists,
  createShortlist,
  getShortlist,
  deleteShortlist,
  addShortlistItem,
  updateShortlistItemStatus,
  removeShortlistItem,
} from '../api/shortlists.js'

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
  const [interviewFor, setInterviewFor] = useState(null) // { id, name } ứng viên đang phỏng vấn
  const [compareMode, setCompareMode] = useState(false)
  const [selected, setSelected] = useState([])
  const [showCompare, setShowCompare] = useState(false)

  // Ứng viên THẬT của JD đang chọn (GET /jds/{id}/candidates).
  const [rows, setRows] = useState(null) // null = chưa tải
  const [loadErr, setLoadErr] = useState('')

  // Shortlist THẬT (GET /jds/{id}/shortlists + /shortlists/{id}).
  const [view, setView] = useState('leaderboard') // 'leaderboard' | 'shortlist'
  const [shortlists, setShortlists] = useState(null) // danh sách shortlist của JD
  const [activeSlId, setActiveSlId] = useState(null) // shortlist đang chọn
  const [slDetail, setSlDetail] = useState(null) // chi tiết shortlist đang chọn
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')

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

  // Nạp danh sách shortlist khi đổi JD; tự chọn shortlist đầu tiên nếu có.
  useEffect(() => {
    if (!projectId) {
      setShortlists(null)
      setActiveSlId(null)
      setSlDetail(null)
      return
    }
    let cancelled = false
    listShortlists(projectId)
      .then((data) => {
        if (cancelled) return
        setShortlists(data)
        setActiveSlId(data[0]?.id ?? null)
      })
      .catch(() => !cancelled && setShortlists([]))
    return () => {
      cancelled = true
    }
  }, [projectId])

  // Nạp chi tiết shortlist đang chọn.
  useEffect(() => {
    if (!activeSlId) {
      setSlDetail(null)
      return
    }
    let cancelled = false
    setSlDetail(null)
    getShortlist(activeSlId)
      .then((d) => !cancelled && setSlDetail(d))
      .catch(() => !cancelled && setSlDetail(null))
    return () => {
      cancelled = true
    }
  }, [activeSlId])

  // Nạp lại cả danh sách (item_count) lẫn chi tiết sau mỗi thay đổi.
  async function refreshShortlist() {
    if (projectId) {
      try {
        setShortlists(await listShortlists(projectId))
      } catch {
        /* giữ nguyên nếu lỗi tạm thời */
      }
    }
    if (activeSlId) {
      try {
        setSlDetail(await getShortlist(activeSlId))
      } catch {
        /* giữ nguyên */
      }
    }
  }

  async function handleCreateShortlist() {
    const name = newName.trim()
    if (!name) return
    try {
      const sl = await createShortlist(projectId, name)
      setNewName('')
      setCreating(false)
      setShortlists(await listShortlists(projectId))
      setActiveSlId(sl.id)
      toast(`Đã tạo shortlist "${name}".`)
    } catch (e) {
      toast(e.message)
    }
  }

  async function handleDeleteShortlist() {
    if (!activeSlId) return
    if (!window.confirm('Xóa shortlist này? Các ứng viên trong đó sẽ bị gỡ (không xóa CV).'))
      return
    try {
      await deleteShortlist(activeSlId)
      const list = await listShortlists(projectId)
      setShortlists(list)
      setActiveSlId(list[0]?.id ?? null)
      toast('Đã xóa shortlist.')
    } catch (e) {
      toast(e.message)
    }
  }

  async function handleAddToShortlist(candidateId) {
    if (!activeSlId) {
      toast('Hãy tạo hoặc chọn một shortlist trước.')
      return
    }
    try {
      await addShortlistItem(activeSlId, candidateId)
      await refreshShortlist()
      toast('Đã thêm vào shortlist.')
    } catch (e) {
      toast(e.message) // 409 đã có / 400 khác JD -> hiện đúng thông báo backend
    }
  }

  async function handleItemStatus(itemId, statusValue) {
    try {
      await updateShortlistItemStatus(activeSlId, itemId, statusValue)
      await refreshShortlist()
    } catch (e) {
      toast(e.message)
    }
  }

  async function handleRemoveItem(itemId) {
    try {
      await removeShortlistItem(activeSlId, itemId)
      await refreshShortlist()
    } catch (e) {
      toast(e.message)
    }
  }

  // ---- No projects ----
  if (projects.length === 0) {
    return (
      <>
        <Topbar />
        <main className="flex-1 overflow-y-auto px-8 py-7">
          <h1 className="text-2xl font-bold text-slate-900">
            Rút gọn danh sách ứng viên
          </h1>
          <div className="mt-10 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white/60 px-6 py-20 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
              <FolderPlus size={30} />
            </div>
            <h2 className="mt-5 text-lg font-semibold text-slate-900">
              Chưa có dự án nào
            </h2>
            <p className="mt-1.5 max-w-md text-sm text-slate-500">
              Tạo dự án (job description) first — then candidates can be
              ranked and shortlisted against it.
            </p>
            <PrimaryButton className="mt-6" onClick={() => navigate('/projects/new')}>
              <Plus size={16} /> Tạo dự án
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
              Rút gọn danh sách ứng viên
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Chọn một dự án để rút gọn danh sách ứng viên.
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
                    {p.jdInput || 'Chưa có mô tả.'}
                  </p>
                  <div className="mt-4 flex items-center justify-end border-t border-slate-100 pt-3 text-xs">
                    <span className="inline-flex items-center gap-1 font-medium text-indigo-600 group-hover:gap-1.5">
                      Rút gọn <ArrowRight size={14} />
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
  // id ứng viên đã nằm trong shortlist đang chọn (để đổi nút "thêm" thành "đã thêm").
  const shortlistedIds = new Set((slDetail?.items || []).map((i) => i.candidate.id))

  function toggleSelect(id) {
    setSelected((l) => (l.includes(id) ? l.filter((x) => x !== id) : [...l, id]))
  }

  // Mở phỏng vấn: chọn ứng viên rồi chuyển sang tab "Phỏng vấn" (thay cho popup cũ).
  function openInterview(c) {
    setInterviewFor({ id: c.id, name: c.name })
    setView('interview')
  }

  // Sau khi override: cập nhật điểm + cờ trong row rồi xếp lại hạng, và làm mới
  // shortlist để điểm hiển thị trong tab Shortlist cũng cập nhật theo.
  function handleOverridden(candidateId, { score, is_overridden }) {
    setRows((prev) =>
      sortRows(
        (prev || []).map((c) =>
          c.id === candidateId ? { ...c, score, is_overridden } : c
        )
      )
    )
    if (activeSlId) refreshShortlist()
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
                title="Đổi dự án"
              >
                <ArrowLeft size={18} />
              </button>
            )}
            <div>
              <h1 className="text-2xl font-bold text-slate-900">
                Rút gọn danh sách ứng viên
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

          {/* Chuyển chế độ xem bằng dropdown (thay cho thanh tab cũ) */}
          <div className="flex items-center gap-2.5">
            <span className="hidden text-sm font-medium text-slate-500 sm:inline">
              Chế độ xem
            </span>
            <Dropdown
              align="right"
              className="min-w-[190px]"
              value={view}
              onChange={setView}
              options={[
                { value: 'leaderboard', label: 'Leaderboard', icon: Trophy },
                {
                  value: 'shortlist',
                  label: 'Shortlist',
                  icon: ListChecks,
                  badge: slDetail?.items ? slDetail.items.length : undefined,
                },
                { value: 'interview', label: 'Phỏng vấn', icon: MessageSquareText },
              ]}
            />
          </div>
        </div>

        {/* Shortlist selector (chỉ hiện ở Leaderboard & Shortlist) */}
        {view !== 'interview' && (
        <Card className="mt-6 flex flex-wrap items-center gap-3 p-3">
          <div className="flex items-center gap-2">
            <ListChecks size={18} className="text-indigo-600" />
            <span className="text-sm font-semibold text-slate-700">Danh sách rút gọn</span>
          </div>

          {shortlists && shortlists.length > 0 ? (
            <select
              value={activeSlId || ''}
              onChange={(e) => setActiveSlId(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400"
            >
              {shortlists.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.item_count})
                </option>
              ))}
            </select>
          ) : (
            shortlists && (
              <span className="text-sm text-slate-400">Chưa có shortlist nào.</span>
            )
          )}

          {creating ? (
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreateShortlist()
                  if (e.key === 'Escape') {
                    setCreating(false)
                    setNewName('')
                  }
                }}
                placeholder="Tên shortlist mới…"
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400"
              />
              <PrimaryButton className="px-3 py-2" onClick={handleCreateShortlist}>
                Tạo
              </PrimaryButton>
              <SecondaryButton
                className="px-3 py-2"
                onClick={() => {
                  setCreating(false)
                  setNewName('')
                }}
              >
                Hủy
              </SecondaryButton>
            </div>
          ) : (
            <SecondaryButton className="px-3 py-2" onClick={() => setCreating(true)}>
              <Plus size={15} /> Danh sách rút gọn mới
            </SecondaryButton>
          )}

          {activeSlId && !creating && (
            <SecondaryButton
              className="border-red-200 px-3 py-2 text-red-600 hover:bg-red-50"
              onClick={handleDeleteShortlist}
            >
              <Trash2 size={15} /> Xoá
            </SecondaryButton>
          )}
        </Card>
        )}

        {view === 'leaderboard' && (
        <>
        {/* Search + controls */}
        <Card className="mt-4 flex items-center gap-3 p-3">
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
            <GitCompare size={15} /> So sánh
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
              <GitCompare size={15} /> So sánh {selected.length || ''}
            </PrimaryButton>
          </div>
        )}

        {/* Leaderboard */}
        <Card className="mt-5 overflow-hidden">
          <div className="flex items-center gap-2 border-b border-slate-200 px-6 py-3">
            <Trophy size={16} className="text-amber-500" />
            <h2 className="text-sm font-semibold text-slate-800">Bảng xếp hạng</h2>
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
                      {compareMode && <th className="px-6 py-3">Chọn</th>}
                      <th className="px-6 py-3">Hạng</th>
                      <th className="px-6 py-3">Ứng viên</th>
                      <th className="px-6 py-3 text-center">Độ phù hợp</th>
                      <th className="px-6 py-3">Kỹ năng chính</th>
                      <th className="px-6 py-3 text-right">Thao tác</th>
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
                                {(formatName(c.name) || '?')[0]}
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="truncate text-sm font-semibold text-slate-900">
                                    {formatName(c.name) || 'Đang trích xuất…'}
                                  </span>
                                  {c.is_overridden && (
                                    <Badge variant="ai" upper={false}>
                                      Đã ghi đè
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
                            <div className="flex justify-end gap-2">
                              <button
                                onClick={() => handleAddToShortlist(c.id)}
                                disabled={!activeSlId || shortlistedIds.has(c.id)}
                                className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 transition hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white"
                                title={
                                  !activeSlId
                                    ? 'Tạo/chọn một shortlist trước'
                                    : shortlistedIds.has(c.id)
                                      ? 'Đã có trong shortlist'
                                      : 'Thêm vào shortlist'
                                }
                              >
                                {shortlistedIds.has(c.id) ? (
                                  <Check size={16} className="text-emerald-600" />
                                ) : (
                                  <ListPlus size={16} />
                                )}
                              </button>
                              <button
                                onClick={() => openInterview(c)}
                                disabled={c.status !== 'COMPLETED'}
                                className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 transition hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white"
                                title={
                                  c.status === 'COMPLETED'
                                    ? 'Phỏng vấn ứng viên (AI)'
                                    : 'Ứng viên cần được chấm điểm trước khi phỏng vấn'
                                }
                              >
                                <MessageSquareText size={16} />
                              </button>
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
        </>
        )}

        {view === 'shortlist' && (
          <Card className="mt-4 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-slate-200 px-6 py-3">
              <ListChecks size={16} className="text-indigo-600" />
              <h2 className="text-sm font-semibold text-slate-800">
                {slDetail ? slDetail.name : 'Shortlist'}
              </h2>
            </div>

            {!activeSlId && (
              <p className="px-6 py-10 text-sm text-slate-400">
                Chưa có shortlist. Bấm “Danh sách rút gọn mới” ở trên để tạo, rồi thêm ứng
                viên từ tab Leaderboard.
              </p>
            )}
            {activeSlId && slDetail === null && (
              <p className="px-6 py-10 text-sm text-slate-400">Đang tải shortlist…</p>
            )}
            {slDetail?.items && slDetail.items.length === 0 && (
              <p className="px-6 py-10 text-sm text-slate-400">
                Shortlist trống. Sang tab Leaderboard và bấm nút thêm để đưa ứng viên
                vào đây.
              </p>
            )}

            {slDetail?.items && slDetail.items.length > 0 && (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px] text-left">
                    <thead>
                      <tr className="border-b border-slate-200 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                        <th className="px-6 py-3">Hạng</th>
                        <th className="px-6 py-3">Ứng viên</th>
                        <th className="px-6 py-3 text-center">Độ phù hợp</th>
                        <th className="px-6 py-3">Quyết định</th>
                        <th className="px-6 py-3 text-right">Thao tác</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {slDetail.items.map((it, i) => {
                        const c = it.candidate
                        return (
                          <tr key={it.id} className="hover:bg-slate-50/60">
                            <td className="px-6 py-4 text-sm font-semibold text-slate-400">
                              #{i + 1}
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-3">
                                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-indigo-50 text-sm font-semibold text-indigo-600">
                                  {(formatName(c.name) || '?')[0]}
                                </div>
                                <div className="min-w-0">
                                  <span className="block truncate text-sm font-semibold text-slate-900">
                                    {formatName(c.name) || 'Đang trích xuất…'}
                                  </span>
                                  <p className="truncate text-xs text-slate-400">
                                    {c.email || '—'}
                                  </p>
                                </div>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center justify-center">
                                {c.score != null ? (
                                  <ScoreRing value={c.score} />
                                ) : (
                                  <span className="text-xs text-slate-300">—</span>
                                )}
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-1.5">
                                <button
                                  onClick={() => handleItemStatus(it.id, 'accepted')}
                                  title="Chọn"
                                  className={`rounded-md p-1.5 transition ${
                                    it.candidate_status === 'accepted'
                                      ? 'bg-emerald-100 text-emerald-600'
                                      : 'text-slate-400 hover:bg-slate-100'
                                  }`}
                                >
                                  <CheckCircle2 size={17} />
                                </button>
                                <button
                                  onClick={() => handleItemStatus(it.id, 'rejected')}
                                  title="Từ chối"
                                  className={`rounded-md p-1.5 transition ${
                                    it.candidate_status === 'rejected'
                                      ? 'bg-red-100 text-red-600'
                                      : 'text-slate-400 hover:bg-slate-100'
                                  }`}
                                >
                                  <XCircle size={17} />
                                </button>
                                <button
                                  onClick={() => handleItemStatus(it.id, 'pending')}
                                  title="Chờ quyết định"
                                  className={`rounded-md p-1.5 transition ${
                                    it.candidate_status === 'pending'
                                      ? 'bg-slate-200 text-slate-600'
                                      : 'text-slate-400 hover:bg-slate-100'
                                  }`}
                                >
                                  <Circle size={17} />
                                </button>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex justify-end gap-2">
                                <button
                                  onClick={() => openInterview(c)}
                                  disabled={c.status !== 'COMPLETED'}
                                  className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 transition hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white"
                                  title={
                                    c.status === 'COMPLETED'
                                      ? 'Phỏng vấn ứng viên (AI)'
                                      : 'Ứng viên cần được chấm điểm trước khi phỏng vấn'
                                  }
                                >
                                  <MessageSquareText size={16} />
                                </button>
                                <button
                                  onClick={() => setOpenId(c.id)}
                                  className="rounded-lg border border-indigo-200 bg-indigo-50 p-2 text-indigo-600 transition hover:bg-indigo-100"
                                  title="Xem chi tiết ứng viên"
                                >
                                  <ExternalLink size={16} />
                                </button>
                                <button
                                  onClick={() => handleRemoveItem(it.id)}
                                  className="rounded-lg border border-red-200 bg-white p-2 text-red-500 transition hover:bg-red-50"
                                  title="Gỡ khỏi shortlist"
                                >
                                  <Trash2 size={16} />
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
                    {slDetail.items.length} ứng viên •{' '}
                    {slDetail.items.filter((i) => i.candidate_status === 'accepted').length}{' '}
                    đã chọn •{' '}
                    {slDetail.items.filter((i) => i.candidate_status === 'rejected').length}{' '}
                    từ chối
                  </span>
                </div>
              </>
            )}
          </Card>
        )}

        {view === 'interview' && (
          interviewFor ? (
            <Card className="mt-4 flex h-[calc(100vh-260px)] min-h-[520px] flex-col overflow-hidden">
              <InterviewPanel
                key={interviewFor.id}
                candidateId={interviewFor.id}
                candidateName={interviewFor.name}
              />
            </Card>
          ) : (
            <Card className="mt-4 flex flex-col items-center justify-center px-6 py-20 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
                <MessageSquareText size={26} />
              </div>
              <h2 className="mt-4 text-lg font-semibold text-slate-900">
                Chưa chọn ứng viên
              </h2>
              <p className="mt-1.5 max-w-md text-sm text-slate-500">
                Sang tab Leaderboard hoặc Shortlist và bấm nút phỏng vấn{' '}
                <MessageSquareText size={14} className="inline align-text-bottom" /> ở
                một ứng viên đã được chấm điểm để bắt đầu buổi phỏng vấn.
              </p>
            </Card>
          )
        )}
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

// Các khía cạnh gợi ý sẵn cho việc so sánh. Giá trị rỗng = so sánh toàn diện.
const COMPARE_ASPECTS = [
  { label: 'Toàn diện', value: '' },
  { label: 'Chuyên môn kỹ thuật', value: 'Chuyên môn kỹ thuật và độ sâu công nghệ' },
  { label: 'Kinh nghiệm', value: 'Bề dày và mức độ liên quan của kinh nghiệm làm việc' },
  { label: 'Kỹ năng lãnh đạo', value: 'Kỹ năng lãnh đạo và quản lý' },
  { label: 'Độ phù hợp với JD', value: 'Mức độ phù hợp tổng thể với yêu cầu công việc (JD)' },
]

// So sánh ứng viên bằng AI: HR chọn khía cạnh -> gọi POST /compare -> hiển thị
// đề xuất + bài phân tích chi tiết (Markdown).
function CompareModal({ candidates, onClose }) {
  const toast = useToast()
  const [preset, setPreset] = useState('') // value của khía cạnh đang chọn
  const [customAspect, setCustomAspect] = useState('') // ô nhập tự do
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null) // { recommendation, detailed_comparison }
  const [error, setError] = useState('')

  async function handleCompare() {
    const aspect = customAspect.trim() || preset
    setLoading(true)
    setError('')
    try {
      const res = await compareCandidates(
        candidates.map((c) => c.id),
        aspect
      )
      setResult(res)
    } catch (e) {
      setError(e.message || 'Không so sánh được ứng viên.')
      toast(e.message || 'Không so sánh được ứng viên.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
            <GitCompare size={18} className="text-indigo-600" /> So sánh ứng viên
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={18} />
          </button>
        </div>

        <div className="overflow-auto p-6">
          {/* Thẻ tóm tắt ứng viên được so sánh */}
          <div
            className="grid gap-4"
            style={{
              gridTemplateColumns: `repeat(${candidates.length}, minmax(160px, 1fr))`,
            }}
          >
            {candidates.map((c) => (
              <div
                key={c.id}
                className="rounded-xl border border-slate-200 p-4 text-center"
              >
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-base font-semibold text-indigo-600">
                  {(formatName(c.name) || '?')[0]}
                </div>
                <p className="mt-2 truncate text-sm font-semibold text-slate-900">
                  {formatName(c.name) || 'Đang trích xuất…'}
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

          {/* Chọn khía cạnh so sánh */}
          <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
            <p className="text-sm font-semibold text-slate-700">
              Bạn muốn so sánh về khía cạnh nào?
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {COMPARE_ASPECTS.map((a) => (
                <button
                  key={a.label}
                  onClick={() => {
                    setPreset(a.value)
                    setCustomAspect('')
                  }}
                  disabled={loading}
                  className={`rounded-full border px-3 py-1.5 text-sm transition disabled:opacity-50 ${
                    !customAspect.trim() && preset === a.value
                      ? 'border-indigo-400 bg-indigo-50 font-medium text-indigo-700'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-indigo-300'
                  }`}
                >
                  {a.label}
                </button>
              ))}
            </div>
            <textarea
              value={customAspect}
              onChange={(e) => setCustomAspect(e.target.value)}
              rows={2}
              disabled={loading}
              placeholder="…hoặc nhập tiêu chí riêng (vd: Ai làm backend tốt hơn?)"
              className="mt-3 w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
            />
            <div className="mt-3 flex justify-end">
              <PrimaryButton onClick={handleCompare} disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" /> AI đang phân tích…
                  </>
                ) : (
                  <>
                    <Sparkles size={16} /> {result ? 'So sánh lại' : 'So sánh'}
                  </>
                )}
              </PrimaryButton>
            </div>
          </div>

          {error && (
            <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </p>
          )}

          {/* Kết quả so sánh */}
          {result && (
            <div className="mt-6 space-y-4">
              <div className="rounded-xl border border-indigo-200 bg-indigo-50/70 p-4">
                <h3 className="flex items-center gap-1.5 text-sm font-bold text-indigo-800">
                  <Award size={16} /> Đề xuất của AI
                </h3>
                <div className="mt-1.5 text-indigo-900">
                  <Markdown text={result.recommendation} />
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 p-4">
                <h3 className="text-sm font-bold text-slate-800">
                  Phân tích chi tiết
                </h3>
                <Markdown text={result.detailed_comparison} className="mt-1" />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
