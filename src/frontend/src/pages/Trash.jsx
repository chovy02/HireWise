import { useCallback, useEffect, useState } from 'react'
import { Trash2, RotateCcw, Briefcase, Users, ShieldAlert } from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import { Card, ConfirmDialog, StateRow } from '../components/ui.jsx'
import { useProjects } from '../context/ProjectContext.jsx'
import { useToast } from '../context/ToastContext.jsx'

// "2026-07-28T09:44:00" -> "28/07/2026 09:44"
function formatDeletedAt(iso) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`
}

export default function Trash() {
  const { fetchTrash, restoreProject, purgeProject } = useProjects()
  const toast = useToast()

  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // id của dự án đang chạy thao tác khôi phục (để khoá đúng thẻ đó, không khoá cả trang)
  const [restoringId, setRestoringId] = useState(null)
  const [pendingPurge, setPendingPurge] = useState(null)
  const [purging, setPurging] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setItems(await fetchTrash())
    } catch (err) {
      setError(err.message || 'Không tải được thùng rác.')
    } finally {
      setLoading(false)
    }
  }, [fetchTrash])

  useEffect(() => {
    load()
  }, [load])

  async function handleRestore(project) {
    setRestoringId(project.id)
    try {
      await restoreProject(project.id)
      setItems((list) => list.filter((p) => p.id !== project.id))
      toast(`Đã khôi phục “${project.title}”.`)
    } catch (err) {
      toast(err.message || 'Không khôi phục được dự án.')
    } finally {
      setRestoringId(null)
    }
  }

  async function confirmPurge() {
    if (!pendingPurge) return
    setPurging(true)
    try {
      await purgeProject(pendingPurge.id)
      setItems((list) => list.filter((p) => p.id !== pendingPurge.id))
      toast(`Đã xoá vĩnh viễn “${pendingPurge.title}”.`)
      setPendingPurge(null)
    } catch (err) {
      toast(err.message || 'Không xoá vĩnh viễn được dự án.')
    } finally {
      setPurging(false)
    }
  }

  const isEmpty = !loading && !error && items.length === 0

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Thùng rác</h1>
          <p className="mt-1 text-sm text-slate-500">
            Dự án đã xoá vẫn giữ nguyên ứng viên và điểm đã chấm. Khôi phục để dùng
            lại, hoặc xoá vĩnh viễn để giải phóng dung lượng.
          </p>
        </div>

        {loading && (
          <Card className="mt-6">
            <StateRow>Đang tải thùng rác…</StateRow>
          </Card>
        )}

        {error && (
          <Card className="mt-6">
            <StateRow tone="error">{error}</StateRow>
          </Card>
        )}

        {isEmpty && (
          <div className="mt-10 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white/60 px-6 py-20 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
              <Trash2 size={30} />
            </div>
            <h2 className="mt-5 text-lg font-semibold text-slate-900">
              Thùng rác đang trống
            </h2>
            <p className="mt-1.5 max-w-md text-sm text-slate-500">
              Khi bạn xoá một dự án ở bảng điều khiển, nó sẽ nằm ở đây cho tới khi
              bạn khôi phục hoặc xoá hẳn.
            </p>
          </div>
        )}

        {!loading && !error && items.length > 0 && (
          <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((p) => {
              const deletedAt = formatDeletedAt(p.deletedAt)
              const busy = restoringId === p.id
              return (
                <Card key={p.id} className="flex flex-col p-5">
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-400">
                      <Briefcase size={18} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate text-base font-semibold text-slate-700">
                        {p.title}
                      </h3>
                      {deletedAt && (
                        <p className="mt-0.5 text-xs text-slate-400">
                          Đã xoá {deletedAt}
                        </p>
                      )}
                    </div>
                  </div>

                  <p className="mt-3 line-clamp-2 flex-1 text-sm leading-relaxed text-slate-500">
                    {p.jdInput || 'Chưa có mô tả.'}
                  </p>

                  <div className="mt-4 flex items-center gap-1.5 border-t border-slate-100 pt-3 text-xs text-slate-500">
                    <Users size={14} /> {p.candidateCount ?? 0} ứng viên
                  </div>

                  <div className="mt-3 flex gap-2">
                    <button
                      onClick={() => handleRestore(p)}
                      disabled={busy}
                      className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <RotateCcw size={15} />
                      {busy ? 'Đang khôi phục…' : 'Khôi phục'}
                    </button>
                    <button
                      onClick={() => setPendingPurge(p)}
                      disabled={busy}
                      title="Xoá vĩnh viễn"
                      aria-label={`Xoá vĩnh viễn dự án ${p.title}`}
                      className="inline-flex items-center justify-center rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </Card>
              )
            })}
          </div>
        )}
      </main>

      <ConfirmDialog
        open={pendingPurge !== null}
        busy={purging}
        title="Xoá vĩnh viễn dự án này?"
        description={
          <>
            <span className="font-semibold text-slate-900">“{pendingPurge?.title}”</span>
            {pendingPurge?.candidateCount > 0 && (
              <>
                {' '}cùng{' '}
                <span className="font-semibold text-slate-900">
                  {pendingPurge.candidateCount} ứng viên
                </span>
                , toàn bộ điểm đánh giá và file CV gốc
              </>
            )}{' '}
            sẽ bị xoá khỏi hệ thống.
            <span className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-700">
              <ShieldAlert size={15} className="mt-0.5 flex-shrink-0" />
              <span>
                Không thể hoàn tác. Muốn chấm điểm lại số CV này sẽ tốn thêm lượt gọi
                AI.
              </span>
            </span>
          </>
        }
        confirmLabel="Xoá vĩnh viễn"
        onConfirm={confirmPurge}
        onCancel={() => !purging && setPendingPurge(null)}
      />
    </>
  )
}
