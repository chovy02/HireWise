import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { createJd, uploadCvs, listJds } from '../api/jds.js'
import { useAuth } from './AuthContext.jsx'

const ProjectContext = createContext(null)

// Re-rank a candidate list by current score (desc) and stamp rank #.
function reRank(candidates) {
  return [...candidates]
    .sort((a, b) => b.score - a.score)
    .map((c, i) => ({ ...c, rank: i + 1 }))
}

// Map 1 JD (bản rút gọn từ listJds) sang shape "project" mà UI dùng.
function mapJdToProject(jd) {
  return {
    id: jd.id,
    backendJdId: jd.id,
    title: jd.title,
    jdInput: jd.raw_text || '',
    jdMarkdown: '',
    sources: [],
    createdAt: jd.created_at,
    candidates: [],
    candidateCount: jd.candidate_count ?? 0,
  }
}

// Holds every project (== JD campaign) plus its candidates, and the override
// logic. Frontend-only: state lives here, no backend calls. Replace the bodies
// with fetch() when the API exists.
export function ProjectProvider({ children }) {
  const { isAuthenticated, loading: authLoading } = useAuth()
  const [projects, setProjects] = useState([])
  // true trong lúc xác thực token / nạp danh sách JD từ backend (để trang chi tiết
  // không vội redirect). Bắt đầu = true: khi F5 một deep-link, `isAuthenticated`
  // chỉ bật true SAU khi /auth/me trả về, nên nếu khởi tạo false thì ProjectDetail
  // sẽ thấy "không có project + loading=false" và redirect về dashboard trước khi
  // kịp hydrate. Giữ true tới khi auth ổn định + danh sách JD tải xong.
  const [loading, setLoading] = useState(true)

  // Tải lại danh sách project từ backend. Dùng cho AI Copilot: sau khi agent tạo
  // JD mới ở server, gọi hàm này để bảng bên phải phản ánh ngay.
  const refreshProjects = useCallback(async () => {
    try {
      const jds = await listJds()
      setProjects(jds.map(mapJdToProject))
    } catch {
      /* giữ nguyên state cũ nếu refresh lỗi */
    }
  }, [])

  // Hydrate danh sách project từ backend mỗi khi đăng nhập. TRƯỚC ĐÂY state chỉ nằm
  // trong RAM nên F5 / mở lại là mất sạch dù JD vẫn còn trong DB. Chạy lại khi
  // login/logout. Vẫn gắn seed candidates (mock) để trang Shortlisting demo hoạt động;
  // trạng thái xử lý CV THẬT được poll riêng ở ProjectDetail.
  useEffect(() => {
    let cancelled = false
    // Chờ AuthContext xác thực xong token đã lưu trước khi quyết định.
    if (authLoading) {
      setLoading(true)
      return
    }
    if (!isAuthenticated) {
      setProjects([])
      setLoading(false)
      return
    }
    setLoading(true)
    listJds()
      .then((jds) => {
        if (cancelled) return
        setProjects(jds.map(mapJdToProject))
      })
      .catch(() => {
        if (!cancelled) setProjects([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [isAuthenticated, authLoading])

  // Create a project from the natural-language brief + chosen ingestion source.
  // REAL backend calls: (1) POST /jds -> Gemini structures the JD, (2) if a ZIP
  // file was chosen, POST /jds/{id}/cvs -> backend queues each CV to Celery.
  // Async; returns the new project's (== backend JD) id so the caller can navigate.
  //
  // The local project keeps mock seed candidates so the existing Shortlisting /
  // CandidateModal demo still works; the REAL processing status is polled live on
  // the ProjectDetail page using `backendJdId` (== id).
  const addProject = useCallback(async ({ jdInput, ingestion, file }) => {
    // 1) Structure the JD on the backend.
    const jd = await createJd(jdInput)

    // 2) Upload the ZIP (if any) -> triggers background CV processing.
    let uploadSummary = null
    if (file) {
      uploadSummary = await uploadCvs(jd.id, file)
    }

    const firstSource = {
      id: `src-${Date.now()}`,
      method: ingestion?.method || 'upload',
      label: ingestion?.label || 'Direct Upload',
      value: file?.name || ingestion?.source || '',
      // Số CV đã stage (đang được worker chấm điểm nền).
      count: uploadSummary?.processing ?? ingestion?.count ?? 0,
      addedAt: new Date().toISOString(),
    }
    const project = {
      id: jd.id,
      backendJdId: jd.id, // dùng để poll tiến độ xử lý CV thật trên ProjectDetail
      title: jd.title,
      jdInput,
      jdMarkdown: jd.jd_markdown,
      sources: [firstSource], // every source ever ingested for this project
      createdAt: jd.created_at,
      candidates: [],
      // Số CV vừa nạp (stage) để dashboard hiện ngay; sẽ khớp số thật sau khi reload.
      candidateCount: uploadSummary?.total ?? 0,
    }
    setProjects((list) => [project, ...list])
    return jd.id
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

  // Ghi bổ sung chi tiết JD (markdown, mô tả gốc) vào project sau khi ProjectDetail
  // fetch đầy đủ từ backend — vì listJds() chỉ trả bản rút gọn.
  const setProjectDetail = useCallback((id, patch) => {
    setProjects((list) =>
      list.map((p) => (p.id === id ? { ...p, ...patch } : p))
    )
  }, [])

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
        loading,
        refreshProjects,
        addProject,
        addSource,
        getProject,
        setProjectDetail,
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
