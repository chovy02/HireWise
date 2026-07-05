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
              Recruitment Dashboard
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {hasProjects
                ? 'Your active job description projects.'
                : 'Get started by creating your first project.'}
            </p>
          </div>
          {/* Once at least one project exists, the create button lives top-right. */}
          {hasProjects && (
            <PrimaryButton onClick={() => navigate('/projects/new')}>
              <Plus size={16} /> Add
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
              Create your first project
            </h2>
            <p className="mt-1.5 max-w-md text-sm text-slate-500">
              A project pairs an AI-generated job description with the candidate
              sources you want to ingest from. Click below to begin.
            </p>
            <button
              onClick={() => navigate('/projects/new')}
              className="mt-6 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg shadow-indigo-200 transition hover:bg-indigo-700"
              title="Create your first project"
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
                      <p className="mt-0.5 text-xs text-slate-400">
                        {p.sources.length} source
                        {p.sources.length === 1 ? '' : 's'}
                      </p>
                    </div>
                  </div>
                  <p className="mt-3 line-clamp-3 flex-1 text-sm leading-relaxed text-slate-500">
                    {p.jdInput || 'No description provided.'}
                  </p>
                  <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-500">
                    <span className="inline-flex items-center gap-1.5">
                      <Users size={14} /> {p.candidateCount ?? 0} candidates
                    </span>
                    <span className="inline-flex items-center gap-1 font-medium text-indigo-600 group-hover:gap-1.5">
                      Open <ArrowRight size={14} />
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
