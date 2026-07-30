// ---------------------------------------------------------------------------
// Bộ lọc HTML theo danh sách CHO PHÉP, dùng cho nội dung mẫu mail do HR tự soạn.
//
// Vì sao cần: nội dung đó được nạp lại vào trình soạn thảo (contenteditable) và vào
// khung xem trước bằng innerHTML. Chuỗi HTML đi một vòng qua DB rồi quay lại chạy
// trong trang là đúng đường của XSS. Kể cả khi HR chỉ tự hại mình, mẫu còn có thể bị
// người khác đọc (admin xem log, đồng nghiệp mở cùng máy), nên không để lọt <script>,
// thuộc tính on* hay javascript: URL.
//
// Cách làm theo DANH SÁCH CHO PHÉP, không phải danh sách cấm: thẻ/thuộc tính lạ bị
// loại mặc định, nên thêm một thẻ nguy hiểm mới cũng không phá được bộ lọc.
// ---------------------------------------------------------------------------

// Đủ cho các nút định dạng đang có. <font> nằm trong danh sách vì
// document.execCommand('foreColor') của trình duyệt vẫn sinh ra nó.
const ALLOWED_TAGS = new Set([
  'B', 'STRONG', 'I', 'EM', 'U', 'S', 'STRIKE', 'DEL',
  'P', 'DIV', 'BR', 'SPAN', 'FONT',
  'UL', 'OL', 'LI',
  'BLOCKQUOTE', 'PRE', 'CODE',
  'H1', 'H2', 'H3',
  'A', 'IMG',
])

const ALLOWED_ATTRS = {
  A: new Set(['href', 'title', 'target', 'rel']),
  IMG: new Set(['src', 'alt', 'width', 'height', 'data-cid']),
  FONT: new Set(['color', 'face', 'size']),
  SPAN: new Set(['style', 'data-token']),
  DIV: new Set(['style']),
  P: new Set(['style']),
  LI: new Set(['style']),
}

// Chỉ giữ vài thuộc tính CSS vô hại. Cho qua cả `style` nghĩa là mở đường cho
// url(javascript:...) và position:fixed phủ kín trang.
const ALLOWED_STYLES = new Set([
  'color', 'background-color', 'font-weight', 'font-style',
  'text-decoration', 'text-align', 'font-size', 'font-family',
])

// src của ảnh: cid: là ảnh trong mail, blob:/data: là ảnh đang xem trong trình soạn
// thảo. http(s) cũng cho qua vì HR có thể dán ảnh từ web.
const SAFE_URL = /^(https?:|mailto:|cid:|blob:|data:image\/)/i

// Tài liệu TRƠ dùng chung để dựng/sửa HTML ngoài màn hình.
//
// Vì sao không dùng document.createElement('div'): node tạo bằng document hiện tại
// vẫn thuộc tài liệu đang sống, nên chỉ cần gán src là Chrome đi tải tài nguyên —
// kể cả khi node chưa được chèn vào trang. Với src="cid:att-..." (thứ mail dùng,
// trình duyệt không hiểu) thì mỗi lần gán sinh một lỗi ERR_UNKNOWN_URL_SCHEME. Mà
// việc tuần tự hoá chạy sau MỖI phím gõ, nên console đầy lỗi và trình duyệt tải rác
// liên tục. Tài liệu tạo bằng createHTMLDocument() không tải tài nguyên.
const inertDoc = document.implementation.createHTMLDocument('')

/** Phân tích HTML trong tài liệu trơ; trả về một <div> chứa nội dung (không tải ảnh). */
export function parseInert(html) {
  const holder = inertDoc.createElement('div')
  holder.innerHTML = html || ''
  return holder
}

/** Bản sao của `node` nằm trong tài liệu trơ, sửa thoải mái mà không kích hoạt tải. */
export function cloneInert(node) {
  return inertDoc.importNode(node, true)
}

function sanitizeStyle(value) {
  return (value || '')
    .split(';')
    .map((rule) => rule.trim())
    .filter(Boolean)
    .filter((rule) => {
      const prop = rule.split(':')[0]?.trim().toLowerCase()
      if (!ALLOWED_STYLES.has(prop)) return false
      // url(...) trong style là đường vòng kinh điển để nhúng script/ảnh theo dõi.
      return !/url\s*\(/i.test(rule)
    })
    .join('; ')
}

export function sanitizeHtml(dirty) {
  // DOMParser phân tích trong một document RỜI, không gắn vào trang: ảnh không tải,
  // script không chạy, khác hẳn việc gán innerHTML vào một node đang sống.
  const doc = new DOMParser().parseFromString(
    `<div id="__root">${dirty || ''}</div>`,
    'text/html'
  )
  const root = doc.getElementById('__root')
  if (!root) return ''

  // Duyệt trên bản sao danh sách: đang xoá/thay node mà lặp trên live NodeList thì bỏ sót.
  for (const el of [...root.querySelectorAll('*')]) {
    const tag = el.tagName.toUpperCase()

    if (!ALLOWED_TAGS.has(tag)) {
      // Thẻ chứa mã (script/style/iframe) phải xoá CẢ nội dung bên trong. Thẻ lạ mà
      // vô hại (vd <section>) thì giữ lại phần chữ, chỉ bỏ vỏ.
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'IFRAME' || tag === 'OBJECT') {
        el.remove()
      } else {
        el.replaceWith(...el.childNodes)
      }
      continue
    }

    const allowed = ALLOWED_ATTRS[tag] || new Set()
    for (const attr of [...el.attributes]) {
      const name = attr.name.toLowerCase()
      if (!allowed.has(name)) {
        el.removeAttribute(attr.name)
        continue
      }
      if (name === 'style') {
        const cleaned = sanitizeStyle(attr.value)
        if (cleaned) el.setAttribute('style', cleaned)
        else el.removeAttribute('style')
        continue
      }
      if ((name === 'href' || name === 'src') && !SAFE_URL.test(attr.value.trim())) {
        el.removeAttribute(attr.name)
      }
    }

    // Link mở tab mới phải có rel=noopener, kẻo trang đích với tới window.opener.
    if (tag === 'A' && el.getAttribute('target') === '_blank') {
      el.setAttribute('rel', 'noopener noreferrer')
    }
  }

  return root.innerHTML
}
