// ---------------------------------------------------------------------------
// Thanh công cụ định dạng cho ô soạn nội dung mail (kiểu Gmail).
//
// Mọi nút đều preventDefault ở onMouseDown. Đây là điểm sống-còn: bấm chuột bình
// thường sẽ chuyển focus sang nút và LÀM MẤT vùng chọn trong ô soạn thảo, nên lệnh
// in đậm không biết phải áp lên đoạn nào. Chặn hành vi mặc định của mousedown thì
// focus không rời ô, vùng chọn còn nguyên.
// ---------------------------------------------------------------------------

import { useState } from 'react'
import {
  Bold,
  Italic,
  Underline,
  Strikethrough,
  List,
  ListOrdered,
  Link2,
  Link2Off,
  RemoveFormatting,
  Image as ImageIcon,
  Paperclip,
  Loader2,
  Palette,
} from 'lucide-react'

// Các nút bật/tắt trạng thái. `state` là tên lệnh dùng để hỏi queryCommandState —
// nhờ nó nút tự sáng lên khi con trỏ đang nằm trong đoạn đã in đậm.
const TOGGLES = [
  { command: 'bold', icon: Bold, label: 'In đậm', hint: 'Ctrl+B' },
  { command: 'italic', icon: Italic, label: 'In nghiêng', hint: 'Ctrl+I' },
  { command: 'underline', icon: Underline, label: 'Gạch chân', hint: 'Ctrl+U' },
  { command: 'strikeThrough', icon: Strikethrough, label: 'Gạch ngang' },
  { command: 'insertUnorderedList', icon: List, label: 'Danh sách dấu đầu dòng' },
  { command: 'insertOrderedList', icon: ListOrdered, label: 'Danh sách số' },
]

// Bảng màu gọn thay cho <input type="color">: HR cần vài màu dùng được trong mail,
// không cần cả dải màu — và mail nhiều màu tự chọn thường trông rất tệ.
const COLORS = [
  { value: '#0f172a', label: 'Đen' },
  { value: '#475569', label: 'Xám' },
  { value: '#4338ca', label: 'Xanh tím' },
  { value: '#0369a1', label: 'Xanh dương' },
  { value: '#047857', label: 'Xanh lá' },
  { value: '#b45309', label: 'Cam' },
  { value: '#b91c1c', label: 'Đỏ' },
]

function ToolButton({ icon: Icon, label, hint, active, disabled, onRun }) {
  return (
    <button
      type="button"
      // Xem chú thích đầu file: đây là lý do vùng chọn không bị mất khi bấm nút.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onRun}
      disabled={disabled}
      title={hint ? `${label} (${hint})` : label}
      aria-label={label}
      aria-pressed={active || undefined}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-md transition disabled:opacity-40 ${
        active
          ? 'bg-indigo-100 text-indigo-700'
          : 'text-slate-600 hover:bg-slate-200/70 hover:text-slate-900'
      }`}
    >
      <Icon size={16} />
    </button>
  )
}

export default function RichTextToolbar({
  editorRef,
  // Tăng lên mỗi khi vùng chọn trong ô thay đổi -> buộc thanh công cụ đọc lại trạng
  // thái nút. Không có nó thì nút in đậm không sáng khi HR bấm vào giữa đoạn đậm.
  selectionTick = 0,
  onInsertImage,
  onAttachFile,
  uploading = false,
  disabled = false,
}) {
  const [colorOpen, setColorOpen] = useState(false)

  // Đọc trực tiếp mỗi lần render (selectionTick làm nó chạy lại) thay vì giữ trong
  // state: trạng thái đậm/nghiêng là thuộc tính của vùng chọn hiện tại, không phải
  // dữ liệu riêng của thanh công cụ — lưu thành state là mở đường cho lệch nhau.
  const stateOf = (command) => Boolean(editorRef?.current?.queryState?.(command))

  function run(command, argument) {
    editorRef?.current?.runCommand?.(command, argument)
  }

  function handleLink() {
    // window.prompt là lựa chọn có ý thức: nó giữ nguyên vùng chọn trong ô soạn thảo.
    // Một modal React sẽ render lại cây, làm mất selection, và phải tự lưu/khôi phục
    // range — nhiều mã hơn cho cùng một kết quả.
    const url = window.prompt('Dán liên kết (https://...):', 'https://')
    if (!url) return
    const trimmed = url.trim()
    // Chỉ nhận http/https/mailto. Cho qua "javascript:" là tạo ra một cú click chạy
    // mã ngay trong trang của người đọc mail lẫn trong trình soạn thảo.
    if (!/^(https?:\/\/|mailto:)/i.test(trimmed)) {
      window.alert('Liên kết phải bắt đầu bằng http://, https:// hoặc mailto:')
      return
    }
    run('createLink', trimmed)
  }

  const busy = disabled || uploading

  return (
    <div className="flex flex-wrap items-center gap-0.5 rounded-t-lg border border-b-0 border-slate-200 bg-slate-100/80 px-2 py-1.5">
      {TOGGLES.map((t) => (
        <ToolButton
          key={t.command}
          icon={t.icon}
          label={t.label}
          hint={t.hint}
          disabled={busy}
          // selectionTick được đọc ở đây để React coi giá trị này là "mới" sau mỗi lần
          // vùng chọn đổi.
          active={selectionTick >= 0 && stateOf(t.command)}
          onRun={() => run(t.command)}
        />
      ))}

      <span className="mx-1 h-5 w-px bg-slate-300" />

      {/* Màu chữ */}
      <div className="relative">
        <ToolButton
          icon={Palette}
          label="Màu chữ"
          disabled={busy}
          active={colorOpen}
          onRun={() => setColorOpen((v) => !v)}
        />
        {colorOpen && (
          <div className="absolute left-0 top-9 z-30 flex gap-1 rounded-lg border border-slate-200 bg-white p-2 shadow-lg">
            {COLORS.map((c) => (
              <button
                key={c.value}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  run('foreColor', c.value)
                  setColorOpen(false)
                }}
                title={c.label}
                aria-label={`Màu chữ ${c.label}`}
                className="h-6 w-6 rounded-full border border-slate-300 transition hover:scale-110"
                style={{ backgroundColor: c.value }}
              />
            ))}
          </div>
        )}
      </div>

      <ToolButton icon={Link2} label="Chèn liên kết" disabled={busy} onRun={handleLink} />
      <ToolButton
        icon={Link2Off}
        label="Bỏ liên kết"
        disabled={busy}
        onRun={() => run('unlink')}
      />
      <ToolButton
        icon={RemoveFormatting}
        label="Xoá định dạng"
        disabled={busy}
        onRun={() => run('removeFormat')}
      />

      <span className="mx-1 h-5 w-px bg-slate-300" />

      <ToolButton
        icon={uploading ? Loader2 : ImageIcon}
        label={uploading ? 'Đang tải lên…' : 'Chèn ảnh vào nội dung'}
        disabled={busy}
        onRun={onInsertImage}
      />
      <ToolButton
        icon={Paperclip}
        label="Đính kèm file"
        disabled={busy}
        onRun={onAttachFile}
      />
    </div>
  )
}
