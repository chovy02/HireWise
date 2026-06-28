# AutoRecruit AI — Frontend

React + Vite + Tailwind CSS v4 single-page app replicating the AutoRecruit AI
dashboard designs. Pairs with the FastAPI backend in [`../backend`](../backend).

## Stack
- **React 18** + **react-router-dom 6**
- **Vite 6** (dev server + build)
- **Tailwind CSS v4** (via `@tailwindcss/vite`)
- **lucide-react** (icons)
- Charts are hand-built inline SVG — no chart dependency.

## Run

```bash
cd src/frontend
npm install
npm run dev        # http://localhost:5173
```

`npm run build` → production bundle in `dist/`. `npm run preview` to serve it.

The dev server **proxies** `/auth` and `/api` to `http://localhost:8000`
(the FastAPI backend), so run the backend too — no CORS config needed on the
Python side. See [`vite.config.js`](vite.config.js).

## Workflow (project-based)
The app is organised around **projects** — each project is one Job Description
campaign:

1. **Dashboard** — empty state ("Create your first project") or a grid of project
   cards. The **Add** button (top-right) starts a new one.
2. **Create project** — left: natural-language JD box; right: Multi-Channel
   Ingestion Hub (pick the first source); bottom: **Add**. Submitting generates
   the JD and drops a new card on the dashboard.
3. **Project detail** — opening a card shows the **AI-generated JD**, the list of
   **ingestion sources** with an **Add Source** action (more CVs / link / inbox),
   the ingestion queue, and **View Shortlist**.
4. **Shortlisting** — a project-scoped leaderboard. The per-row button opens the
   **candidate popup** (there is no separate CV Analysis page). The popup's
   **pen icon** lets HR override the AI evaluation — the change is flagged, logged
   to an edit history (old → new, editor, timestamp), and the leaderboard re-ranks.

## What's wired vs. mocked
- **Auth** (login / signup / email verification) → calls the **real** backend
  (`/auth/*`).
- **Projects / candidates / overrides** → held in client state in
  [`src/context/ProjectContext.jsx`](src/context/ProjectContext.jsx) (resets on
  reload — no persistence yet). Static placeholder lists (ingestion queue, system
  alerts, seed candidates, JD template) live in
  [`src/data/mockData.js`](src/data/mockData.js).

👉 **[`BACKEND_INTEGRATION.md`](BACKEND_INTEGRATION.md)** maps every control and
context handler to the endpoint it should call when you connect them.

## Sign-up rules (per spec)
Fields: **name, email, password, confirm password**. The confirm-password check
(and an 8-char minimum) runs **entirely in the browser** — the submit button stays
disabled until they match. Only `{ username, email, password }` is sent to
`POST /auth/register`.

## Structure
```
src/
├── api/            # client.js (fetch wrapper) + auth.js (real endpoints)
├── components/     # Layout, Sidebar, Topbar, AuthLayout, ui.jsx (primitives),
│                   #   CandidateModal (candidate profile + override popup)
├── context/        # AuthContext (token/user), ToastContext,
│                   #   ProjectContext (projects, sources, candidates, overrides)
├── data/           # mockData.js — JD template, seed candidates, queue/alerts
├── pages/          # Login, SignUp, VerifyEmail, Dashboard (project list),
│                   #   CreateProject, ProjectDetail, Shortlisting, AdminGateway
├── App.jsx         # routes (public auth + protected app shell)
└── main.jsx        # entry
```

Routes: `/login`, `/signup`, `/verify` (full-screen auth) · `/` (project list),
`/projects/new` (create), `/projects/:id` (detail), `/shortlisting`, `/admin`
(the app shell). **The dashboard is the public landing page** — no login required
to browse the (mocked) screens. Sign in / Sign up live in the sidebar's
bottom-left corner. (`ProtectedRoute.jsx` is kept but unused, in case you want to
re-gate routes like Admin later.)
