import { apiFetch, apiFetchBlob } from './client.js'

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

// POST /candidates/{id}/retry -> 202 { candidate_id, status: 'PENDING' }
// Chấm lại 1 CV đang FAILED. Chỉ nhận CV ở trạng thái lỗi (backend trả 409 nếu CV
// đang được worker xử lý, 400 nếu CV đã chấm xong).
export function retryCandidate(candidateId) {
  return apiFetch(`/candidates/${candidateId}/retry`, { method: 'POST', auth: true })
}

// GET /candidates/{id} -> CandidateDetailResponse
// Chi tiết ứng viên: skills, projects, và evaluation (score_breakdown, explanation, evidence).
export function getCandidate(candidateId) {
  return apiFetch(`/candidates/${candidateId}`, { auth: true })
}

// GET /candidates/{id}/cv -> Blob (application/pdf)  file CV gốc để nhúng
export function getCandidateCv(candidateId) {
  return apiFetchBlob(`/candidates/${candidateId}/cv`, { auth: true })
}

// PATCH /evaluations/{id}/override  { new_score, reason } -> EvaluationResponse
// UC U005 - HR chỉnh điểm AI chấm; backend lưu lịch sử vào evaluation_overrides.
export function overrideEvaluation(evaluationId, { new_score, reason }) {
  return apiFetch(`/evaluations/${evaluationId}/override`, {
    method: 'PATCH',
    body: { new_score, reason },
    auth: true,
  })
}
