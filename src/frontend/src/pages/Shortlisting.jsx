import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Search,
  SlidersHorizontal,
  ArrowUpDown,
  X,
  ExternalLink,
  Lightbulb,
  Trophy,
  GitCompare,
  CheckCircle2,
  FolderPlus,
  Plus,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  Badge,
  Tag,
  ScoreRing,
  Segmented,
  SecondaryButton,
  PrimaryButton,
} from '../components/ui.jsx'
import CandidateModal from '../components/CandidateModal.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { useProjects } from '../context/ProjectContext.jsx'
import { shortlistFilters } from '../data/mockData.js'

export default function Shortlisting() {
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()
  const { projects } = useProjects()

  // Which project (JD) are we shortlisting against?
  const initialId =
    location.state?.projectId && projects.some((p) => p.id === location.state.projectId)
      ? location.state.projectId
      : projects[0]?.id || null
  const [projectId, setProjectId] = useState(initialId)

  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState(shortlistFilters)
  const [openId, setOpenId] = useState(null) // candidate popup
  const [compareMode, setCompareMode] = useState(false)
  const [selected, setSelected] = useState([]) // ids picked for comparison
  const [showCompare, setShowCompare] = useState(false)

  // ---- No projects: nudge the user to create one first ----
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
            <PrimaryButton
              className="mt-6"
              onClick={() => navigate('/projects/new')}
            >
              <Plus size={16} /> Create a project
            </PrimaryButton>
          </div>
        </main>
      </>
    )
  }

  const project = projects.find((p) => p.id === projectId) || projects[0]
  // Read live from context so overrides + re-ranking reflect instantly.
  const candidates = project.candidates
  const visible = candidates.filter((c) =>
    query.trim()
      ? (c.name + ' ' + c.title + ' ' + c.skills.join(' '))
          .toLowerCase()
          .includes(query.trim().toLowerCase())
      : true
  )
  const openCandidate = candidates.find((c) => c.id === openId) || null
  const compareList = candidates.filter((c) => selected.includes(c.id))

  function toggleSelect(id) {
    setSelected((list) =>
      list.includes(id) ? list.filter((x) => x !== id) : [...list, id]
    )
  }

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        {/* Header */}
        <div className="flex items-start justify-between">
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
          {/* Which JD to list — switch between projects */}
          {projects.length > 1 && (
            <Segmented
              options={projects.map((p) => ({ value: p.id, label: p.title }))}
              value={project.id}
              onChange={(id) => {
                setProjectId(id)
                setSelected([])
                setCompareMode(false)
              }}
            />
          )}
        </div>

        {/* Search + controls */}
        <Card className="mt-6 flex items-center gap-3 p-3">
          <div className="flex flex-1 items-center gap-2">
            <Search size={18} className="ml-2 flex-shrink-0 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder='Semantic Search: e.g. "managed a team of at least 5 and knows React"'
              className="w-full flex-1 bg-transparent text-sm text-slate-700 placeholder-slate-400 outline-none"
            />
            <Badge variant="ai">AI Powered</Badge>
          </div>
          <div className="h-7 w-px bg-slate-200" />
          <SecondaryButton onClick={() => toast('Filters → opens filter panel')}>
            <SlidersHorizontal size={15} /> Filters
          </SecondaryButton>
          <SecondaryButton onClick={() => toast('Sort → AI Rank')}>
            <ArrowUpDown size={15} /> Sort: AI Rank
          </SecondaryButton>
          {/* Compare mode toggle */}
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

        {/* Active filter chips */}
        {filters.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {filters.map((f) => (
              <span
                key={f}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600"
              >
                {f}
                <button
                  onClick={() => setFilters((l) => l.filter((x) => x !== f))}
                  className="text-slate-400 hover:text-slate-600"
                >
                  <X size={14} />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Compare action bar */}
        {compareMode && (
          <div className="mt-4 flex items-center justify-between rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3">
            <p className="text-sm text-indigo-700">
              Select candidates to compare ({selected.length} selected).
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

        {/* Leaderboard table */}
        <Card className="mt-5 overflow-hidden">
          <div className="flex items-center gap-2 border-b border-slate-200 px-6 py-3">
            <Trophy size={16} className="text-amber-500" />
            <h2 className="text-sm font-semibold text-slate-800">Leaderboard</h2>
          </div>
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
                {visible.map((c) => (
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
                      #{c.rank}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-indigo-50 text-sm font-semibold text-indigo-600">
                          {c.name[0]}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-slate-900">
                              {c.name}
                            </span>
                            {c.isNew && (
                              <Badge variant="new" upper={false}>
                                New
                              </Badge>
                            )}
                            {c.overridden && (
                              <Badge variant="ai" upper={false}>
                                Overridden
                              </Badge>
                            )}
                            {c.shortlisted && (
                              <Badge variant="completed" upper={false}>
                                <CheckCircle2 size={11} /> Shortlisted
                              </Badge>
                            )}
                          </div>
                          <p className="text-xs text-slate-400">
                            {c.title} • {c.years} years
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-center gap-1.5">
                        <ScoreRing value={c.score} />
                        <button
                          onClick={() =>
                            toast(`Why ${c.score}? → AI explanation (mock)`)
                          }
                          className="text-slate-300 hover:text-amber-500"
                          title="Why this score?"
                        >
                          <Lightbulb size={16} />
                        </button>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-1.5">
                        {c.skills.map((s) => (
                          <Tag key={s}>{s}</Tag>
                        ))}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex justify-end">
                        {/* Opens the candidate popup (no page nav, no CV tab) */}
                        <button
                          onClick={() => setOpenId(c.id)}
                          className="rounded-lg border border-indigo-200 bg-indigo-50 p-2 text-indigo-600 transition hover:bg-indigo-100"
                          title="Open candidate profile"
                        >
                          <ExternalLink size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between border-t border-slate-200 px-6 py-3.5">
            <p className="text-sm text-slate-500">
              Showing {visible.length} of {candidates.length} candidates
            </p>
          </div>
        </Card>
      </main>

      {/* Candidate profile popup */}
      {openCandidate && (
        <CandidateModal
          project={project}
          candidate={openCandidate}
          onClose={() => setOpenId(null)}
          onViewLeaderboard={() =>
            toast('Showing the leaderboard for this project.')
          }
          onCompare={() => {
            setCompareMode(true)
            setSelected([openCandidate.id])
          }}
        />
      )}

      {/* Compare popup */}
      {showCompare && compareList.length >= 2 && (
        <CompareModal
          candidates={compareList}
          onClose={() => setShowCompare(false)}
        />
      )}
    </>
  )
}

// Side-by-side comparison of the selected candidates.
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
            <GitCompare size={18} className="text-indigo-600" /> Compare
            Candidates
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
                  {c.name[0]}
                </div>
                <p className="mt-2 text-sm font-semibold text-slate-900">
                  {c.name}
                </p>
                <p className="text-xs text-slate-400">{c.title}</p>
                <div className="mt-3 flex justify-center">
                  <ScoreRing value={c.score} />
                </div>
                <p className="mt-3 text-xs text-slate-400">Rank #{c.rank}</p>
                <p className="mt-1 text-xs text-slate-400">
                  {c.years} years experience
                </p>
                <div className="mt-3 flex flex-wrap justify-center gap-1.5">
                  {c.skills.map((s) => (
                    <Tag key={s}>{s}</Tag>
                  ))}
                </div>
                {c.overridden && (
                  <p className="mt-3 text-[11px] font-semibold uppercase text-indigo-600">
                    Overridden (AI: {c.aiScore})
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
