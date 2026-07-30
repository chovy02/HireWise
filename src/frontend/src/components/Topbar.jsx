// The thin white strip at the top of Dashboard / Shortlisting / Admin pages.
// (CV Analysis renders its own custom header instead of this.)
//
// Bên phải là chuông thông báo: hiển thị các thông báo admin phát (is_active),
// kèm chấm đỏ đếm số thông báo người dùng chưa xem (lưu id đã xem ở localStorage).
import { useEffect, useRef, useState } from 'react'
import { Bell, X } from 'lucide-react'
import { getActiveNotifications } from '../api/notifications.js'
import { formatDateTime } from '../utils/datetime.js'

const SEEN_KEY = 'hirewise_seen_notifications'

// Chấm màu theo loại thông báo, khớp bảng màu badge của admin.
const TYPE_DOT = {
  info: 'bg-sky-500',
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  error: 'bg-red-500',
}

function readSeen() {
  try {
    const raw = localStorage.getItem(SEEN_KEY)
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

// Chuông tách riêng để dùng được ở HAI nơi: thanh Topbar (màn rộng) và thanh công
// cụ hẹp của Layout. Trước đây hai thanh này chồng lên nhau ở dưới lg, tốn ~100px
// chiều cao mà thanh trên chỉ chứa mỗi cái chuông.
export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [err, setErr] = useState('')
  const [seen, setSeen] = useState(readSeen)
  const panelRef = useRef(null)

  function load() {
    getActiveNotifications()
      .then((data) => {
        setItems(Array.isArray(data) ? data : [])
        setErr('')
      })
      .catch((e) => {
        // Không chặn luồng chính, nhưng PHẢI hiện lỗi trong panel: nuốt im lặng
        // khiến chuông hỏng trông y hệt chuông không có thông báo nào.
        setErr(e.message || 'Không tải được thông báo.')
      })
  }

  // Tải khi mount + poll mỗi 30s để bắt thông báo mới admin vừa phát.
  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  // Đóng panel khi bấm ra ngoài.
  useEffect(() => {
    if (!open) return
    function onClick(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const unread = items.filter((n) => !seen.includes(n.id)).length

  function toggle() {
    const next = !open
    setOpen(next)
    // Mở chuông = đánh dấu đã xem toàn bộ thông báo hiện có.
    if (next && items.length) {
      const ids = items.map((n) => n.id)
      setSeen(ids)
      try {
        localStorage.setItem(SEEN_KEY, JSON.stringify(ids))
      } catch {
        /* localStorage đầy/bị chặn — bỏ qua */
      }
    }
  }

  return (
    <div className="relative" ref={panelRef}>
        <button
          onClick={toggle}
          className="relative rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
          title="Thông báo"
          aria-label="Thông báo"
        >
          <Bell size={20} />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
              {unread > 9 ? '9+' : unread}
            </span>
          )}
        </button>

        {open && (
          <div className="absolute right-0 top-12 z-50 w-[360px] max-w-[90vw] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Bell size={16} className="text-indigo-500" /> Thông báo
              </h3>
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              >
                <X size={16} />
              </button>
            </div>

            <div className="max-h-[70vh] overflow-y-auto">
              {err ? (
                <div className="px-4 py-8 text-center text-sm text-red-500">{err}</div>
              ) : items.length === 0 ? (
                <div className="px-4 py-10 text-center text-sm text-slate-400">
                  Chưa có thông báo nào.
                </div>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {items.map((n) => (
                    <li key={n.id} className="flex gap-3 px-4 py-3 hover:bg-slate-50/60">
                      <span
                        className={`mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ${
                          TYPE_DOT[n.type] || 'bg-slate-400'
                        }`}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-slate-900">{n.title}</p>
                        <p className="mt-0.5 text-sm text-slate-600">{n.message}</p>
                        <p className="mt-1 text-xs text-slate-400">
                          {formatDateTime(n.created_at)}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
      )}
    </div>
  )
}


// Thanh trắng mảnh trên cùng của Dashboard / Shortlisting / Admin.
// Ẩn dưới lg: ở đó Layout đã dựng thanh công cụ riêng (có hamburger + chuông +
// nút Copilot), giữ cả hai sẽ thành hai thanh chồng nhau.
export default function Topbar() {
  return (
    <header className="relative hidden h-14 flex-shrink-0 items-center justify-end gap-4 border-b border-slate-200 bg-white px-6 lg:flex">
      <NotificationBell />
    </header>
  )
}
