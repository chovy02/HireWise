import { apiFetch } from './client.js'

// ---- Shortlist API. Maps 1:1 to src/backend/app/routers/shortlist.py ----
// Tất cả endpoint đều yêu cầu đăng nhập; thao tác ghi cần role hr_staff/admin.

// POST /jds/{jdId}/shortlists  { name } -> ShortlistResponse
export function createShortlist(jdId, name) {
  return apiFetch(`/jds/${jdId}/shortlists`, {
    method: 'POST',
    body: { name },
    auth: true,
  })
}

// GET /jds/{jdId}/shortlists -> [ShortlistListItem]  (kèm item_count)
export function listShortlists(jdId) {
  return apiFetch(`/jds/${jdId}/shortlists`, { auth: true })
}

// GET /shortlists/{id} -> ShortlistResponse  (items sắp theo điểm giảm dần)
export function getShortlist(shortlistId) {
  return apiFetch(`/shortlists/${shortlistId}`, { auth: true })
}

// DELETE /shortlists/{id} -> 204
export function deleteShortlist(shortlistId) {
  return apiFetch(`/shortlists/${shortlistId}`, { method: 'DELETE', auth: true })
}

// POST /shortlists/{id}/items  { candidate_id } -> ShortlistItemResponse
// Backend chặn: ứng viên khác JD (400), đã có trong shortlist (409).
export function addShortlistItem(shortlistId, candidateId) {
  return apiFetch(`/shortlists/${shortlistId}/items`, {
    method: 'POST',
    body: { candidate_id: candidateId },
    auth: true,
  })
}

// PATCH /shortlists/{id}/items/{itemId}  { candidate_status } -> ShortlistItemResponse
// candidate_status: 'pending' | 'accepted' | 'rejected'
export function updateShortlistItemStatus(shortlistId, itemId, candidateStatus) {
  return apiFetch(`/shortlists/${shortlistId}/items/${itemId}`, {
    method: 'PATCH',
    body: { candidate_status: candidateStatus },
    auth: true,
  })
}

// DELETE /shortlists/{id}/items/{itemId} -> 204  (gỡ khỏi shortlist, không xóa ứng viên)
export function removeShortlistItem(shortlistId, itemId) {
  return apiFetch(`/shortlists/${shortlistId}/items/${itemId}`, {
    method: 'DELETE',
    auth: true,
  })
}
