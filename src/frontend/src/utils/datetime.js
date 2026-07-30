// Hiển thị mọi mốc thời gian theo GIỜ VIỆT NAM (UTC+7).
//
// QUY ƯỚC CỦA HỆ THỐNG: backend lưu và trả về thời điểm ở dạng ISO-8601 CÓ offset
// ("2026-07-26T13:02:53+00:00" hoặc "...Z"). Frontend chỉ làm một việc: quy đổi sang
// UTC+7 để hiển thị. Đừng tự cộng/trừ giờ bằng tay ở chỗ nào khác.
//
// BA CÁI BẪY mà file này xử lý:
//
// 1. CHUỖI KHÔNG CÓ OFFSET. Theo chuẩn ECMAScript, `new Date("2026-07-26T13:02:53")`
//    được hiểu là GIỜ ĐỊA PHƯƠNG của trình duyệt, còn có "Z"/offset thì mới là UTC.
//    Đây chính là nguyên nhân toàn hệ thống từng hiển thị sớm 7 tiếng. Nay backend đã
//    trả kèm offset, nhưng `parse` dưới đây vẫn tự gắn "Z" cho chuỗi thiếu offset để
//    dữ liệu/API cũ (hoặc cache của trình duyệt) không hiện sai.
//
// 2. MÚI GIỜ CỦA MÁY NGƯỜI DÙNG. Nếu chỉ gọi `toLocaleString('vi-VN')` thì mới đúng
//    ĐỊNH DẠNG tiếng Việt, còn múi giờ vẫn lấy theo máy — laptop đặt sai TZ hay HR
//    truy cập từ nước ngoài sẽ thấy giờ khác nhau trên cùng một dữ liệu. Phải truyền
//    `timeZone` tường minh mới ghim được về UTC+7 cho mọi người.
//
// 3. THỨ TỰ NGÀY/GIỜ KHÔNG ỔN ĐỊNH. `toLocaleString('vi-VN', {...})` tuỳ phiên bản
//    ICU có thể trả "17:50 30/07/2026" (giờ trước ngày). Vì vậy ở đây GHÉP TAY phần
//    ngày với phần giờ, để luôn ra "30/07/2026 17:50" — đúng thói quen đọc của người
//    Việt và khớp với định dạng các trang vẫn đang dùng.

export const APP_TIME_ZONE = 'Asia/Ho_Chi_Minh'

const LOCALE = 'vi-VN'

// Chuỗi ISO thiếu offset -> coi là UTC (xem bẫy số 1 ở trên).
// Khớp "YYYY-MM-DDTHH:MM[:SS[.mmm]]" mà KHÔNG có "Z" hay "±HH:MM" ở cuối.
const ISO_WITHOUT_OFFSET = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/

const DATE_PARTS = { day: '2-digit', month: '2-digit', year: 'numeric' }
// hourCycle 'h23' (không dùng hour12:false): đảm bảo nửa đêm ra "00:00" chứ không
// phải "24:00" — một khác biệt có thật giữa các bản ICU.
const TIME_PARTS = { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }

/** Đưa giá trị bất kỳ (chuỗi ISO, số ms, Date) về Date; trả null nếu không hợp lệ. */
export function parse(value) {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value

  const d =
    typeof value === 'string' && ISO_WITHOUT_OFFSET.test(value)
      ? new Date(`${value.replace(' ', 'T')}Z`)
      : new Date(value)

  return Number.isNaN(d.getTime()) ? null : d
}

function datePart(d, options) {
  return d.toLocaleDateString(LOCALE, { timeZone: APP_TIME_ZONE, ...options })
}

function timePart(d, options) {
  return d.toLocaleTimeString(LOCALE, { timeZone: APP_TIME_ZONE, ...TIME_PARTS, ...options })
}

/** "30/07/2026 17:50" — mặc định cho hầu hết chỗ hiển thị. */
export function formatDateTime(value, fallback = '—') {
  const d = parse(value)
  if (!d) return fallback
  return `${datePart(d, DATE_PARTS)} ${timePart(d)}`
}

/** "30/07/2026 17:50:01" — cho nhật ký, nơi cần tới từng giây. */
export function formatDateTimeWithSeconds(value, fallback = '—') {
  const d = parse(value)
  if (!d) return fallback
  return `${datePart(d, DATE_PARTS)} ${timePart(d, { second: '2-digit' })}`
}

/** "30/07/2026" — khi chỉ cần ngày. */
export function formatDate(value, fallback = '—') {
  const d = parse(value)
  if (!d) return fallback
  return datePart(d, DATE_PARTS)
}

/** "30/07 17:50" — bản gọn cho danh sách hẹp (lịch sử chat…).
 *
 * Ghép dấu "/" bằng tay: `toLocaleDateString('vi-VN', {day, month})` (bỏ năm) trả về
 * "30-07" với dấu GẠCH NGANG, lệch với mọi chỗ khác trong app đang dùng dấu gạch chéo.
 */
export function formatShortDateTime(value, fallback = '') {
  const d = parse(value)
  if (!d) return fallback
  const parts = new Intl.DateTimeFormat(LOCALE, {
    timeZone: APP_TIME_ZONE,
    day: '2-digit',
    month: '2-digit',
  }).formatToParts(d)
  const get = (type) => parts.find((p) => p.type === type)?.value ?? ''
  return `${get('day')}/${get('month')} ${timePart(d)}`
}
