import { apiFetch, apiFetchBlob } from './client.js'

// ---- Mẫu email kết quả. Maps 1:1 to src/backend/app/routers/email_templates.py ----
// Chỉ HR (hr_staff) dùng được; mỗi HR có mẫu riêng cho từng loại kết quả.

// Hai loại mẫu duy nhất backend chấp nhận (uq_user_template_type).
export const TEMPLATE_TYPES = ['accepted', 'rejected']

// Các biến động backend thay bằng dữ liệu thật khi gửi (xem SafeDict trong
// services/email_notification.py: gõ sai tên biến thì backend GIỮ NGUYÊN chuỗi
// "{ten_sai}" trong mail chứ không lỗi — nên UI phải cảnh báo trước khi lưu).
export const TEMPLATE_VARIABLES = [
  { token: '{candidate_name}', label: 'Tên ứng viên' },
  { token: '{jd_title}', label: 'Tên vị trí tuyển dụng' },
  { token: '{hr_name}', label: 'Tên người phụ trách (bạn)' },
]

// GET /email-templates -> [EmailTemplateResponse]
// LUÔN trả đủ 2 mẫu (accepted + rejected). Mẫu HR chưa từng lưu có `id: null` —
// đó là bản mặc định của hệ thống, hiển thị được nhưng chưa nằm dưới DB.
export function getEmailTemplates() {
  return apiFetch('/email-templates', { auth: true })
}

// PUT /email-templates/{type} -> EmailTemplateResponse
// Upsert: chưa có thì tạo, có rồi thì cập nhật.
//
// body_format ('text' | 'html') phải gửi kèm: backend dựa vào đúng nó để quyết định
// gửi mail chữ thường hay mail có định dạng. Gửi HTML mà để 'text' thì ứng viên nhận
// được nguyên thẻ <b> giữa câu.
export function upsertEmailTemplate(templateType, payload) {
  return apiFetch(`/email-templates/${templateType}`, {
    method: 'PUT',
    body: {
      subject: payload.subject,
      body_template: payload.body_template,
      body_format: payload.body_format || 'text',
      is_active: payload.is_active,
    },
    auth: true,
  })
}

// POST /email-templates/{type}/attachments (multipart) -> EmailAttachmentResponse
//
// isInline=true dành cho ảnh chèn GIỮA nội dung: kết quả có `content_id`, và nội dung
// HTML trỏ tới ảnh bằng <img src="cid:{content_id}"> — đó là cách duy nhất ứng dụng
// mail hiển thị được ảnh nằm trong bài. isInline=false là file đính kèm bình thường.
export function uploadEmailAttachment(templateType, file, isInline = false) {
  const form = new FormData()
  form.append('file', file)
  // FormData chỉ mang chuỗi; FastAPI tự đổi 'true'/'false' thành bool cho Form(bool).
  form.append('is_inline', isInline ? 'true' : 'false')
  return apiFetch(`/email-templates/${templateType}/attachments`, {
    method: 'POST',
    body: form,
    auth: true,
  })
}

// DELETE /email-templates/{type}/attachments/{id} -> 204
export function deleteEmailAttachment(templateType, attachmentId) {
  return apiFetch(`/email-templates/${templateType}/attachments/${attachmentId}`, {
    method: 'DELETE',
    auth: true,
  })
}

// GET /email-templates/{type}/attachments/{id}/content -> Blob
//
// Cần để HIỆN LẠI ảnh đã chèn trong trình soạn thảo: nội dung lưu dưới DB chỉ có
// "cid:att-...", mà thẻ <img> của trình duyệt không hiểu giao thức đó — và cũng không
// gửi kèm được token Bearer. Nên phải tải bằng fetch rồi đổi sang blob: URL, đúng cách
// trang xem CV đang làm với file PDF.
export function fetchEmailAttachmentBlob(templateType, attachmentId) {
  return apiFetchBlob(
    `/email-templates/${templateType}/attachments/${attachmentId}/content`,
    { auth: true }
  )
}
