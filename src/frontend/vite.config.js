import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The FastAPI backend runs on http://localhost:8000 (see docker-compose.yml).
// We proxy auth/api calls there in dev so we never need to touch the backend
// (no CORS middleware required on the Python side).
//
// Proxy target is env-driven so the same config works in both setups:
//   - running `npm run dev` on the host  -> http://localhost:8000 (default)
//   - running inside docker-compose      -> http://api:8000 (set VITE_PROXY_TARGET)
// Inside the frontend container "localhost" is the container itself, NOT the
// `api` service, so Docker must reach the backend by its service name.
const PROXY_TARGET = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

// If the backend is down or crashing (e.g. before it's fully built), the proxy
// would otherwise surface a cryptic 500. This handler returns a clear 503 + JSON
// message so the login/signup pages can show something helpful instead.
function backendProxy() {
  return {
    target: PROXY_TARGET,
    changeOrigin: true,
    configure: (proxy) => {
      proxy.on('error', (_err, _req, res) => {
        try {
          if (res && !res.headersSent && res.writeHead) {
            res.writeHead(503, { 'Content-Type': 'application/json' })
          }
          if (res && res.end) {
            res.end(
              JSON.stringify({
                detail:
                  'Backend not reachable on http://localhost:8000. Start/rebuild the FastAPI server (see src/backend & docker-compose.yml).',
              })
            )
          }
        } catch {
          /* socket already gone — nothing to do */
        }
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/auth': backendProxy(),
      '/api': backendProxy(),
      // JD / CV / evaluation routers không có prefix /api ở backend.
      '/jds': backendProxy(),
      '/candidates': backendProxy(),
      '/evaluations': backendProxy(),
      '/shortlists': backendProxy(),
      '/users': backendProxy(),
      '/admin': backendProxy(),
      '/interviews': backendProxy(),
      '/compare': backendProxy(),
      '/agent': backendProxy(),
      // Chuông thông báo của người dùng. Thiếu dòng này thì request rơi vào SPA
      // fallback của Vite (trả index.html kèm HTTP 200) và chuông im lặng rỗng.
      '/notifications': backendProxy(),
    },
  },
})
