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
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import {
  getEmailTemplates,
  upsertEmailTemplate,
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

// Thay biến động giống backend (SafeDict): biến KHÔNG nhận ra thì GIỮ NGUYÊN chuỗi
// thay vì bỏ trống — để phần xem trước phản ánh đúng cái ứng viên sẽ nhận được.
function renderPreview(text, values) {
  return String(text ?? '').replace(/\{(\w+)\}/g, (whole, key) =>
    key in values ? values[key] : whole
  )
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

export default function EmailTemplates() {
  const toast = useToast()
  const { user } = useAuth()

  const [templates, setTemplates] = useState(null) // bản gốc từ server (để "Hoàn tác")
  const [drafts, setDrafts] = useState({}) // { accepted: {...}, rejected: {...} } đang sửa
  const [loadErr, setLoadErr] = useState('')
  const [savingType, setSavingType] = useState(null)

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
            Object.entries(byType).map(([type, t]) => [
              type,
              {
                subject: t.subject,
                body_template: t.body_template,
                is_active: t.is_active,
              },
            ])
          )
        )
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
    if (!draft.subject.trim() || !draft.body_template.trim()) {
      toast('Tiêu đề và nội dung mail không được để trống.')
      return
    }
    setSavingType(type)
    try {
      const saved = await upsertEmailTemplate(type, draft)
      setTemplates((prev) => ({ ...prev, [type]: saved }))
      setDrafts((prev) => ({
        ...prev,
        [type]: {
          subject: saved.subject,
          body_template: saved.body_template,
          is_active: saved.is_active,
        },
      }))
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
    updateDraft(type, {
      subject: src.subject,
      body_template: src.body_template,
      is_active: src.is_active,
    })
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
        <Card className="mt-6 p-5">
          <div className="flex items-center gap-2">
            <Variable size={16} className="text-indigo-600" />
            <h2 className="text-sm font-semibold text-slate-800">
              Biến động dùng được trong mẫu
            </h2>
          </div>
          <p className="mt-1.5 text-sm text-slate-500">
            Bấm vào một biến để chèn vào ô đang nhập. Hệ thống thay chúng bằng dữ
            liệu thật lúc gửi; biến viết sai tên sẽ hiện nguyên văn trong mail của
            ứng viên.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {TEMPLATE_VARIABLES.map((v) => (
              <span
                key={v.token}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs"
              >
                <code className="font-mono font-semibold text-indigo-700">
                  {v.token}
                </code>
                <span className="text-slate-500">{v.label}</span>
              </span>
            ))}
          </div>
        </Card>

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
                onChange={(patch) => updateDraft(type, patch)}
                onSave={() => handleSave(type)}
                onRevert={() => handleRevert(type)}
              />
            ))}
          </div>
        )}
      </main>
    </>
  )
}

// Khung soạn một mẫu: tiêu đề + nội dung + công tắc bật/tắt + xem trước.
function TemplateEditor({
  type,
  draft,
  saved,
  hrName,
  saving,
  onChange,
  onSave,
  onRevert,
}) {
  const meta = TEMPLATE_META[type]
  const [showPreview, setShowPreview] = useState(false)

  // Ô nhập được focus lần cuối — nút chèn biến cần biết chèn vào tiêu đề hay nội dung.
  const subjectRef = useRef(null)
  const bodyRef = useRef(null)
  const [lastField, setLastField] = useState('body_template')

  // Mẫu chưa từng lưu (id === null) là bản mặc định của hệ thống: KHÔNG có gì để
  // hoàn tác về, và HR nên biết mình đang xem bản gốc chứ không phải bản của mình.
  const isDefault = !saved?.id

  const dirty =
    draft.subject !== saved?.subject ||
    draft.body_template !== saved?.body_template ||
    draft.is_active !== saved?.is_active

  const unknownTokens = useMemo(
    () => findUnknownTokens(draft.subject, draft.body_template),
    [draft.subject, draft.body_template]
  )

  const previewValues = { ...PREVIEW_SAMPLE, hr_name: hrName }

  // Chèn biến tại đúng con trỏ của ô vừa dùng, rồi trả focus về đó — chèn vào cuối
  // chuỗi thì HR phải tự cắt dán lại, mất hẳn ý nghĩa của cái nút.
  function insertToken(token) {
    const field = lastField
    const el = field === 'subject' ? subjectRef.current : bodyRef.current
    const current = draft[field] ?? ''
    if (!el) {
      onChange({ [field]: current + token })
      return
    }
    const start = el.selectionStart ?? current.length
    const end = el.selectionEnd ?? current.length
    onChange({ [field]: current.slice(0, start) + token + current.slice(end) })
    // Đặt lại con trỏ sau khi React vẽ lại giá trị mới.
    requestAnimationFrame(() => {
      el.focus()
      const pos = start + token.length
      el.setSelectionRange(pos, pos)
    })
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
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Tiêu đề mail
          </label>
          <input
            ref={subjectRef}
            value={draft.subject}
            onFocus={() => setLastField('subject')}
            onChange={(e) => onChange({ subject: e.target.value })}
            className="mt-1.5 w-full rounded-lg border border-slate-200 px-3.5 py-2.5 text-sm text-slate-800 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
          />
        </div>

        <div>
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Nội dung mail
            </label>
            <div className="flex flex-wrap gap-1.5">
              {TEMPLATE_VARIABLES.map((v) => (
                <button
                  key={v.token}
                  type="button"
                  onClick={() => insertToken(v.token)}
                  title={`Chèn ${v.label}`}
                  className="rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[11px] font-semibold text-indigo-700 transition hover:border-indigo-300 hover:bg-indigo-50"
                >
                  {v.token}
                </button>
              ))}
            </div>
          </div>
          <textarea
            ref={bodyRef}
            value={draft.body_template}
            onFocus={() => setLastField('body_template')}
            onChange={(e) => onChange({ body_template: e.target.value })}
            rows={10}
            className="mt-1.5 w-full resize-y rounded-lg border border-slate-200 px-3.5 py-2.5 font-mono text-[13px] leading-relaxed text-slate-800 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
          />
        </div>

        {unknownTokens.length > 0 && (
          <div className="flex items-start gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm text-amber-800">
            <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
            <p>
              Không nhận ra biến{' '}
              <span className="font-mono font-semibold">
                {unknownTokens.join(', ')}
              </span>
              . Hệ thống sẽ gửi nguyên văn phần này cho ứng viên — kiểm tra lại tên
              biến trong danh sách ở trên.
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
              <pre className="whitespace-pre-wrap px-4 py-4 text-sm leading-relaxed text-slate-700">
                {renderPreview(draft.body_template, previewValues)}
              </pre>
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
