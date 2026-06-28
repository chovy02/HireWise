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

  // HR override: update a candidate's score (and optionally summary), flag the
  // profile as overridden, append an edit-history record, and re-rank so the
  // leaderboard position updates.
  const overrideCandidate = useCallback(
    (projectId, candidateId, changes, editor) => {
      const timestamp = new Date().toISOString()
      setProjects((list) =>
        list.map((p) => {
          if (p.id !== projectId) return p
          const updated = p.candidates.map((c) => {
            if (c.id !== candidateId) return c
            const history = [...c.editHistory]
            // Record each changed field as its own audit entry.
            for (const [field, newValue] of Object.entries(changes)) {
              const oldValue = c[field]
              if (String(oldValue) === String(newValue)) continue
              history.push({
                field,
                oldValue,
                newValue,
                editor: editor || 'HR',
                timestamp,
              })
            }
            if (history.length === c.editHistory.length) return c // nothing changed
            return { ...c, ...changes, overridden: true, editHistory: history }
          })
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
