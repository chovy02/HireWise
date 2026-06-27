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

## What's wired vs. mocked
- **Auth** (login / signup / email verification) → calls the **real** backend
  (`/auth/*`).
- **Dashboard, Shortlisting, CV Analysis, Admin Gateway** → render **mock data**
  from [`src/data/mockData.js`](src/data/mockData.js). Those screens have no
  backend routes yet.

👉 **[`BACKEND_INTEGRATION.md`](BACKEND_INTEGRATION.md)** maps every button to the
endpoint it should call when you connect them.

## Sign-up rules (per spec)
Fields: **name, email, password, confirm password**. The confirm-password check
(and an 8-char minimum) runs **entirely in the browser** — the submit button stays
disabled until they match. Only `{ username, email, password }` is sent to
`POST /auth/register`.

## Structure
```
src/
├── api/            # client.js (fetch wrapper) + auth.js (real endpoints)
├── components/     # Layout, Sidebar, Topbar, AuthLayout, ui.jsx (primitives)
├── context/        # AuthContext (token/user), ToastContext
├── data/           # mockData.js — placeholder data matching the designs
├── pages/          # Login, SignUp, VerifyEmail, Dashboard, Shortlisting,
│                   #   CVAnalysis, AdminGateway
├── App.jsx         # routes (public auth + protected app shell)
└── main.jsx        # entry
```

Routes: `/login`, `/signup`, `/verify` (full-screen auth) · `/`, `/shortlisting`,
`/cv-analysis`, `/admin` (the app shell). **The dashboard is the public landing
page** — no login required to browse the (mocked) screens. Sign in / Sign up live
in the sidebar's bottom-left corner. (`ProtectedRoute.jsx` is kept but unused, in
case you want to re-gate routes like Admin later.)
