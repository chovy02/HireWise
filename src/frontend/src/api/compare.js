import { apiFetch } from './client.js'

// ---- Compare API. Maps 1:1 to src/backend/app/routers/compare.py ----
// Yêu cầu đăng nhập + role hr_staff (backend chặn).

// POST /compare  { candidate_ids, aspect? } -> CompareResponse
// AI đọc CV gốc + JD rồi trả về { recommendation, detailed_comparison(Markdown) }.
// Ràng buộc backend: >= 2 ứng viên, cùng một JD, đều đã COMPLETED.
export function compareCandidates(candidateIds, aspect) {
  return apiFetch('/compare', {
    method: 'POST',
    body: { candidate_ids: candidateIds, aspect: aspect?.trim() || null },
    auth: true,
  })
}
