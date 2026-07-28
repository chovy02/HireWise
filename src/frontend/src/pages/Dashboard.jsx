import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, FolderPlus, ArrowRight } from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import { PrimaryButton, ConfirmDialog } from '../components/ui.jsx'
import ProjectCard from '../components/ProjectCard.jsx'
import { useProjects } from '../context/ProjectContext.jsx'
import { useToast } from '../context/ToastContext.jsx'

export default function Dashboard() {
  const navigate = useNavigate()
  const { projects, trashProject } = useProjects()
  const toast = useToast()

  // Dự án đang chờ xác nhận xoá (null = hộp thoại đóng). Giữ cả object chứ không chỉ
  // id, để hộp thoại nêu đích danh tên dự án và số ứng viên sắp bị ảnh hưởng.
  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const hasProjects = projects.length > 0

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await trashProject(pendingDelete.id)
      toast(`Đã chuyển “${pendingDelete.title}” vào thùng rác.`)
      setPendingDelete(null)
    } catch (err) {
      toast(err.message || 'Không xoá được dự án. Thử lại sau.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              Bảng điều khiển tuyển dụng
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {hasProjects
                ? 'Các dự án mô tả công việc đang hoạt động của bạn.'
                : 'Bắt đầu bằng cách tạo dự án đầu tiên.'}
            </p>
          </div>
          {/* Có ít nhất 1 dự án -> nút tạo nằm góc trên bên phải.
              whitespace-nowrap: ở 390px nhãn bị bẻ thành 2 dòng và ép sát tiêu đề. */}
          {hasProjects && (
            <PrimaryButton
              onClick={() => navigate('/projects/new')}
              className="flex-shrink-0 whitespace-nowrap"
            >
              <Plus size={16} /> Dự án mới
            </PrimaryButton>
          )}
        </div>

        {/* ---- Empty state ---- */}
        {!hasProjects && (
          <div className="mt-10 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white/60 px-6 py-20 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
              <FolderPlus size={30} />
            </div>
            <h2 className="mt-5 text-lg font-semibold text-slate-900">
              Tạo dự án đầu tiên của bạn
            </h2>
            <p className="mt-1.5 max-w-md text-sm text-slate-500">
              Mỗi dự án ghép một bản mô tả công việc do AI dựng với các nguồn hồ sơ
              ứng viên bạn muốn thu thập. Bấm bên dưới để bắt đầu.
            </p>
            <button
              onClick={() => navigate('/projects/new')}
              className="mt-6 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg shadow-indigo-200 transition hover:bg-indigo-700"
              title="Tạo dự án đầu tiên"
              aria-label="Tạo dự án đầu tiên"
            >
              <Plus size={28} />
            </button>
          </div>
        )}

        {/* ---- Project grid ---- */}
        {hasProjects && (
          <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <ProjectCard
                key={p.id}
                project={p}
                accent="indigo"
                actionLabel="Mở dự án"
                actionIcon={ArrowRight}
                onOpen={() => navigate(`/projects/${p.id}`)}
                onDelete={() => setPendingDelete(p)}
              />
            ))}
          </div>
        )}
      </main>

      <ConfirmDialog
        open={pendingDelete !== null}
        busy={deleting}
        title="Chuyển dự án vào thùng rác?"
        description={
          <>
            Dự án <span className="font-semibold text-slate-900">“{pendingDelete?.title}”</span>
            {pendingDelete?.candidateCount > 0 && (
              <> cùng <span className="font-semibold text-slate-900">{pendingDelete.candidateCount} ứng viên</span> đã chấm điểm</>
            )}{' '}
            sẽ được chuyển vào thùng rác. Bạn có thể khôi phục lại bất cứ lúc nào.
          </>
        }
        confirmLabel="Chuyển vào thùng rác"
        onConfirm={confirmDelete}
        onCancel={() => !deleting && setPendingDelete(null)}
      />
    </>
  )
}
