import { apiFetch } from './client.js'

// ---- JD + CV ingestion API. Maps 1:1 to src/backend/app/routers/cv.py ----
// Tất cả endpoint đều yêu cầu đăng nhập (auth: true).

// POST /jds  { raw_text } -> JDResponse
// AI (Gemini) chuẩn hóa mô tả ngôn ngữ tự nhiên thành JD có cấu trúc.
export function createJd(rawText) {
  return apiFetch('/jds', { method: 'POST', body: { raw_text: rawText }, auth: true })
}

// GET /jds -> [JDListItem]
export function listJds() {
  return apiFetch('/jds', { auth: true })
}

// GET /jds/{id} -> JDResponse
export function getJd(jdId) {
  return apiFetch(`/jds/${jdId}`, { auth: true })
}

// GET /jds/{id}/candidates -> [CandidateListItem]  (leaderboard, dùng để poll tiến độ)
export function getCandidates(jdId) {
  return apiFetch(`/jds/${jdId}/candidates`, { auth: true })
}

// POST /jds/{id}/cvs  (multipart, field "file" = ZIP) -> 202 UploadBatchResponse
// Backend stage nhanh rồi đẩy mỗi CV vào Celery xử lý nền.
export function uploadCvs(jdId, file) {
  const form = new FormData()
  form.append('file', file)
  return apiFetch(`/jds/${jdId}/cvs`, { method: 'POST', body: form, auth: true })
}
