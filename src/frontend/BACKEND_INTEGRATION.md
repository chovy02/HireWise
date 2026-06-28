# Backend Integration Map

This document lists **every interactive control** in the frontend and the backend
endpoint it should call. It's the to-do list for wiring the UI to the API.

Legend:
- ✅ **Exists** — endpoint already implemented in `src/backend/app/routers/`
- 🔲 **To build** — endpoint referenced by the UI but not implemented yet

> The app screens currently render **mock data**. Project state (job
> descriptions, their ingestion sources, candidates, overrides) lives entirely in
> [`src/context/ProjectContext.jsx`](src/context/ProjectContext.jsx) and resets on
> reload. Static placeholder lists (ingestion queue, system alerts, seed
> candidates, JD template) live in
> [`src/data/mockData.js`](src/data/mockData.js). Only the auth flow talks to the
> real backend today.
>
> In dev, Vite proxies `/auth` and `/api` to `http://localhost:8000`
> (see [`vite.config.js`](vite.config.js)), so the Python backend needs **no CORS
> changes**.

---

## 🧭 Project-based workflow (current UX)

A **project == a Job Description campaign**. The flow:

1. **Dashboard** ([`pages/Dashboard.jsx`](src/pages/Dashboard.jsx)) — empty state
   ("Create your first project") or a grid of project cards. **Add** button
   (top-right once projects exist).
2. **Create project** ([`pages/CreateProject.jsx`](src/pages/CreateProject.jsx)) —
   left: natural-language JD box; right: Multi-Channel Ingestion Hub (pick the
   first source); bottom: **Add**. On submit the JD is generated and the user
   returns to the dashboard with a new card.
3. **Project detail** ([`pages/ProjectDetail.jsx`](src/pages/ProjectDetail.jsx)) —
   opening a card shows the **generated JD**, the list of **ingestion sources**
   (+ **Add Source** to add more CVs / link / inbox), the ingestion queue, and a
   **View Shortlist** button scoped to that JD.
4. **Shortlisting** ([`pages/Shortlisting.jsx`](src/pages/Shortlisting.jsx)) —
   project-scoped leaderboard. The per-row button opens the **candidate popup**
   ([`components/CandidateModal.jsx`](src/components/CandidateModal.jsx)) — the old
   CV Analysis page is gone. The popup's **pen icon** overrides the AI evaluation.

Replace the `ProjectContext` handler bodies (`addProject`, `addSource`,
`overrideCandidate`, `toggleShortlist`) with `fetch()` calls when the API exists.

---

## 📁 Projects / Job Descriptions — [`context/ProjectContext.jsx`](src/context/ProjectContext.jsx)

| Control / handler | Method & Endpoint | Status | Backs onto (model) |
|---|---|---|---|
| **Add** (create project) → `addProject()` | `POST /api/job-descriptions` (send `raw_text` + first source; AI returns `title`, `jd_markdown`, `requirements`) | 🔲 | `JobDescription` (+ `requirements` JSONB) |
| Dashboard project grid (data) | `GET /api/job-descriptions` | 🔲 | `JobDescription` list |
| Open a project (detail) | `GET /api/job-descriptions/{id}` | 🔲 | `JobDescription` (+ sources, counts) |
| **Add Source** → `addSource()` | `POST /api/job-descriptions/{id}/sources` `{ method, value }` (`upload` = multipart) | 🔲 | new `IngestionSource` table → `Candidate.source_id` |
| Ingestion Sources list (data) | `GET /api/job-descriptions/{id}/sources` | 🔲 | `IngestionSource` (+ per-source CV count) |
| Ingestion source by method | `upload` → `POST /api/ingestion/upload` · `link` → `POST /api/ingestion/link` · `email` → `POST /api/ingestion/email` | 🔲 | `Candidate` (+ `file_hash` dedupe, `source`) |

---

## 🔐 Authentication — fully wired today

All three call the real backend via [`src/api/auth.js`](src/api/auth.js).

| Control | File | Method & Endpoint | Status | Notes |
|---|---|---|---|---|
| **Sign in** button | [`pages/Login.jsx`](src/pages/Login.jsx) | `POST /auth/login` | ✅ | Body `{ email, password }`. Stores `access_token` + `user` in `localStorage`, redirects to `/`. |
| **Create account** button | [`pages/SignUp.jsx`](src/pages/SignUp.jsx) | `POST /auth/register` | ✅ | Body `{ username, email, password }`. Frontend maps the "Full name" field → `username`. |
| Confirm-password match | [`pages/SignUp.jsx`](src/pages/SignUp.jsx) | *(none — client-side only)* | — | **Checked entirely in the browser** as requested. Submit is disabled until passwords match and length ≥ 8. Never hits the backend. |
| **Verify account** button | [`pages/VerifyEmail.jsx`](src/pages/VerifyEmail.jsx) | `POST /auth/verify-email` | ✅ | Body `{ token }` — the JWT the backend emails after registration. On success → `/login`. |
| **Sign out** (sidebar gear menu) | [`components/Sidebar.jsx`](src/components/Sidebar.jsx) | *(none — clears local token)* | — | Clears `localStorage`; add a `POST /auth/logout` here later if you implement server-side token revocation. |

**Auth flow:** Register → backend emails a 15-min JWT → user pastes it on `/verify`
→ account `is_active = True` → Login.

---

## 📊 Dashboard — [`pages/Dashboard.jsx`](src/pages/Dashboard.jsx)

The dashboard is now a **project list** (see *Projects / Job Descriptions* above).

| Control | Method & Endpoint | Status | Backs onto (model) |
|---|---|---|---|
| Project grid + counts (data) | `GET /api/job-descriptions` | 🔲 | `JobDescription` (+ source count, candidate count) |
| **Add** / first-project **+** | navigates to `/projects/new` (create form) | — | — |
| Open a project card | navigates to `/projects/{id}` | — | — |

### Ingestion queue / alerts (shown on project detail)

| Control | Method & Endpoint | Status | Backs onto (model) |
|---|---|---|---|
| **Ingestion Queue** list (data) | `GET /api/job-descriptions/{id}/queue` | 🔲 | derive from `Candidate.status` / a jobs table |
| **System Alerts** list (data) | `GET /api/system/alerts` | 🔲 | `SystemLog` (level = WARNING/ERROR/INFO) |

---

## 👥 Shortlisting — [`pages/Shortlisting.jsx`](src/pages/Shortlisting.jsx)

Project-scoped. The leaderboard reorders live when an evaluation is overridden.

| Control | Method & Endpoint | Status | Backs onto (model) |
|---|---|---|---|
| Project (JD) switch | `GET /api/job-descriptions` | 🔲 | `JobDescription` |
| Leaderboard table (data) | `GET /api/shortlist?jd_id=…&sort=ai_rank` | 🔲 | `Shortlist` + `ShortlistItem` + `Evaluation.score` |
| **Semantic Search** | `POST /api/shortlist/search` `{ jd_id, query }` | 🔲 | Vector search over `Candidate.raw_text` / `CandidateSkill` |
| **Filters** / chip **×** | query params on `GET /api/shortlist` | 🔲 | filter on `Evaluation`, `CandidateSkill`, experience |
| **Sort: AI Rank** | `GET /api/shortlist?sort=ai_rank\|score\|name` | 🔲 | order by `Evaluation.score` |
| **💡 explain score** (per row) | `GET /api/evaluations/{cv_id}` | 🔲 | `Evaluation.explanation` / `score_breakdown` |
| **↗ open profile** (per row) | opens candidate popup → `GET /api/candidates/{id}` + `GET /api/evaluations/{cv_id}` | 🔲 | `Candidate` (+ `Evaluation`) |
| **Compare** (select ≥2 → modal) | `GET /api/candidates?ids=…` (or compose client-side) | 🔲 | `Candidate` + `Evaluation` |

---

## 📄 Candidate popup — [`components/CandidateModal.jsx`](src/components/CandidateModal.jsx)

Replaces the old CV Analysis page. Opened from the Shortlisting leaderboard.

| Control / handler | Method & Endpoint | Status | Backs onto (model) |
|---|---|---|---|
| Popup data (resume + brief) | `GET /api/candidates/{id}` + `GET /api/evaluations/{cv_id}` | 🔲 | `Candidate`, `CandidateSkill`, `Evaluation` |
| **Original PDF** | `GET /api/candidates/{id}/file` (download) | 🔲 | `Candidate.file_path` |
| **Proceed to Shortlist** → `toggleShortlist()` | `POST /api/shortlist/{item_id}/approve` (or `DELETE` to unshortlist) | 🔲 | `ShortlistItem.candidate_status` |
| **Leaderboard** / **Compare** buttons | navigate / open compare (see Shortlisting) | — | — |
| **✏️ Override AI evaluation** (pen) → `overrideCandidate()` | `PATCH /api/evaluations/{cv_id}` `{ score, match_score, profile, verified_skills, deductions, flags, summary }` | 🔲 | `Evaluation` + `CandidateSkill` (set `is_overridden=true`) |
| → records edit history (one row per changed field) | `POST /api/evaluations/{cv_id}/history` *(or audit rows on the PATCH)* `{ field, old_value, new_value, editor, timestamp }` | 🔲 | new `EvaluationEdit` audit table |
| → re-rank leaderboard | server recomputes rank on the override `PATCH`; client re-sorts by `score` | 🔲 | order by `Evaluation.score` |

> **Override contract (matches the use case):** the pen toggles edit mode, where
> HR can edit **every AI-written field** — suitability score, match %, extracted
> profile (experience / education), verified skills, AI deductions (title +
> evidence), and flags. On save: each changed field is updated to HR's value, the
> profile is flagged **overridden** (`is_overridden`), one edit-history record per
> changed field (`field`, `old_value`, `new_value`, `editor`, `timestamp`) is
> appended, and the candidate's leaderboard position updates. All of this is done
> client-side today in `overrideCandidate()` (the popup computes the per-field
> diff; the context applies the patch, stamps history, and re-ranks).

---

## 🛡️ Admin Gateway — [`pages/AdminGateway.jsx`](src/pages/AdminGateway.jsx)

### Agent Monitor tab
| Control | Method & Endpoint | Status | Backs onto (model) |
|---|---|---|---|
| Stat cards (status / API calls / agents / error rate) | `GET /api/admin/metrics` | 🔲 | aggregate `AgentToolLog`, `SystemLog` |
| **LLM Tool Invocations** chart (data) | `GET /api/admin/metrics?range=24h\|7d\|30d` | 🔲 | `AgentToolLog.created_at` time-buckets |
| time-range **dropdown** | re-query above with `range` | 🔲 | — |
| **Security & Error Logs** bars (data) | `GET /api/admin/metrics` (error distribution) | 🔲 | `SystemLog` / `AgentToolLog.status` grouped |
| **View Full Logs →** | `GET /api/admin/logs` | 🔲 | `SystemLog`, `AgentToolLog` |

### Access Control (RBAC) tab
| Control | Method & Endpoint | Status | Backs onto (model) |
|---|---|---|---|
| Permission matrix (data) | `GET /api/admin/permissions` | 🔲 | roles ↔ permissions (new table) + `User.role` |
| permission **toggles** | local state until saved | — | System Admin column is locked on (full access) |
| **+ Add New Role** | `POST /api/admin/roles` | 🔲 | new roles table |
| **Save Changes** | `PUT /api/admin/permissions` (sends full matrix) | 🔲 | persist role/permission grid |

---

## How to wire one up (example)

Today the project state is mocked in
[`src/context/ProjectContext.jsx`](src/context/ProjectContext.jsx). To connect,
turn each handler into an API call. Example — **create project** (`addProject`):

```jsx
// 1. add to src/api/ (new file, e.g. projects.js)
import { apiFetch } from './client.js'
export const createProject = (body) =>
  apiFetch('/api/job-descriptions', { method: 'POST', body, auth: true })

// 2. in ProjectContext.jsx, make addProject async and call the API
const addProject = useCallback(async ({ jdInput, ingestion }) => {
  const jd = await createProject({ raw_text: jdInput, source: ingestion })
  // jd already contains the AI-generated title + jd_markdown from the server
  setProjects((list) => [jd, ...list])
  return jd.id
}, [])
```

The same pattern applies to `addSource`
(`POST /api/job-descriptions/{id}/sources`), `overrideCandidate`
(`PATCH /api/evaluations/{cv_id}` + history), and `toggleShortlist`
(`POST /api/shortlist/{item_id}/approve`).

`apiFetch(path, { auth: true })` automatically attaches the
`Authorization: Bearer <token>` header from `localStorage`.
