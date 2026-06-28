import { createContext, useContext, useState, useCallback } from 'react'
import { generateJD, makeSeedCandidates } from '../data/mockData.js'

const ProjectContext = createContext(null)

// Re-rank a candidate list by current score (desc) and stamp rank #.
function reRank(candidates) {
  return [...candidates]
    .sort((a, b) => b.score - a.score)
    .map((c, i) => ({ ...c, rank: i + 1 }))
}

// Holds every project (== JD campaign) plus its candidates, and the override
// logic. Frontend-only: state lives here, no backend calls. Replace the bodies
// with fetch() when the API exists.
export function ProjectProvider({ children }) {
  // Starts empty so the Dashboard shows the "Create your first project" state.
  const [projects, setProjects] = useState([])

  // Create a project from the natural-language brief + chosen ingestion source.
  // Returns the new project's id so the caller can navigate to it.
  const addProject = useCallback(({ jdInput, ingestion }) => {
    const generated = generateJD(jdInput)
    const id = `proj-${Date.now()}`
    const firstSource = {
      id: `src-${Date.now()}`,
      method: ingestion?.method || 'upload',
      label: ingestion?.label || 'Direct Upload',
      value: ingestion?.source || '',
      count: ingestion?.count ?? 0,
      addedAt: new Date().toISOString(),
    }
    const project = {
      id,
      title: generated.title,
      jdInput,
      jdMarkdown: generated.markdown,
      sources: [firstSource], // every source ever ingested for this project
      createdAt: new Date().toISOString(),
      candidates: reRank(makeSeedCandidates()),
    }
    setProjects((list) => [project, ...list])
    return id
  }, [])

  // Add another ingestion source (more CVs / another link / another inbox) to an
  // existing project, so the detail view can list every source that fed it.
  const addSource = useCallback((projectId, source) => {
    setProjects((list) =>
      list.map((p) =>
        p.id !== projectId
          ? p
          : {
              ...p,
              sources: [
                ...p.sources,
                {
                  id: `src-${Date.now()}`,
                  method: source.method || 'upload',
                  label: source.label || 'Direct Upload',
                  value: source.value || '',
                  count: source.count ?? 0,
                  addedAt: new Date().toISOString(),
                },
              ],
            }
      )
    )
  }, [])

  const getProject = useCallback(
    (id) => projects.find((p) => p.id === id) || null,
    [projects]
  )

  // HR override: apply a patch to a candidate (any AI-written field, including
  // the nested `analysis`), flag the profile as overridden, append the supplied
  // edit-history entries (the caller computes old→new diffs since it knows the
  // human-readable labels), and re-rank so the leaderboard position updates.
  const overrideCandidate = useCallback(
    (projectId, candidateId, patch, history, editor) => {
      if (!history || history.length === 0) return // nothing changed
      const timestamp = new Date().toISOString()
      const stamped = history.map((h) => ({
        ...h,
        editor: editor || 'HR',
        timestamp,
      }))
      setProjects((list) =>
        list.map((p) => {
          if (p.id !== projectId) return p
          const updated = p.candidates.map((c) =>
            c.id !== candidateId
              ? c
              : {
                  ...c,
                  ...patch,
                  overridden: true,
                  editHistory: [...c.editHistory, ...stamped],
                }
          )
          return { ...p, candidates: reRank(updated) }
        })
      )
    },
    []
  )

  // Toggle a candidate into / out of the shortlist (the "proceed" step).
  const toggleShortlist = useCallback((projectId, candidateId) => {
    setProjects((list) =>
      list.map((p) =>
        p.id !== projectId
          ? p
          : {
              ...p,
              candidates: p.candidates.map((c) =>
                c.id === candidateId
                  ? { ...c, shortlisted: !c.shortlisted }
                  : c
              ),
            }
      )
    )
  }, [])

  return (
    <ProjectContext.Provider
      value={{
        projects,
        addProject,
        addSource,
        getProject,
        overrideCandidate,
        toggleShortlist,
      }}
    >
      {children}
    </ProjectContext.Provider>
  )
}

export function useProjects() {
  const ctx = useContext(ProjectContext)
  if (!ctx) throw new Error('useProjects must be used within a ProjectProvider')
  return ctx
}
