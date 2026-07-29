import { apiFetch } from './client.js'

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

// PUT /email-templates/{type}  { subject, body_template, is_active } -> EmailTemplateResponse
// Upsert: chưa có thì tạo, có rồi thì cập nhật.
export function upsertEmailTemplate(templateType, payload) {
  return apiFetch(`/email-templates/${templateType}`, {
    method: 'PUT',
    body: {
      subject: payload.subject,
      body_template: payload.body_template,
      is_active: payload.is_active,
    },
    auth: true,
  })
}
