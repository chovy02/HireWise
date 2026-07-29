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

// POST /shortlists/{id}/send-notifications -> { message, total_queued }
//
// Gửi mail kết quả cho các ứng viên đã chốt accepted/rejected. Backend TỰ lọc:
// chỉ gửi người chưa gửi lần nào, hoặc người vừa bị đổi quyết định sau lần gửi
// trước (notified_status != candidate_status) -> bấm hai lần không spam ứng viên.
//
// Việc gửi chạy trong BackgroundTasks: API trả về NGAY với số đã xếp hàng, chưa
// phải số đã gửi thành công. Muốn biết ai đã gửi xong thì nạp lại shortlist và
// đọc notified_at của từng item.
export function sendShortlistNotifications(shortlistId) {
  return apiFetch(`/shortlists/${shortlistId}/send-notifications`, {
    method: 'POST',
    auth: true,
  })
}
