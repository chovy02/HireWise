import { apiFetch } from './client.js'

// ---- Thông báo cho người dùng. Maps tới src/backend/app/routers/notifications.py ----
// Admin phát thông báo qua /admin/notifications; người dùng đọc thông báo đang bật ở đây.

// GET /notifications -> [NotificationResponse] (chỉ những thông báo is_active=true)
export function getActiveNotifications() {
  return apiFetch('/notifications', { auth: true })
}
