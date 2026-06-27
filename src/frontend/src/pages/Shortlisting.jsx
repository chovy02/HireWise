import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search,
  SlidersHorizontal,
  ArrowUpDown,
  X,
  ExternalLink,
  Lightbulb,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  Badge,
  Tag,
  ScoreRing,
  Segmented,
  SecondaryButton,
} from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import {
  candidatesByCampaign,
  shortlistFilters,
  totalCandidates,
} from '../data/mockData.js'

const CAMPAIGNS = ['Frontend Eng', 'Product Mgr']

export default function Shortlisting() {
  const navigate = useNavigate()
  const toast = useToast()

  const [campaign, setCampaign] = useState('Frontend Eng')
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState(shortlistFilters)

  const candidates = candidatesByCampaign[campaign] || []

  // ACTION: semantic search -> POST /api/shortlist/search { campaign, query }
  function runSearch(e) {
    e.preventDefault()
    if (query.trim()) {
      toast(`Semantic search → POST /api/shortlist/search ("${query.trim()}")`)
    }
  }

  function removeFilter(f) {
    // ACTION: removing a chip re-queries GET /api/shortlist with updated params
    setFilters((list) => list.filter((x) => x !== f))
  }

  // ACTION: open candidate -> navigate to CV Analysis (GET /api/candidates/:id)
  function openCandidate(c) {
    navigate('/cv-analysis', { state: { candidateId: c.id } })
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
              AI-ranked candidates for active campaigns.
            </p>
          </div>
          {/* SWITCH: campaign selector -> GET /api/job-descriptions (list drives) */}
          <Segmented
            options={CAMPAIGNS}
            value={campaign}
            onChange={setCampaign}
          />
        </div>

        {/* Search + controls */}
        <Card className="mt-6 flex items-center gap-3 p-3">
          <form onSubmit={runSearch} className="flex flex-1 items-center gap-2">
            <Search size={18} className="ml-2 flex-shrink-0 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder='Semantic Search: e.g. "Find me someone who has managed a team of at least 5 people and knows React"'
              className="w-full flex-1 bg-transparent text-sm text-slate-700 placeholder-slate-400 outline-none"
            />
            <Badge variant="ai">AI Powered</Badge>
          </form>
          <div className="h-7 w-px bg-slate-200" />
          {/* BUTTON: Filters -> opens filter panel (adds query params to shortlist) */}
          <SecondaryButton onClick={() => toast('Filters → opens filter panel')}>
            <SlidersHorizontal size={15} /> Filters
          </SecondaryButton>
          {/* BUTTON: Sort -> GET /api/shortlist?sort=ai_rank|score|name */}
          <SecondaryButton
            onClick={() => toast('Sort → GET /api/shortlist?sort=ai_rank')}
          >
            <ArrowUpDown size={15} /> Sort: AI Rank
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
                  onClick={() => removeFilter(f)}
                  className="text-slate-400 hover:text-slate-600"
                >
                  <X size={14} />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Candidate table */}
        <Card className="mt-5 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left">
              <thead>
                <tr className="border-b border-slate-200 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  <th className="px-6 py-3">Rank</th>
                  <th className="px-6 py-3">Candidate</th>
                  <th className="px-6 py-3 text-center">Suitability</th>
                  <th className="px-6 py-3">Key Skills</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {candidates.map((c) => (
                  <tr key={c.id} className="hover:bg-slate-50/60">
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
                        {/* BUTTON: explain score -> GET /api/evaluations/:cvId (explanation) */}
                        <button
                          onClick={() =>
                            toast(
                              `Why ${c.score}? → GET /api/evaluations/${c.id} (explanation)`
                            )
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
                        {/* BUTTON: open profile -> CV Analysis (GET /api/candidates/:id) */}
                        <button
                          onClick={() => openCandidate(c)}
                          className="rounded-lg border border-indigo-200 bg-indigo-50 p-2 text-indigo-600 transition hover:bg-indigo-100"
                          title="View full analysis"
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

          {/* Footer / pagination */}
          <div className="flex items-center justify-between border-t border-slate-200 px-6 py-3.5">
            <p className="text-sm text-slate-500">
              Showing {candidates.length} of {totalCandidates} candidates
            </p>
            <div className="flex gap-2">
              {/* BUTTONS: pagination -> GET /api/shortlist?page=N */}
              <SecondaryButton
                className="px-3 py-1.5"
                onClick={() => toast('Prev → GET /api/shortlist?page=…')}
              >
                Prev
              </SecondaryButton>
              <SecondaryButton
                className="px-3 py-1.5"
                onClick={() => toast('Next → GET /api/shortlist?page=…')}
              >
                Next
              </SecondaryButton>
            </div>
          </div>
        </Card>
      </main>
    </>
  )
}
