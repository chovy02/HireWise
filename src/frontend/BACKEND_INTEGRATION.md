# Backend Integration Map

This document lists **every interactive control** in the frontend and the backend
endpoint it should call. It's the to-do list for wiring the UI to the API.

Legend:
- ✅ **Exists** — endpoint already implemented in `src/backend/app/routers/`
- 🔲 **To build** — endpoint referenced by the UI but not implemented yet

> The 4 dashboard screens currently render **mock data** from
> [`src/data/mockData.js`](src/data/mockData.js). Only the auth flow talks to the
> real backend today. Each control below has a `// BUTTON:` / `// ACTION:` comment
> next to it in the source so you can grep for it.
>
> In dev, Vite proxies `/auth` and `/api` to `http://localhost:8000`
> (see [`vite.config.js`](vite.config.js)), so the Python backend needs **no CORS
> changes**.

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

| Control | Method & Endpoint | Status | Backs onto (model) |
|---|---|---|---|
| **+ New Campaign** | `POST /api/job-descriptions` | 🔲 | `JobDescription` |
| **Generate Scoring Matrix** | `POST /api/job-descriptions` (send `raw_text`, AI returns `jd_markdown` + `requirements`) | 🔲 | `JobDescription.requirements` (JSONB) |
| Ingestion tab: **Direct Upload** drop zone / **Browse Files** | `POST /api/ingestion/upload` (multipart ZIP/PDF/DOCX) | 🔲 | `Candidate` (+ `file_hash` dedupe) |
| Ingestion tab: **Link Sync → Connect** | `POST /api/ingestion/link` (Google Forms/Sheet URL) | 🔲 | `Candidate` (`source="google_forms"`) |
| Ingestion tab: **Email Listener → Connect** | `POST /api/ingestion/email` (shared inbox) | 🔲 | `Candidate` (`source="email"`) |
| **Ingestion Queue** list (data) | `GET /api/ingestion/queue` | 🔲 | Queue/job status — consider a new table or derive from `Candidate.status` |
| **System Alerts** list (data) | `GET /api/system/alerts` | 🔲 | `SystemLog` (level = WARNING/ERROR/INFO) |
| Stat cards (Active Drives / CVs Processed / AI Insights) | `GET /api/dashboard/stats` | 🔲 | Aggregates over `JobDescription`, `Candidate`, `AgentToolLog` |

---

## 👥 Shortlisting — [`pages/Shortlisting.jsx`](src/pages/Shortlisting.jsx)

| Control | Method & Endpoint | Status | Backs onto (model) |
|---|---|---|---|
| **Frontend Eng / Product Mgr** switch | `GET /api/job-descriptions` (list active drives) | 🔲 | `JobDescription` |
| Candidate table (data) | `GET /api/shortlist?jd_id=…` | 🔲 | `Shortlist` + `ShortlistItem` + `Evaluation.score` |
| **Semantic Search** (submit) | `POST /api/shortlist/search` `{ jd_id, query }` | 🔲 | Vector/semantic search over `Candidate.raw_text` / `CandidateSkill` |
| **Filters** button | adds query params to `GET /api/shortlist` | 🔲 | filter on `Evaluation`, `CandidateSkill`, experience |
| filter chips **×** | re-query `GET /api/shortlist` with the chip removed | 🔲 | — |
| **Sort: AI Rank** | `GET /api/shortlist?sort=ai_rank\|score\|name` | 🔲 | order by `Evaluation.score` |
| **💡 explain score** (per row) | `GET /api/evaluations/{cv_id}` | 🔲 | `Evaluation.explanation` / `score_breakdown` |
| **↗ open profile** (per row) | navigates to CV Analysis → `GET /api/candidates/{id}` | 🔲 | `Candidate` (+ `Evaluation`) |
| **Prev / Next** | `GET /api/shortlist?page=N` | 🔲 | pagination |

---

## 📄 CV Analysis — [`pages/CVAnalysis.jsx`](src/pages/CVAnalysis.jsx)

| Control | Method & Endpoint | Status | Backs onto (model) |
|---|---|---|---|
| Page data (resume + brief) | `GET /api/candidates/{id}` + `GET /api/evaluations/{cv_id}` | 🔲 | `Candidate`, `CandidateSkill`, `Evaluation` |
| **← Back** | client-side history back | — | — |
| **Original PDF** | `GET /api/candidates/{id}/file` (download) | 🔲 | `Candidate.file_path` |
| **Approve Candidate** | `POST /api/shortlist/{item_id}/approve` | 🔲 | `ShortlistItem.candidate_status = "accepted"` |
| **Hover to highlight source** | uses evidence offsets already in the brief payload | 🔲 | `Evaluation.evidence` (JSONB) |
| **Acknowledge & Dismiss** (flag) | `PATCH /api/evaluations/{id}` `{ flag_acknowledged: true }` | 🔲 | `Evaluation` (add column) — hidden client-side for now |

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

Today the buttons call `toast(...)` as a placeholder. To connect, e.g., **New Campaign**:

```jsx
// 1. add to src/api/ (new file, e.g. campaigns.js)
import { apiFetch } from './client.js'
export const createCampaign = (body) =>
  apiFetch('/api/job-descriptions', { method: 'POST', body, auth: true })

// 2. in Dashboard.jsx, replace the toast handler
onClick={async () => {
  const jd = await createCampaign({ title, raw_text: jobText })
  // refresh list / navigate …
}}
```

`apiFetch(path, { auth: true })` automatically attaches the
`Authorization: Bearer <token>` header from `localStorage`.
