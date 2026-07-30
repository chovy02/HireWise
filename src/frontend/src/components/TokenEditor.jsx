// ---------------------------------------------------------------------------
// Ô soạn thảo hiển thị biến động thành THẺ có viền ("Tên ứng viên") thay vì chuỗi
// thô ({candidate_name}), nhưng vẫn đọc/ghi ra plain text đúng định dạng backend.
//
// Vì sao không dùng <textarea>: textarea chỉ chứa văn bản thuần, không vẽ được ô
// viền quanh một đoạn. Cần contenteditable + <span contenteditable="false"> cho mỗi
// biến — nhờ contentEditable=false, cả thẻ bị xoá bằng MỘT lần Backspace và không
// thể sửa nửa vời thành "{candidate_nam}".
//
// Quy ước quan trọng: CHỈ biến có trong `variables` mới thành thẻ. Biến gõ sai vẫn
// nằm dạng chữ thường -> "không có ô viền nghĩa là không phải biến thật", HR nhìn là
// biết ngay mà không cần đọc cảnh báo.
// ---------------------------------------------------------------------------

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react'
import { sanitizeHtml, parseInert, cloneInert } from '../utils/sanitizeHtml.js'

// Tailwind quét class dưới dạng chuỗi trong file nguồn, nên hằng số này vẫn được
// biên dịch dù chỉ gán qua JS (không nằm trong JSX) — đã kiểm bằng computed style.
//
// KHÔNG đặt font ở đây: thẻ cố tình thừa hưởng font của ô chứa nó để nằm cùng một
// mạch chữ với phần văn bản xung quanh. (`font-sans` từng có ở đây nhưng vô tác dụng:
// dự án không khai báo --font-sans trong @theme của index.css.)
// KHÔNG có margin ngang: khoảng trắng phải do chính văn bản mẫu quyết định. Thêm
// mx vào đây thì "Chào {candidate_name}," hiện ra thành "Chào [Tên ứng viên] ," —
// dấu phẩy bị đẩy rời ra trong khi mail thật không có dấu cách ở đó.
const PILL_CLASS =
  'inline-flex items-center rounded-md border border-indigo-200 bg-indigo-50 px-1.5 py-px align-baseline text-[12px] font-semibold text-indigo-700'

// Ảnh chèn giữa bài: chặn tràn khung soạn thảo. Không đặt cứng chiều rộng — ảnh giữ
// đúng tỉ lệ gốc, giống cách Gmail hiển thị.
const IMAGE_CLASS = 'my-1 block h-auto max-w-full rounded'

const TOKEN_SPLIT = /(\{\w+\})/
const BLOCK_TAGS = new Set(['DIV', 'P', 'LI'])

// Trình duyệt chèn ký tự này để giữ chỗ cho con trỏ; không được lọt ra ngoài text.
const ZWSP = '​'

function makePill(token, label) {
  const el = document.createElement('span')
  el.dataset.token = token
  el.contentEditable = 'false'
  // Thẻ nằm trong vùng editable nên trình duyệt cho kéo nó đi. Kéo như vậy sẽ chèn
  // NHÃN ("Tên ứng viên") dạng chữ thường vào chỗ mới rồi xoá thẻ cũ -> mất biến.
  el.draggable = false
  el.title = `Biến động: ${token}`
  el.textContent = label
  el.className = PILL_CLASS
  return el
}

// DOM -> plain text để gửi backend.
function serializeNode(node, atStart) {
  if (node.nodeType === Node.TEXT_NODE) return node.data.replaceAll(ZWSP, '')
  if (node.nodeType !== Node.ELEMENT_NODE) return ''

  if (node.dataset?.token) return node.dataset.token
  if (node.tagName === 'BR') {
    // <br> cuối cùng thường là ký tự đệm trình duyệt tự thêm, không phải dòng mới
    // do người dùng gõ -> tính vào sẽ sinh ra một '\n' rác ở cuối mỗi lần lưu.
    return node.nextSibling ? '\n' : ''
  }

  let inner = ''
  for (const child of node.childNodes) inner += serializeNode(child, atStart && !inner)
  // Bấm Enter trong contenteditable: Chrome bọc dòng mới vào <div>.
  if (BLOCK_TAGS.has(node.tagName) && !atStart) return '\n' + inner
  return inner
}

function serialize(root) {
  let out = ''
  for (const child of root.childNodes) out += serializeNode(child, out === '')
  return out
}

// ---------------------------------------------------------------------------
// Chế độ HTML (richText): giữ định dạng in đậm/nghiêng/danh sách + ảnh chèn giữa bài
// ---------------------------------------------------------------------------

function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

// DOM -> HTML để lưu.
//
// Làm trên một BẢN SAO rồi đọc innerHTML, thay vì tự dựng chuỗi HTML bằng tay: dựng
// tay phải tự lo escape, thuộc tính, thẻ tự đóng — sai một chỗ là hỏng cả nội dung.
// Bản sao cho phép thay thẳng node rồi để trình duyệt tự sinh HTML đúng chuẩn.
function serializeHtml(root) {
  // cloneInert, KHÔNG root.cloneNode: bản sao phải nằm ngoài tài liệu đang sống,
  // nếu không thao tác đặt src="cid:..." ngay dưới đây sẽ khiến trình duyệt đi tải
  // và bắn ERR_UNKNOWN_URL_SCHEME sau mỗi phím gõ (xem chú thích ở sanitizeHtml.js).
  const clone = cloneInert(root)

  // Thẻ biến -> lại thành chữ "{token}" để backend thay bằng dữ liệu thật.
  for (const pill of clone.querySelectorAll('[data-token]')) {
    pill.replaceWith(document.createTextNode(pill.dataset.token))
  }

  // Ảnh: src đang là blob: (chỉ sống trong phiên làm việc này) -> đổi về cid: là thứ
  // mail hiểu được. Lưu blob URL vào DB thì mail gửi đi có ảnh hỏng vĩnh viễn.
  for (const img of clone.querySelectorAll('img[data-cid]')) {
    img.setAttribute('src', `cid:${img.dataset.cid}`)
    img.removeAttribute('data-cid')
  }

  // Ký tự đệm giữ chỗ con trỏ và cờ contenteditable là chuyện của trình soạn thảo,
  // không được đi vào mail.
  for (const el of clone.querySelectorAll('[contenteditable]')) {
    el.removeAttribute('contenteditable')
  }
  for (const el of clone.querySelectorAll('[draggable]')) {
    el.removeAttribute('draggable')
  }

  const html = clone.innerHTML.replaceAll(ZWSP, '')
  return sanitizeHtml(html)
}

// HTML đã lưu -> DOM để soạn tiếp.
// `resolveCid` đổi "cid:att-xxx" thành URL trình duyệt tải được (blob:), vì thẻ <img>
// không hiểu giao thức cid:.
function buildHtmlFragment(html, labels, resolveCid) {
  // Dựng trong tài liệu trơ trước: HTML lưu trong DB chứa src="cid:...", gán vào một
  // node của tài liệu đang sống là trình duyệt đi tải ngay và báo lỗi scheme lạ. Chỉ
  // sau khi đã đổi hết cid: sang blob: mới đưa node về tài liệu thật.
  const holder = parseInert(sanitizeHtml(html || ''))

  for (const img of holder.querySelectorAll('img')) {
    const src = img.getAttribute('src') || ''
    if (!src.startsWith('cid:')) continue
    const cid = src.slice(4)
    img.dataset.cid = cid
    const url = resolveCid?.(cid)
    if (url) img.setAttribute('src', url)
    else {
      // Chưa tải được ảnh (file đã bị xoá, hoặc blob chưa kịp dựng): bỏ src để trình
      // duyệt hiện ô ảnh vỡ kèm alt, chứ KHÔNG giữ "cid:..." — Chrome coi đó là URL
      // tương đối và bắn một request 404 về chính server frontend.
      img.removeAttribute('src')
      img.alt = img.alt || 'Ảnh đính kèm không tải được'
    }
    img.className = IMAGE_CLASS
  }

  // Biến trong HTML đang là chữ "{token}" -> đổi thành thẻ. Dùng lại đúng pillify của
  // chế độ chữ thường nên hai chế độ không lệch nhau về cách nhận biến.
  pillify(holder, labels)

  // Giờ mọi src đã là blob:/rỗng -> nhập về tài liệu thật để chèn vào ô soạn thảo.
  const live = document.importNode(holder, true)
  const out = document.createDocumentFragment()
  out.append(...live.childNodes)
  return out
}

// plain text -> DOM (thẻ cho biến đã biết, chữ thường cho phần còn lại).
function buildFragment(text, labels) {
  const frag = document.createDocumentFragment()
  for (const part of String(text ?? '').split(TOKEN_SPLIT)) {
    if (!part) continue
    if (labels[part]) frag.appendChild(makePill(part, labels[part]))
    else frag.appendChild(document.createTextNode(part))
  }
  return frag
}

// Mẫu cũ lưu dạng chữ thường; mở bằng trình soạn thảo HTML thì phải đổi sang HTML
// trước, nếu không mọi dấu xuống dòng biến mất (HTML gộp khoảng trắng).
export function plainTextToHtml(text) {
  return escapeHtml(text)
    .split('\n')
    .map((line) => (line.trim() === '' ? '<div><br></div>' : `<div>${line}</div>`))
    .join('')
}

// Biến chữ thô thành thẻ NGAY KHI nó xuất hiện, bất kể đến từ đâu: kéo-thả, dán,
// hay gõ tay đủ "{candidate_name}". Một đường xử lý cho cả ba.
// Trả về thẻ cuối vừa tạo (để đặt lại con trỏ), hoặc null nếu không đổi gì —
// không đổi gì thì KHÔNG được chạm vào con trỏ, kẻo đang gõ mà bị nhảy.
function pillify(root, labels) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const targets = []
  while (walker.nextNode()) {
    const node = walker.currentNode
    if (node.parentElement?.dataset?.token) continue // đã nằm trong thẻ
    if (node.data.includes('{') && TOKEN_SPLIT.test(node.data)) targets.push(node)
  }

  let lastPill = null
  for (const node of targets) {
    const parts = node.data.split(TOKEN_SPLIT)
    if (!parts.some((p) => labels[p])) continue // chỉ có biến lạ -> để nguyên chữ

    const frag = document.createDocumentFragment()
    for (const part of parts) {
      if (!part) continue
      if (labels[part]) {
        const pill = makePill(part, labels[part])
        frag.appendChild(pill)
        lastPill = pill
      } else {
        frag.appendChild(document.createTextNode(part))
      }
    }
    node.parentNode.replaceChild(frag, node)
  }
  return lastPill
}

// Đặt con trỏ ngay sau `node`. Nếu `node` là phần tử cuối cùng thì thêm một text node
// rỗng-nhìn-thấy-được (ZWSP) để con trỏ có chỗ đậu — không có nó, con trỏ đứng sau
// một thẻ contenteditable=false ở cuối ô rất khó bấm vào và gõ tiếp.
function placeCaretAfter(node) {
  if (!node.nextSibling) {
    node.parentNode.appendChild(document.createTextNode(ZWSP))
  }
  const range = document.createRange()
  range.setStartAfter(node)
  range.collapse(true)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(range)
}

const TokenEditor = forwardRef(function TokenEditor(
  {
    value,
    onChange,
    variables,
    singleLine = false,
    // richText=true: value là HTML, bật được in đậm/nghiêng/danh sách/ảnh.
    // richText=false: value là chữ thường (dùng cho Tiêu đề mail — giao thức không
    // cho phép HTML ở Subject).
    richText = false,
    // Đổi "att-xxx" thành URL hiển thị được. Bắt buộc khi richText và nội dung có ảnh.
    resolveCid,
    // Gọi mỗi khi vùng chọn trong ô thay đổi. Thanh công cụ cần tín hiệu này để tô
    // sáng đúng nút (đậm/nghiêng/danh sách) theo chỗ con trỏ đang đứng.
    //
    // Có prop riêng thay vì để bên ngoài truyền onKeyUp/onMouseUp qua ...rest: những
    // handler đó đã được dùng ở dưới cho saveRange, mà ...rest spread SAU nên sẽ ghi
    // đè, làm mất vùng chọn đã lưu — kéo theo hỏng cả chèn-tại-con-trỏ lẫn mọi lệnh
    // định dạng. Lỗi im lặng, không có thông báo nào.
    onSelectionChange,
    ariaLabel,
    className = '',
    ...rest
  },
  ref
) {
  const elRef = useRef(null)
  // Text mới nhất mà chính ô này phát ra. Dùng để phân biệt "value đổi vì người dùng
  // đang gõ ở đây" với "value đổi từ bên ngoài" (bấm Hoàn tác, tải xong từ server).
  const lastEmitted = useRef(null)
  // Vùng chọn cuối cùng bên trong ô: nút "chèn biến" nằm ngoài ô nên khi bấm, con trỏ
  // đã rời đi — phải nhớ lại mới chèn được vào đúng chỗ HR đang soạn.
  const savedRange = useRef(null)

  const labels = useMemo(
    () => Object.fromEntries(variables.map((v) => [v.token, v.label])),
    [variables]
  )

  // CHỈ vẽ lại DOM khi thay đổi đến từ bên ngoài.
  //
  // Vẽ lại theo từng ký tự (kiểu controlled input) sẽ thay toàn bộ node con sau mỗi
  // lần gõ và con trỏ bị nhảy về đầu ô — lỗi kinh điển của contenteditable trong
  // React. Vì vậy DOM là nguồn sự thật trong lúc gõ, `value` chỉ dùng để nạp lại.
  useEffect(() => {
    const el = elRef.current
    if (!el || value === lastEmitted.current) return
    el.replaceChildren(
      richText
        ? buildHtmlFragment(value, labels, resolveCid)
        : buildFragment(value, labels)
    )
    lastEmitted.current = value
  }, [value, labels, richText, resolveCid])

  function emit() {
    if (richText) {
      const html = serializeHtml(elRef.current)
      lastEmitted.current = html
      onChange(html)
      return
    }

    let text = serialize(elRef.current)
    // Ô một dòng: Enter đã bị chặn, nhưng dán nhiều dòng thì vẫn lọt \n vào.
    if (singleLine && text.includes('\n')) {
      text = text.replace(/\n+/g, ' ')
      elRef.current.replaceChildren(buildFragment(text, labels))
      const range = document.createRange()
      range.selectNodeContents(elRef.current)
      range.collapse(false)
      const sel = window.getSelection()
      sel.removeAllRanges()
      sel.addRange(range)
    }
    lastEmitted.current = text
    onChange(text)
  }

  function saveRange() {
    const sel = window.getSelection()
    if (!sel?.rangeCount) return
    const range = sel.getRangeAt(0)
    if (elRef.current?.contains(range.commonAncestorContainer)) {
      savedRange.current = range.cloneRange()
      onSelectionChange?.()
    }
  }

  function insertToken(token) {
    const el = elRef.current
    if (!el) return
    el.focus()

    let range = savedRange.current
    if (!range || !el.contains(range.commonAncestorContainer)) {
      range = document.createRange()
      range.selectNodeContents(el)
      range.collapse(false) // chưa từng đặt con trỏ -> chèn vào cuối
    }
    range.deleteContents()
    const pill = makePill(token, labels[token] || token)
    range.insertNode(pill)
    placeCaretAfter(pill)
    saveRange()
    emit()
  }

  // Đặt lại con trỏ về chỗ HR đang soạn. Mọi nút trên thanh công cụ đều nằm NGOÀI ô,
  // nên tới lúc chạy lệnh thì vùng chọn trong ô đã mất.
  function restoreSelection() {
    const el = elRef.current
    if (!el) return
    el.focus()
    const range = savedRange.current
    if (range && el.contains(range.commonAncestorContainer)) {
      const sel = window.getSelection()
      sel.removeAllRanges()
      sel.addRange(range)
    }
  }

  // Chạy lệnh định dạng của trình duyệt (in đậm, danh sách, màu chữ...).
  //
  // document.execCommand đã bị đánh dấu "deprecated" nhưng vẫn là cách duy nhất chạy
  // được ở mọi trình duyệt hiện nay mà không phải tự viết engine định dạng — và nó
  // giữ được cả undo/redo sẵn có của contenteditable, thứ mà tự thao tác DOM sẽ làm
  // mất. Trình soạn thảo của Gmail, Notion... cũng đi từ đây.
  function runCommand(command, argument = null) {
    restoreSelection()
    document.execCommand(command, false, argument)
    saveRange()
    emit()
  }

  // Chèn ảnh tại con trỏ. `cid` là khoá backend trả về, `url` là blob: để hiện ngay.
  function insertImage(cid, url, alt = '') {
    const el = elRef.current
    if (!el) return
    restoreSelection()

    const img = document.createElement('img')
    img.dataset.cid = cid
    img.src = url
    if (alt) img.alt = alt
    img.className = IMAGE_CLASS

    const sel = window.getSelection()
    if (sel?.rangeCount && el.contains(sel.getRangeAt(0).commonAncestorContainer)) {
      const range = sel.getRangeAt(0)
      range.deleteContents()
      range.insertNode(img)
      placeCaretAfter(img)
    } else {
      el.appendChild(img)
    }
    saveRange()
    emit()
  }

  // Bỏ mọi thẻ <img> trỏ tới một ảnh vừa bị xoá khỏi mẫu.
  //
  // Backend cố tình KHÔNG tự sửa nội dung khi xoá file (xem remove_attachment), nên
  // dọn ở đây là việc của giao diện — để lại thẻ ảnh trỏ vào file không còn thì HR
  // thấy ô ảnh vỡ mà không hiểu vì sao.
  function removeImagesByCid(cid) {
    const el = elRef.current
    if (!el) return
    const found = el.querySelectorAll(`img[data-cid="${cid}"]`)
    if (!found.length) return
    found.forEach((img) => img.remove())
    emit()
  }

  useImperativeHandle(ref, () => ({
    insertToken,
    runCommand,
    insertImage,
    removeImagesByCid,
    focus: () => elRef.current?.focus(),
    // Thanh công cụ cần biết đang ở trong đoạn in đậm/danh sách nào để tô sáng nút.
    queryState: (command) => {
      try {
        return document.queryCommandState(command)
      } catch {
        return false
      }
    },
  }))

  return (
    <div
      ref={elRef}
      // Ô tiêu đề dùng plaintext-only để dán từ Word/Gmail không mang theo cỡ chữ,
      // màu, thẻ HTML. Ô nội dung PHẢI là "true" — plaintext-only chặn luôn cả
      // execCommand('bold'), nên các nút định dạng sẽ im lặng không làm gì.
      // (Firefox cũ không hỗ trợ plaintext-only và tự hiểu thành "true"; serialize()
      // đã bỏ mọi thẻ lạ nên ô tiêu đề vẫn ra chữ thường.)
      contentEditable={richText ? 'true' : 'plaintext-only'}
      suppressContentEditableWarning
      role="textbox"
      aria-multiline={!singleLine}
      aria-label={ariaLabel}
      onInput={() => {
        const pill = pillify(elRef.current, labels)
        if (pill) placeCaretAfter(pill)
        emit()
        saveRange()
      }}
      onKeyDown={(e) => {
        if (singleLine && e.key === 'Enter') e.preventDefault()
        // Phím tắt quen tay của mọi trình soạn thảo. Trình duyệt vốn đã tự làm B/I/U
        // trong contenteditable, nhưng bắt lại ở đây để emit() chạy — không thì state
        // React không biết nội dung vừa đổi và nút "Lưu mẫu" vẫn mờ.
        if (richText && (e.ctrlKey || e.metaKey) && !e.altKey) {
          const key = e.key.toLowerCase()
          const command = key === 'b' ? 'bold' : key === 'i' ? 'italic' : key === 'u' ? 'underline' : null
          if (command) {
            e.preventDefault()
            runCommand(command)
          }
        }
      }}
      onKeyUp={saveRange}
      onMouseUp={saveRange}
      onBlur={saveRange}
      // whitespace-pre-wrap chỉ dành cho chế độ chữ thường (dấu \n mới thành dòng
      // mới). Ở chế độ HTML thì <div>/<br> lo việc đó, còn pre-wrap sẽ biến mỗi khoảng
      // trắng thừa trong HTML thành khoảng trắng thật trên màn hình.
      className={`break-words outline-none ${
        richText ? '[&_ol]:list-decimal [&_ul]:list-disc [&_li]:ml-5 [&_ol]:ml-1 [&_ul]:ml-1' : 'whitespace-pre-wrap'
      } ${className}`}
      {...rest}
    />
  )
})

export default TokenEditor
