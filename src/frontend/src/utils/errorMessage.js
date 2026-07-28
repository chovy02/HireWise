// Đổi thông báo lỗi kỹ thuật từ backend/nhà cung cấp AI thành câu HR đọc hiểu được.
//
// candidates.error_message lưu NGUYÊN VĂN lỗi (kể cả khối JSON dài của Groq) — như
// vậy là đúng, vì khi debug ta cần đủ chi tiết. Nhưng đổ nguyên khối đó lên giao
// diện thì HR không hiểu gì và cũng không biết phải làm gì tiếp. Hàm này rút ra
// điều DUY NHẤT họ cần biết: chuyện gì xảy ra và có nên bấm "Thử lại" hay không.

// "28m11.712s" -> "khoảng 28 phút" | "45.3s" -> "khoảng 1 phút"
function formatWait(raw) {
  if (!raw) return null
  const h = Number((raw.match(/(\d+(?:\.\d+)?)h/) || [])[1] || 0)
  const m = Number((raw.match(/(\d+(?:\.\d+)?)m(?!s)/) || [])[1] || 0)
  const s = Number((raw.match(/(\d+(?:\.\d+)?)s/) || [])[1] || 0)
  const totalMin = h * 60 + m + s / 60
  if (!totalMin) return null
  if (totalMin < 1) return 'khoảng 1 phút'
  if (totalMin < 60) return `khoảng ${Math.ceil(totalMin)} phút`
  return `khoảng ${Math.round(totalMin / 60)} giờ`
}

/**
 * @param {string|null} raw - candidates.error_message
 * @returns {{title: string, hint: string, raw: string|null, retryUseful: boolean}}
 *   retryUseful=false nghĩa là bấm "Thử lại" ngay bây giờ cũng vô ích.
 */
export function humanizeExtractionError(raw) {
  if (!raw || !raw.trim()) {
    return {
      title: 'Không rõ nguyên nhân',
      hint: 'Hệ thống không ghi lại được lý do. Bấm "Thử lại" để chạy lại và ghi nhận lỗi cụ thể nếu còn.',
      raw: null,
      retryUseful: true,
    }
  }

  const text = String(raw)

  // Hết hạn mức của nhà cung cấp AI. Đây là lỗi hay gặp nhất khi chấm nhiều CV
  // trong ngày, và là lỗi DUY NHẤT mà thử lại ngay chắc chắn thất bại.
  if (/429|rate.?limit|rate_limit_exceeded|quota|TPD|tokens per day/i.test(text)) {
    const wait = formatWait((text.match(/try again in ([\dhms.]+)/i) || [])[1])
    const isDaily = /per day|TPD/i.test(text)
    return {
      title: isDaily
        ? 'Đã dùng hết hạn mức AI trong ngày'
        : 'Gọi AI quá nhanh, bị tạm chặn',
      hint: isDaily
        ? `Tài khoản AI đã hết số token cho phép trong 24 giờ. Thử lại ${
            wait ? `sau ${wait}` : 'vào ngày mai'
          } hoặc nâng hạn mức. Bấm "Thử lại" lúc này sẽ vẫn lỗi.`
        : `Hệ thống gọi AI dồn dập nên bị chặn tạm thời. Đợi ${
            wait || 'một lát'
          } rồi bấm "Thử lại".`,
      raw: text,
      retryUseful: false,
    }
  }

  // CV không có text để đọc -> thử lại bao nhiêu lần cũng vậy.
  if (/không đọc được text|không có text|scan|ảnh/i.test(text)) {
    return {
      title: 'CV không có nội dung chữ',
      hint: 'File này nhiều khả năng là ảnh chụp/scan nên không trích được chữ. Cần bản CV dạng text (PDF xuất từ Word) thay vì ảnh.',
      raw: text,
      retryUseful: false,
    }
  }

  if (/timeout|timed out|deadline|connection|network|unavailable|503|502/i.test(text)) {
    return {
      title: 'Không kết nối được dịch vụ AI',
      hint: 'Mạng chập chờn hoặc dịch vụ AI đang quá tải. Đây là lỗi tạm thời, bấm "Thử lại" thường là được.',
      raw: text,
      retryUseful: true,
    }
  }

  if (/json|parse|decode|unexpected token/i.test(text)) {
    return {
      title: 'AI trả về dữ liệu không đọc được',
      hint: 'Model sinh ra kết quả sai định dạng — lỗi ngẫu nhiên, chạy lại thường sẽ ổn.',
      raw: text,
      retryUseful: true,
    }
  }

  // Không nhận dạng được: hiện câu ngắn, chi tiết đầy đủ để trong phần "xem thêm".
  return {
    title: 'CV xử lý không thành công',
    hint: 'Lỗi không nằm trong các trường hợp thường gặp. Bấm "Thử lại"; nếu vẫn lỗi, xem chi tiết kỹ thuật bên dưới.',
    raw: text,
    retryUseful: true,
  }
}
