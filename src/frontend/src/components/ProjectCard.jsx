import { Briefcase, Users, ArrowRight, Trash2 } from 'lucide-react'
import { Card } from './ui.jsx'
import { formatDate as formatLocalDate } from '../utils/datetime.js'

// Thẻ dự án (JD), dùng CHUNG cho Bảng điều khiển và trang chọn dự án ở Rút gọn.
//
// Trước đây hai trang tự dựng markup riêng nên thẻ cùng một dự án lại lệch tỉ lệ:
// bên này cắt mô tả 3 dòng có kèm số ứng viên, bên kia cắt 2 dòng và footer chỉ có
// chữ nằm dính lề phải (trống hẳn nửa trái). Gộp về một component thì mọi trang có
// đúng một tỉ lệ, và sửa một lần là ăn cả hai chỗ.
//
// `accent` + `actionLabel` là thứ phân biệt hai ngữ cảnh: cùng một dự án nhưng mở để
// XEM (tím indigo, "Mở dự án") khác với mở để RÚT GỌN (tím violet, "Rút gọn").

const ACCENTS = {
  indigo: {
    chip: 'bg-indigo-50 text-indigo-600',
    action: 'text-indigo-600',
    hover: 'hover:border-indigo-300',
    ring: 'focus-visible:ring-indigo-300',
  },
  // Emerald cho ngữ cảnh rút gọn — trùng màu ô "Đã rút gọn" ở trang chi tiết dự án,
  // nên cả app dùng một màu cho một khái niệm. Bản đầu tôi chọn violet, nhưng cạnh
  // indigo thì hai chip nhìn gần như y hệt, tức là không giải quyết được việc phân
  // biệt hai thẻ.
  emerald: {
    chip: 'bg-emerald-50 text-emerald-600',
    action: 'text-emerald-600',
    hover: 'hover:border-emerald-300',
    ring: 'focus-visible:ring-emerald-300',
  },
}

// "2026-07-26T13:02:53+00:00" -> "26/07/2026" (theo giờ Việt Nam)
const formatDate = (iso) => formatLocalDate(iso, null)

export default function ProjectCard({
  project,
  onOpen,
  onDelete,
  actionLabel = 'Mở',
  actionIcon: ActionIcon = ArrowRight,
  accent = 'indigo',
}) {
  const a = ACCENTS[accent] || ACCENTS.indigo
  const created = formatDate(project.createdAt)

  return (
    // Thẻ là <div> chứ không phải <button>: nút xoá nằm bên trong, mà <button> lồng
    // <button> là HTML không hợp lệ (bấm nút con kích hoạt luôn nút cha).
    <div className="group relative flex h-full flex-col">
      <div
        role="button"
        tabIndex={0}
        onClick={onOpen}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onOpen?.()
          }
        }}
        className={`flex h-full cursor-pointer flex-col rounded-xl text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ${a.ring}`}
      >
        <Card className={`flex h-full flex-col p-5 transition ${a.hover} hover:shadow-md`}>
          {/* Icon đứng RIÊNG một hàng, không nằm cạnh tiêu đề.
              Trước đây icon chiếm một cột bên trái nên tiêu đề bị thụt vào ~50px,
              trong khi mô tả và chân thẻ vẫn bám mép thẻ — ba mép trái khác nhau
              trong cùng một khối, nhìn là thấy lệch. Tách icon ra thì mọi dòng chữ
              dùng chung đúng một mép trái. */}
          <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${a.chip}`}>
            <Briefcase size={18} />
          </div>

          {/* Ngày tạo là thứ phân biệt được hai dự án TRÙNG TÊN, trùng cả mô tả —
              chuyện rất dễ xảy ra khi HR tạo nháp vài lần cho cùng một vị trí. */}
          <h3 className="mt-3.5 truncate text-base font-semibold text-slate-900">
            {project.title}
          </h3>
          {created && (
            <p className="mt-0.5 text-xs text-slate-400">Tạo ngày {created}</p>
          )}

          {/* min-h giữ cho các thẻ trong cùng một hàng CAO BẰNG NHAU kể cả khi dự án
              này mô tả 1 dòng còn dự án kia 2 dòng — thiếu nó thì lưới thẻ so le. */}
          <p className="mt-2.5 line-clamp-2 min-h-[2.75rem] flex-1 text-sm leading-relaxed text-slate-500">
            {project.jdInput || 'Chưa có mô tả.'}
          </p>

          {/* Chân thẻ: LUÔN có nội dung ở CẢ HAI bên. Trước đây thẻ ở trang Rút gọn
              chỉ có mỗi chữ "Rút gọn →" dính lề phải nên nửa trái trống hoác. */}
          <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 text-xs">
            <span className="inline-flex items-center gap-1.5 text-slate-500">
              <Users size={14} /> {project.candidateCount ?? 0} ứng viên
            </span>
            <span
              className={`inline-flex items-center gap-1 font-semibold ${a.action} transition-all group-hover:gap-1.5`}
            >
              {actionLabel} <ActionIcon size={14} />
            </span>
          </div>
        </Card>
      </div>

      {/* Nút xoá: mờ khi không rê chuột để lưới thẻ đỡ rối, nhưng LUÔN hiện khi được
          focus bằng bàn phím — opacity-0 mà vẫn bấm được là cái bẫy quen thuộc. */}
      {onDelete && (
        <button
          onClick={onDelete}
          title="Xoá dự án"
          aria-label={`Xoá dự án ${project.title}`}
          className="absolute right-3 top-3 rounded-lg p-1.5 text-slate-300 opacity-0 transition hover:bg-red-50 hover:text-red-600 focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-300 group-hover:opacity-100"
        >
          <Trash2 size={16} />
        </button>
      )}
    </div>
  )
}
