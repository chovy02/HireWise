import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Mail,
  MailCheck,
  MailX,
  Save,
  RotateCcw,
  Loader2,
  Eye,
  AlertTriangle,
  Variable,
  GripVertical,
  MousePointerClick,
  Paperclip,
  FileText,
  X,
} from 'lucide-react'
import Topbar from '../components/Topbar.jsx'
import {
  Card,
  CardHeader,
  PageHeader,
  Badge,
  Toggle,
  PrimaryButton,
  SecondaryButton,
  StateRow,
} from '../components/ui.jsx'
import TokenEditor, { plainTextToHtml } from '../components/TokenEditor.jsx'
import RichTextToolbar from '../components/RichTextToolbar.jsx'
import { sanitizeHtml, parseInert } from '../utils/sanitizeHtml.js'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import {
  getEmailTemplates,
  upsertEmailTemplate,
  uploadEmailAttachment,
  deleteEmailAttachment,
  fetchEmailAttachmentBlob,
  TEMPLATE_TYPES,
  TEMPLATE_VARIABLES,
} from '../api/emailTemplates.js'

// Nhãn/màu cho hai loại mẫu. Dùng đúng cặp màu emerald/red như nút quyết định
// "Chọn / Từ chối" ở trang Danh sách rút gọn: HR nhìn màu là biết đang sửa mẫu nào.
const TEMPLATE_META = {
  accepted: {
    icon: MailCheck,
    title: 'Ứng viên được chọn',
    hint: 'Gửi khi HR đánh dấu ứng viên là “Chọn” trong danh sách rút gọn.',
    iconClass: 'bg-emerald-50 text-emerald-600',
    accent: 'text-emerald-600',
  },
  rejected: {
    icon: MailX,
    title: 'Ứng viên bị từ chối',
    hint: 'Gửi khi HR đánh dấu ứng viên là “Từ chối” trong danh sách rút gọn.',
    iconClass: 'bg-red-50 text-red-600',
    accent: 'text-red-600',
  },
}

// Dữ liệu mẫu cho khung xem trước. Không gọi API — chỉ để HR thấy mail thành hình
// trước khi lưu, vì biến động trong ô nhập ({candidate_name}…) đọc rất khó hình dung.
const PREVIEW_SAMPLE = {
  candidate_name: 'Nguyễn Thị Mai',
  jd_title: 'Kỹ sư Backend (Python)',
}

const KNOWN_TOKENS = new Set(TEMPLATE_VARIABLES.map((v) => v.token))

// Thay biến động giống backend (_fill_tokens): biến KHÔNG nhận ra thì GIỮ NGUYÊN chuỗi
// thay vì bỏ trống — để phần xem trước phản ánh đúng cái ứng viên sẽ nhận được.
function renderPreview(text, values) {
  return String(text ?? '').replace(/\{(\w+)\}/g, (whole, key) =>
    key in values ? values[key] : whole
  )
}

// Nội dung HTML có chữ thật hay chỉ là vỏ thẻ rỗng?
//
// Trình duyệt để lại "<div><br></div>" trong một ô contenteditable đã bị xoá sạch, nên
// kiểm tra bằng .trim() trên chuỗi HTML luôn cho ra "có nội dung" và một mẫu trắng
// vẫn lưu được. Phải bóc thẻ ra rồi mới xét — ảnh cũng tính là có nội dung.
function htmlHasContent(html) {
  const holder = parseInert(sanitizeHtml(html || ''))
  if (holder.querySelector('img')) return true
  return holder.textContent.replace(/​/g, '').trim().length > 0
}

// Đổi "cid:att-xxx" trong HTML thành blob: URL để khung xem trước hiện được ảnh.
//
// parseInert: dựng ngoài tài liệu đang sống để cái src="cid:..." trung gian không làm
// trình duyệt đi tải rồi báo ERR_UNKNOWN_URL_SCHEME.
function resolveCidsInHtml(html, cidUrls) {
  const holder = parseInert(sanitizeHtml(html || ''))
  for (const img of holder.querySelectorAll('img')) {
    const src = img.getAttribute('src') || ''
    if (!src.startsWith('cid:')) continue
    const url = cidUrls[src.slice(4)]
    if (url) img.setAttribute('src', url)
    else img.removeAttribute('src')
    img.className = 'my-1 block h-auto max-w-full rounded'
  }
  return holder.innerHTML
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

// Các biến HR gõ mà backend không biết. Backend không báo lỗi cho chúng — mail vẫn
// gửi, chỉ là ứng viên đọc được nguyên "{ten_ung_vien}" giữa câu. Nên phải cảnh báo
// ở đây, trước khi lưu.
function findUnknownTokens(...texts) {
  const found = new Set()
  for (const text of texts) {
    for (const m of String(text ?? '').matchAll(/\{\w+\}/g)) {
      if (!KNOWN_TOKENS.has(m[0])) found.add(m[0])
    }
  }
  return [...found]
}

// Thẻ biến kéo-thả được.
//
// CÁCH CHÈN DỰA HẲN VÀO TRÌNH DUYỆT: chỉ cần setData('text/plain') lúc bắt đầu kéo,
// còn việc chèn là hành vi mặc định của <input>/<textarea> — và nó chèn đúng ngay chỗ
// con trỏ chuột nhả ra, rồi phát sự kiện `input` nên onChange của React nhận được như
// người dùng tự gõ.
//
// VÌ VẬY TUYỆT ĐỐI KHÔNG preventDefault() ở dragover/drop trên các ô nhập, và cũng
// không tự tính vị trí chèn. Đã đo trên chính React của dự án: thả vào giữa ô thì
// biến vào đúng ký tự thứ 42 (chỗ nhả chuột), state React khớp DOM, onChange chạy 1
// lần. Ngược lại, cách "tự chèn tại el.selectionStart đọc trong dragover" cho ra 0 —
// selectionStart KHÔNG chạy theo vạch chèn khi kéo — nên biến rơi về đầu ô.
//
// role="button" + tabIndex thay cho <button>: vẫn bấm/Enter được để chèn tại con trỏ
// (đường dùng cho bàn phím và cảm ứng, nơi không kéo-thả được), nhưng chắc chắn kéo
// được ở mọi trình duyệt.
function VariableChip({ variable, onInsert, onDragStart, onDragEnd }) {
  return (
    <span
      role="button"
      tabIndex={0}
      draggable="true"
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', variable.token)
        e.dataTransfer.effectAllowed = 'copy'
        onDragStart?.()
      }}
      onDragEnd={() => onDragEnd?.()}
      onClick={() => onInsert?.()}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onInsert?.()
        }
      }}
      title={`${variable.token} — kéo vào ô, hoặc bấm để chèn tại con trỏ`}
      className="inline-flex cursor-grab select-none items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-2 py-1.5 text-xs font-semibold text-indigo-700 shadow-sm transition hover:border-indigo-400 hover:bg-indigo-100 focus:outline-none focus:ring-2 focus:ring-indigo-200 active:cursor-grabbing"
    >
      <GripVertical size={12} className="flex-shrink-0 text-indigo-400" />
      {/* Hiện NHÃN chứ không phải {token}: thẻ kéo ra phải trông giống hệt thẻ sẽ
          nằm trong ô, để HR biết trước mình đang chèn cái gì. Tên biến thật nằm ở
          tooltip cho ai cần tra. */}
      {variable.label}
    </span>
  )
}

// Nội dung mẫu về dạng HTML để mở bằng trình soạn thảo.
//
// Mẫu lưu trước tính năng này (và cả 2 mẫu mặc định của hệ thống) là chữ thường với
// dấu \n. Nạp thẳng vào ô HTML thì HTML gộp hết khoảng trắng và cả mail dồn thành một
// đoạn liền — nên phải đổi \n thành <div> trước.
function draftFromTemplate(t) {
  return {
    subject: t.subject,
    body_template:
      t.body_format === 'html' ? t.body_template : plainTextToHtml(t.body_template),
    // Mở bằng trình soạn thảo là từ nay lưu dưới dạng HTML. Không cố giữ lại 'text':
    // HR vừa bấm in đậm là nội dung đã không còn biểu diễn được bằng chữ thường.
    body_format: 'html',
    is_active: t.is_active,
  }
}

export default function EmailTemplates() {
  const toast = useToast()
  const { user } = useAuth()

  const [templates, setTemplates] = useState(null) // bản gốc từ server (để "Hoàn tác")
  const [drafts, setDrafts] = useState({}) // { accepted: {...}, rejected: {...} } đang sửa
  const [loadErr, setLoadErr] = useState('')
  const [savingType, setSavingType] = useState(null)

  // cid -> blob: URL cho ảnh chèn giữa bài. Giữ ở đây (cấp trang) chứ không trong từng
  // ô soạn thảo: khung xem trước cũng cần đúng bộ URL này.
  const [cidUrls, setCidUrls] = useState({})

  // Thu hồi các blob URL khi rời trang. Không gọi revokeObjectURL thì mỗi ảnh giữ
  // nguyên bộ nhớ cho tới khi đóng tab.
  const cidUrlsRef = useRef({})
  useEffect(() => {
    cidUrlsRef.current = cidUrls
  }, [cidUrls])
  useEffect(() => {
    return () => {
      for (const url of Object.values(cidUrlsRef.current)) URL.revokeObjectURL(url)
    }
  }, [])

  // Tải ảnh inline của một mẫu về dạng blob để hiển thị được.
  //
  // Không thể để <img src="/email-templates/.../content"> vì endpoint đó cần header
  // Authorization mà thẻ <img> không gửi được — cùng lý do trang xem CV phải tải PDF
  // qua fetch (xem apiFetchBlob).
  async function loadInlineImages(templatesByType) {
    const entries = []
    for (const [type, tpl] of Object.entries(templatesByType)) {
      for (const att of tpl.attachments || []) {
        if (!att.is_inline || !att.content_id) continue
        try {
          const blob = await fetchEmailAttachmentBlob(type, att.id)
          entries.push([att.content_id, URL.createObjectURL(blob)])
        } catch {
          // Ảnh lỗi thì bỏ qua: TokenEditor hiện ô ảnh vỡ kèm alt, phần còn lại của
          // mẫu vẫn soạn được bình thường.
        }
      }
    }
    if (entries.length) {
      setCidUrls((prev) => ({ ...prev, ...Object.fromEntries(entries) }))
    }
  }

  useEffect(() => {
    let cancelled = false
    getEmailTemplates()
      .then((data) => {
        if (cancelled) return
        // Backend cam kết trả đủ 2 mẫu, nhưng vẫn gom theo type thay vì tin vào thứ
        // tự mảng: đảo thứ tự ở backend là đủ để UI sửa nhầm mẫu.
        const byType = {}
        for (const t of data) byType[t.template_type] = t
        setTemplates(byType)
        setDrafts(
          Object.fromEntries(
            Object.entries(byType).map(([type, t]) => [type, draftFromTemplate(t)])
          )
        )
        loadInlineImages(byType)
      })
      .catch((e) => !cancelled && setLoadErr(e.message))
    return () => {
      cancelled = true
    }
  }, [])

  function updateDraft(type, patch) {
    setDrafts((prev) => ({ ...prev, [type]: { ...prev[type], ...patch } }))
  }

  async function handleSave(type) {
    const draft = drafts[type]
    // Kiểm tra trên phần CHỮ, không trên chuỗi HTML: một ô rỗng vẫn có thể chứa
    // "<div><br></div>" do trình duyệt tự thêm, nên .trim() trên HTML luôn khác rỗng
    // và nút Lưu sẽ chấp nhận một mẫu trắng.
    if (!draft.subject.trim() || !htmlHasContent(draft.body_template)) {
      toast('Tiêu đề và nội dung mail không được để trống.')
      return
    }
    setSavingType(type)
    try {
      const saved = await upsertEmailTemplate(type, draft)
      // Giữ lại attachments đang có: PUT chỉ trả về mẫu, và nếu ghi đè bằng mảng rỗng
      // thì danh sách file vừa gắn biến mất khỏi giao diện dù vẫn còn dưới DB.
      setTemplates((prev) => ({
        ...prev,
        [type]: { ...saved, attachments: saved.attachments ?? prev[type]?.attachments ?? [] },
      }))
      setDrafts((prev) => ({ ...prev, [type]: draftFromTemplate(saved) }))
      toast(`Đã lưu mẫu mail “${TEMPLATE_META[type].title}”.`)
    } catch (e) {
      toast(e.message || 'Không lưu được mẫu mail.')
    } finally {
      setSavingType(null)
    }
  }

  // Hoàn tác về bản ĐANG LƯU trên server (không phải bản mặc định hệ thống): HR sửa
  // dở rồi đổi ý thì lấy lại đúng thứ đang có hiệu lực.
  function handleRevert(type) {
    const src = templates?.[type]
    if (!src) return
    updateDraft(type, draftFromTemplate(src))
  }

  // Gắn file vào mẫu. inline=true -> ảnh chèn ngay tại con trỏ trong nội dung.
  async function handleUpload(type, file, { inline, editorRef }) {
    try {
      const att = await uploadEmailAttachment(type, file, inline)
      // Mẫu có thể vừa được backend tạo ra lúc này (_get_or_create_template), nên nạp
      // lại để `id`, `updated_at` và danh sách file khớp với DB.
      setTemplates((prev) => ({
        ...prev,
        [type]: {
          ...prev[type],
          attachments: [...(prev[type]?.attachments || []), att],
        },
      }))

      if (inline) {
        const url = URL.createObjectURL(file)
        setCidUrls((prev) => ({ ...prev, [att.content_id]: url }))
        editorRef?.current?.insertImage(att.content_id, url, file.name)
        toast(`Đã chèn ảnh “${file.name}” vào nội dung.`)
      } else {
        toast(`Đã đính kèm “${file.name}”.`)
      }
    } catch (e) {
      toast(e.message || 'Không tải được file lên.')
    }
  }

  async function handleDeleteAttachment(type, attachment, editorRef) {
    try {
      await deleteEmailAttachment(type, attachment.id)
      setTemplates((prev) => ({
        ...prev,
        [type]: {
          ...prev[type],
          attachments: (prev[type]?.attachments || []).filter((a) => a.id !== attachment.id),
        },
      }))
      // Ảnh inline: bỏ luôn thẻ <img> khỏi nội dung, kẻo còn lại một ô ảnh vỡ trỏ tới
      // file đã xoá (backend cố tình không tự sửa nội dung — xem remove_attachment).
      if (attachment.is_inline && attachment.content_id) {
        editorRef?.current?.removeImagesByCid(attachment.content_id)
        setCidUrls((prev) => {
          const next = { ...prev }
          if (next[attachment.content_id]) URL.revokeObjectURL(next[attachment.content_id])
          delete next[attachment.content_id]
          return next
        })
      }
      toast(`Đã xoá “${attachment.filename}”.`)
    } catch (e) {
      toast(e.message || 'Không xoá được file.')
    }
  }

  return (
    <>
      <Topbar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        <PageHeader
          icon={Mail}
          title="Mẫu email thông báo kết quả"
          subtitle="Tự soạn nội dung mail gửi ứng viên sau khi chốt kết quả. Tắt một mẫu thì hệ thống dùng lại nội dung mặc định."
        />

        {/* Bảng biến động: đặt TRÊN các ô nhập vì HR cần biết gõ được gì trước khi gõ. */}
        

        {templates === null && !loadErr && (
          <Card className="mt-5">
            <StateRow>Đang tải mẫu email…</StateRow>
          </Card>
        )}
        {loadErr && (
          <Card className="mt-5">
            <StateRow tone="error">Lỗi tải mẫu email: {loadErr}</StateRow>
          </Card>
        )}

        {templates && (
          <div className="mt-5 space-y-5">
            {TEMPLATE_TYPES.filter((type) => drafts[type]).map((type) => (
              <TemplateEditor
                key={type}
                type={type}
                draft={drafts[type]}
                saved={templates[type]}
                hrName={user?.name || 'HR Staff'}
                saving={savingType === type}
                cidUrls={cidUrls}
                onChange={(patch) => updateDraft(type, patch)}
                onSave={() => handleSave(type)}
                onRevert={() => handleRevert(type)}
                onUpload={(file, opts) => handleUpload(type, file, opts)}
                onDeleteAttachment={(att, editorRef) =>
                  handleDeleteAttachment(type, att, editorRef)
                }
              />
            ))}
          </div>
        )}
      </main>
    </>
  )
}

// Danh sách file đính kèm của mẫu (KHÔNG gồm ảnh chèn giữa bài — ảnh đã hiện ngay
// trong nội dung, liệt kê lại chỉ gây tưởng là gửi hai lần).
function AttachmentList({ attachments, onDelete }) {
  const files = attachments.filter((a) => !a.is_inline)
  const inlineCount = attachments.length - files.length

  if (!files.length && !inlineCount) return null

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-3">
      <div className="flex items-center gap-2">
        <Paperclip size={14} className="text-slate-500" />
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          File đính kèm
        </span>
        {inlineCount > 0 && (
          <span className="text-xs text-slate-400">
            (+{inlineCount} ảnh trong nội dung)
          </span>
        )}
      </div>

      {files.length === 0 ? (
        <p className="mt-1.5 text-xs text-slate-400">
          Chưa có file nào. Dùng nút <Paperclip size={11} className="inline" /> trên
          thanh công cụ để đính kèm.
        </p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {files.map((att) => (
            <li
              key={att.id}
              className="flex items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5"
            >
              <FileText size={14} className="flex-shrink-0 text-slate-400" />
              <span className="min-w-0 flex-1 truncate text-sm text-slate-700">
                {att.filename}
              </span>
              <span className="flex-shrink-0 text-xs text-slate-400">
                {formatBytes(att.size_bytes)}
              </span>
              <button
                type="button"
                onClick={() => onDelete(att)}
                title={`Xoá ${att.filename}`}
                aria-label={`Xoá ${att.filename}`}
                className="flex-shrink-0 rounded p-1 text-slate-400 transition hover:bg-red-50 hover:text-red-600"
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-slate-400">
        Mọi ứng viên nhận kết quả này sẽ nhận cùng bộ file.
      </p>
    </div>
  )
}

// Khung soạn một mẫu: tiêu đề + nội dung + công tắc bật/tắt + xem trước.
function TemplateEditor({
  type,
  draft,
  saved,
  hrName,
  saving,
  cidUrls,
  onChange,
  onSave,
  onRevert,
  onUpload,
  onDeleteAttachment,
}) {
  const meta = TEMPLATE_META[type]
  const [showPreview, setShowPreview] = useState(false)

  // Buộc thanh công cụ đọc lại queryCommandState sau mỗi lần vùng chọn đổi, để nút
  // in đậm sáng/tắt theo đúng chỗ con trỏ đang đứng.
  const [selectionTick, setSelectionTick] = useState(0)
  const bumpSelection = () => setSelectionTick((n) => n + 1)

  const [uploading, setUploading] = useState(false)
  // Hai input file ẩn: một cho ảnh chèn giữa bài, một cho file đính kèm. Dùng input
  // thật (không phải API) để hộp thoại chọn file là của hệ điều hành, và `accept`
  // lọc sẵn đúng loại.
  const imageInputRef = useRef(null)
  const fileInputRef = useRef(null)

  async function pickAndUpload(input, inline) {
    const file = input.files?.[0]
    // Reset NGAY: không xoá value thì chọn lại đúng file vừa rồi sẽ không phát sự kiện
    // change (giá trị không đổi) và HR tưởng nút bị hỏng.
    input.value = ''
    if (!file) return
    setUploading(true)
    try {
      await onUpload(file, { inline, editorRef: bodyRef })
    } finally {
      setUploading(false)
    }
  }

  // Ô nhập được focus lần cuối — đường BẤM để chèn cần biết chèn vào tiêu đề hay
  // nội dung. (Đường KÉO THẢ không cần: thả ở đâu thì vào đó.)
  const subjectRef = useRef(null)
  const bodyRef = useRef(null)
  const [lastField, setLastField] = useState('body_template')

  // Đang kéo một biến -> làm nổi cả hai ô để HR thấy chỗ thả được; `dragOverField`
  // là ô con trỏ đang đi vào.
  const [dragging, setDragging] = useState(false)
  const [dragOverField, setDragOverField] = useState(null)

  // Props chung cho hai ô nhập.
  //
  // KHÔNG có onDragOver, và các handler dưới đây TUYỆT ĐỐI KHÔNG preventDefault():
  // chỉ đổi trạng thái hiển thị. Hủy dragover/drop là chặn luôn việc chèn mặc định
  // của trình duyệt — mà đó chính là thứ đặt biến vào đúng vị trí nhả chuột.
  //
  // Đã đo: đổi state (kéo theo render lại + đổi className) ngay trong lúc kéo và cả
  // trong drop đều KHÔNG ảnh hưởng — biến vẫn vào đúng ký tự thứ 42 khi thả giữa ô,
  // state React vẫn khớp DOM.
  //
  // onDrop phải có: `dragEnd` một mình không đủ để tắt highlight. Có lần trình duyệt
  // phát thêm `dragenter` SAU `dragend`, làm ô sáng vĩnh viễn sau khi đã thả xong.
  function dropZoneProps(field) {
    return {
      onFocus: () => setLastField(field),
      onDragEnter: () => setDragOverField(field),
      onDragLeave: () =>
        setDragOverField((current) => (current === field ? null : current)),
      onDrop: () => {
        setDragging(false)
        setDragOverField(null)
      },
    }
  }

  // Viền/nền báo chỗ thả. Ô đang được trỏ tới đậm hơn hai ô còn lại.
  function dropZoneClass(field) {
    if (dragOverField === field) return 'border-indigo-500 bg-indigo-50/60 ring-2 ring-indigo-200'
    if (dragging) return 'border-indigo-300 border-dashed bg-indigo-50/20'
    return 'border-slate-200'
  }

  // Mẫu chưa từng lưu (id === null) là bản mặc định của hệ thống: KHÔNG có gì để
  // hoàn tác về, và HR nên biết mình đang xem bản gốc chứ không phải bản của mình.
  const isDefault = !saved?.id

  // So với bản đã QUY VỀ HTML, không so thẳng với bản trên server.
  //
  // Mẫu cũ lưu dạng chữ thường được đổi sang HTML ngay khi mở trang, nên so trực tiếp
  // thì chuỗi luôn khác nhau: vừa vào trang đã hiện "Chưa lưu" và nút Lưu sáng lên dù
  // HR chưa gõ gì. Việc đổi định dạng để hiển thị KHÔNG phải là một thay đổi của HR.
  const baseline = useMemo(() => (saved ? draftFromTemplate(saved) : null), [saved])

  const dirty =
    !baseline ||
    draft.subject !== baseline.subject ||
    draft.body_template !== baseline.body_template ||
    draft.is_active !== baseline.is_active

  const unknownTokens = useMemo(
    () => findUnknownTokens(draft.subject, draft.body_template),
    [draft.subject, draft.body_template]
  )

  const previewValues = { ...PREVIEW_SAMPLE, hr_name: hrName }

  // Ảnh chèn giữa bài đã nằm trong nội dung rồi; danh sách "file đính kèm" chỉ hiện
  // loại còn lại, đúng như Gmail.
  const regularAttachments = (saved?.attachments || []).filter((a) => !a.is_inline)

  // Đường BẤM để chèn: đẩy xuống ô vừa dùng. TokenEditor tự lo chèn đúng chỗ con trỏ
  // (nó nhớ vùng chọn cuối cùng, vì bấm ra ngoài ô là con trỏ đã rời đi).
  function insertToken(token) {
    const editor = lastField === 'subject' ? subjectRef.current : bodyRef.current
    editor?.insertToken(token)
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-6 py-4">
        <div className="flex items-center gap-3">
          <div
            className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg ${meta.iconClass}`}
          >
            <meta.icon size={19} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-800">{meta.title}</h2>
              {isDefault && (
                <Badge variant="neutral" upper={false}>
                  Mặc định hệ thống
                </Badge>
              )}
              {!draft.is_active && (
                <Badge variant="warning" upper={false}>
                  Đang tắt
                </Badge>
              )}
              {dirty && (
                <Badge variant="info" upper={false}>
                  Chưa lưu
                </Badge>
              )}
            </div>
            <p className="mt-0.5 text-xs text-slate-500">{meta.hint}</p>
          </div>
        </div>

        <label className="flex items-center gap-2.5 text-sm">
          <Toggle
            checked={draft.is_active}
            onChange={(v) => onChange({ is_active: v })}
          />
          <span className="font-medium text-slate-600">
            {draft.is_active ? 'Dùng mẫu này' : 'Dùng mẫu mặc định'}
          </span>
        </label>
      </div>

      <div className="space-y-4 p-6">
        {/* Khay biến: một hàng duy nhất phục vụ CẢ hai ô, đặt trên cùng vì HR cần
            thấy có thứ để kéo trước khi bắt đầu soạn. */}
        <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Kéo biến vào ô
            </span>
            <div className="flex flex-wrap gap-1.5">
              {TEMPLATE_VARIABLES.map((v) => (
                <VariableChip
                  key={v.token}
                  variable={v}
                  onInsert={() => insertToken(v.token)}
                  onDragStart={() => setDragging(true)}
                  onDragEnd={() => {
                    setDragging(false)
                    setDragOverField(null)
                  }}
                />
              ))}
            </div>
          </div>
          <p className="mt-2 flex items-start gap-1.5 text-xs text-slate-500">
            <MousePointerClick size={13} className="mt-0.5 flex-shrink-0" />
            Thả vào đúng chỗ cần chèn — biến vào ngay vị trí con trỏ chuột. Hoặc bấm
            vào thẻ để chèn tại con trỏ văn bản. Xoá một biến chỉ cần một lần Backspace.
          </p>
        </div>

        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Tiêu đề mail
          </label>
          <TokenEditor
            ref={subjectRef}
            value={draft.subject}
            onChange={(text) => onChange({ subject: text })}
            variables={TEMPLATE_VARIABLES}
            singleLine
            ariaLabel="Tiêu đề mail"
            {...dropZoneProps('subject')}
            className={`mt-1.5 w-full rounded-lg border px-3.5 py-2.5 text-sm text-slate-800 transition-colors focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 ${dropZoneClass(
              'subject'
            )}`}
          />
        </div>

        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Nội dung mail
          </label>

          <div className="mt-1.5">
            <RichTextToolbar
              editorRef={bodyRef}
              selectionTick={selectionTick}
              uploading={uploading}
              onInsertImage={() => imageInputRef.current?.click()}
              onAttachFile={() => fileInputRef.current?.click()}
            />
            {/* Bỏ font-mono của <textarea> cũ: chữ đều nhau chỉ có ích khi phải đọc
                "{candidate_name}" thô, giờ biến đã thành thẻ nên chữ thường dễ đọc hơn
                và giống mail thật hơn. */}
            <TokenEditor
              ref={bodyRef}
              value={draft.body_template}
              onChange={(html) => onChange({ body_template: html })}
              variables={TEMPLATE_VARIABLES}
              richText
              resolveCid={(cid) => cidUrls[cid]}
              ariaLabel="Nội dung mail"
              onSelectionChange={bumpSelection}
              {...dropZoneProps('body_template')}
              className={`max-h-[460px] min-h-[220px] w-full overflow-y-auto rounded-b-lg border px-3.5 py-2.5 text-sm leading-relaxed text-slate-800 transition-colors focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 ${dropZoneClass(
                'body_template'
              )}`}
            />
          </div>

          {/* Input file ẩn — nút thật nằm trên thanh công cụ. */}
          <input
            ref={imageInputRef}
            type="file"
            accept="image/png,image/jpeg,image/gif,image/webp"
            className="hidden"
            onChange={(e) => pickAndUpload(e.target, true)}
          />
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={(e) => pickAndUpload(e.target, false)}
          />
        </div>

        <AttachmentList
          attachments={saved?.attachments || []}
          onDelete={(att) => onDeleteAttachment(att, bodyRef)}
        />

        {unknownTokens.length > 0 && (
          <div className="flex items-start gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm text-amber-800">
            <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
            <p>
              Không nhận ra biến{' '}
              <span className="font-mono font-semibold">
                {unknownTokens.join(', ')}
              </span>{' '}
              (vì thế nó không có khung). Hệ thống sẽ gửi nguyên văn phần này cho ứng
              viên — xoá đi rồi kéo thẻ đúng từ khay vào thay thế.
            </p>
          </div>
        )}

        {/* Xem trước: mặc định đóng để hai khung soạn không đẩy nhau xuống quá dài. */}
        <div>
          <button
            type="button"
            onClick={() => setShowPreview((v) => !v)}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-700"
            aria-expanded={showPreview}
          >
            <Eye size={15} />
            {showPreview ? 'Ẩn xem trước' : 'Xem trước với dữ liệu mẫu'}
          </button>

          {showPreview && (
            <div className="mt-3 overflow-hidden rounded-xl border border-slate-200">
              <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs text-slate-500">
                  Tới:{' '}
                  <span className="font-medium text-slate-700">
                    {PREVIEW_SAMPLE.candidate_name}
                  </span>
                </p>
                <p className="mt-1 text-sm font-semibold text-slate-900">
                  {renderPreview(draft.subject, previewValues)}
                </p>
              </div>
              {/* Xem trước phải render HTML THẬT để HR thấy đúng cái ứng viên nhận
                  được — in ra dạng chữ thì mọi định dạng và ảnh đều vô hình.
                  dangerouslySetInnerHTML ở đây an toàn vì chuỗi đã đi qua
                  sanitizeHtml (danh sách thẻ/thuộc tính cho phép) bên trong
                  resolveCidsInHtml. */}
              <div
                className="px-4 py-4 text-sm leading-relaxed text-slate-700 [&_a]:text-indigo-600 [&_a]:underline [&_li]:ml-5 [&_ol]:ml-1 [&_ol]:list-decimal [&_ul]:ml-1 [&_ul]:list-disc"
                dangerouslySetInnerHTML={{
                  __html: resolveCidsInHtml(
                    renderPreview(draft.body_template, previewValues),
                    cidUrls
                  ),
                }}
              />
              {regularAttachments.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 bg-slate-50 px-4 py-3">
                  <span className="text-xs text-slate-500">
                    {regularAttachments.length} file đính kèm:
                  </span>
                  {regularAttachments.map((att) => (
                    <span
                      key={att.id}
                      className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600"
                    >
                      <Paperclip size={11} />
                      {att.filename}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2.5 border-t border-slate-100 pt-4">
          {saved?.updated_at && (
            <span className="mr-auto text-xs text-slate-400">
              Cập nhật lần cuối: {new Date(saved.updated_at).toLocaleString('vi-VN')}
            </span>
          )}
          <SecondaryButton
            onClick={onRevert}
            disabled={!dirty || isDefault || saving}
            className="disabled:cursor-not-allowed disabled:opacity-60"
            title={
              isDefault
                ? 'Mẫu này chưa từng được lưu — chưa có bản cũ để hoàn tác'
                : 'Hoàn tác về bản đang lưu'
            }
          >
            <RotateCcw size={15} /> Hoàn tác
          </SecondaryButton>
          <PrimaryButton onClick={onSave} disabled={saving || !dirty}>
            {saving ? (
              <>
                <Loader2 size={16} className="animate-spin" /> Đang lưu…
              </>
            ) : (
              <>
                <Save size={16} /> Lưu mẫu
              </>
            )}
          </PrimaryButton>
        </div>
      </div>
    </Card>
  )
}
