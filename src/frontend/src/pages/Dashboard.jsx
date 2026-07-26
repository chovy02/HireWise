import { useNavigate } from 'react-router-dom'
import { Plus, FolderPlus, Briefcase, Users, ArrowRight } from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import { Card, PrimaryButton } from '../components/ui.jsx'
import { useProjects } from '../context/ProjectContext.jsx'

export default function Dashboard() {
  const navigate = useNavigate()
  const { projects } = useProjects()

  const hasProjects = projects.length > 0

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
              <button
                key={p.id}
                onClick={() => navigate(`/projects/${p.id}`)}
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
                  <p className="mt-3 line-clamp-3 flex-1 text-sm leading-relaxed text-slate-500">
                    {p.jdInput || 'Chưa có mô tả.'}
                  </p>
                  <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-500">
                    <span className="inline-flex items-center gap-1.5">
                      <Users size={14} /> {p.candidateCount ?? 0} ứng viên
                    </span>
                    <span className="inline-flex items-center gap-1 font-medium text-indigo-600 group-hover:gap-1.5">
                      Mở <ArrowRight size={14} />
                    </span>
                  </div>
                </Card>
              </button>
            ))}
          </div>
        )}
      </main>
    </>
  )
}
