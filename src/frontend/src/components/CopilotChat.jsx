import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, Send, Loader2, SquarePen, History, Trash2, X } from 'lucide-react'
import {
  chatWithAgent,
  listChatSessions,
  getChatSession,
  deleteChatSession,
} from '../api/agent.js'
import { useProjects } from '../context/ProjectContext.jsx'
import { usePageContext } from '../context/PageContext.jsx'
import { formatShortDateTime } from '../utils/datetime.js'

const SUGGESTIONS = [
  'Đang mở tuyển những vị trí nào?',
  'Tạo JD tuyển Backend Python 3 năm kinh nghiệm, cần Docker & PostgreSQL',
  'Mở vị trí Backend ra xem',
]

const WELCOME = {
  role: 'ai',
  text: 'Xin chào! Mình là trợ lý tuyển dụng. Bạn cứ ra lệnh, mình sẽ thao tác và mở đúng màn hình bên trái cho bạn.',
}

// Ngày dạng "14/07 18:42" (giờ Việt Nam) cho danh sách lịch sử.
const shortDate = (iso) => formatShortDateTime(iso)

// AI Copilot: cột phải. HR chat -> agent gọi tool qua MCP -> điều hướng/làm mới phần
// giao diện bên trái qua `ui_actions`. Lịch sử hội thoại lưu ở backend (chat_sessions).
export default function CopilotChat({ open = false, onClose }) {
  const navigate = useNavigate()
  const { refreshProjects } = useProjects()
  // Vị trí mà trang bên trái đang mở (do Shortlisting/ProjectDetail công bố).
  const { pageContext } = usePageContext()

  const [messages, setMessages] = useState([WELCOME])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  // Phiên chat do backend tạo; lưu lại để các lượt sau nối đúng lịch sử trong DB.
  const [sessionId, setSessionId] = useState(null)

  // Panel lịch sử
  const [historyOpen, setHistoryOpen] = useState(false)
  const [sessions, setSessions] = useState([])
  const [loadingSessions, setLoadingSessions] = useState(false)

  const scrollRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  // Tự giãn chiều cao textarea theo số dòng, tối đa ~6 dòng rồi cho cuộn nội bộ.
  const MAX_INPUT_HEIGHT = 140
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto' // reset để scrollHeight phản ánh đúng nội dung hiện tại
    el.style.height = `${Math.min(el.scrollHeight, MAX_INPUT_HEIGHT)}px`
    el.style.overflowY = el.scrollHeight > MAX_INPUT_HEIGHT ? 'auto' : 'hidden'
  }, [input])

  const loadSessions = useCallback(async () => {
    setLoadingSessions(true)
    try {
      setSessions(await listChatSessions())
    } catch {
      setSessions([])
    } finally {
      setLoadingSessions(false)
    }
  }, [])

  // Mở panel lịch sử -> nạp danh sách phiên.
  useEffect(() => {
    if (historyOpen) loadSessions()
  }, [historyOpen, loadSessions])

  function newChat() {
    setSessionId(null)
    setMessages([WELCOME])
    setInput('')
    setHistoryOpen(false)
  }

  async function openSession(id) {
    setHistoryOpen(false)
    setLoading(true)
    try {
      const data = await getChatSession(id)
      setSessionId(id)
      setMessages(data.messages?.length ? data.messages : [WELCOME])
    } catch (err) {
      setMessages([WELCOME, { role: 'ai', text: `⚠️ ${err.message}`, error: true }])
    } finally {
      setLoading(false)
    }
  }

  async function removeSession(e, id) {
    e.stopPropagation() // đừng mở phiên khi bấm nút xoá
    try {
      await deleteChatSession(id)
      setSessions((list) => list.filter((s) => s.session_id !== id))
      if (id === sessionId) newChat() // đang mở đúng phiên vừa xoá
    } catch {
      /* im lặng — không đáng làm phiền HR */
    }
  }

  // Thực thi các directive điều hướng giao diện mà agent trả về.
  function runUiActions(actions = []) {
    for (const a of actions) {
      if (a?.type === 'navigate' && a.path) navigate(a.path)
      else if (a?.type === 'refresh') refreshProjects()
    }
  }

  async function send(text) {
    const content = (text ?? input).trim()
    if (!content || loading) return

    setMessages((m) => [...m, { role: 'user', text: content }])
    setInput('')
    setLoading(true)
    try {
      // Backend tự dựng lịch sử từ DB theo session_id -> không gửi lại history.
      // `pageContext` cho agent biết HR đang mở vị trí nào, để yêu cầu không nêu vị
      // trí ("lấy 3 người điểm cao nhất") không bị agent đoán sai sang vị trí khác.
      const res = await chatWithAgent(content, sessionId, pageContext)
      if (res.session_id) setSessionId(res.session_id)
      // Chỉ giữ phần TEXT trả lời. `tool_calls`/`steps` là chuyện nội bộ của agent —
      // HR không cần biết mình vừa gọi tool nào, hiện ra chỉ làm rối khung chat.
      setMessages((m) => [...m, { role: 'ai', text: res.reply || '(không có phản hồi)' }])
      runUiActions(res.ui_actions)
    } catch (err) {
      setMessages((m) => [...m, { role: 'ai', text: `⚠️ ${err.message}`, error: true }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <aside
      className={[
        'relative flex-col border-l border-slate-200 bg-white',
        // Mobile: lớp phủ toàn màn hình, chỉ hiện khi bật từ thanh công cụ.
        // min-w-[280px] cũ khiến panel chiếm gần hết bề ngang điện thoại và
        // đẩy nội dung trang ra ngoài khung nhìn.
        open ? 'fixed inset-0 z-40 flex' : 'hidden',
        // lg trở lên: cột cố định ~1/5 bên phải như thiết kế gốc.
        'lg:relative lg:flex lg:h-screen lg:w-1/5 lg:min-w-[280px] lg:max-w-sm lg:flex-shrink-0',
      ].join(' ')}
    >
      {/* Header */}
      <div className="flex items-center gap-2.5 border-b border-slate-100 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 text-white">
          <Sparkles size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-900">AI Copilot</p>
          <p className="truncate text-xs text-slate-400">Trợ lý tuyển dụng</p>
        </div>
        <button
          onClick={newChat}
          title="Cuộc trò chuyện mới"
          aria-label="Cuộc trò chuyện mới"
          className="rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
        >
          <SquarePen size={17} />
        </button>
        <button
          onClick={() => setHistoryOpen((v) => !v)}
          title="Lịch sử trò chuyện"
          aria-label="Lịch sử trò chuyện"
          aria-expanded={historyOpen}
          className={`rounded-md p-1.5 transition hover:bg-slate-100 ${
            historyOpen ? 'bg-slate-100 text-indigo-600' : 'text-slate-400 hover:text-slate-700'
          }`}
        >
          <History size={17} />
        </button>
        {/* Chỉ mobile: panel là lớp phủ nên phải có lối thoát. */}
        <button
          onClick={onClose}
          title="Đóng AI Copilot"
          aria-label="Đóng AI Copilot"
          className="rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 lg:hidden"
        >
          <X size={17} />
        </button>
      </div>

      {/* Panel lịch sử (phủ lên khung chat) */}
      {historyOpen && (
        <div className="absolute inset-x-0 bottom-0 top-[65px] z-10 flex flex-col bg-white">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Lịch sử trò chuyện
            </p>
            <button
              onClick={() => setHistoryOpen(false)}
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            >
              <X size={15} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            {loadingSessions ? (
              <p className="flex items-center gap-2 px-2 py-3 text-sm text-slate-400">
                <Loader2 size={14} className="animate-spin" /> Đang tải…
              </p>
            ) : sessions.length === 0 ? (
              <p className="px-2 py-3 text-sm text-slate-400">Chưa có cuộc trò chuyện nào.</p>
            ) : (
              sessions.map((s) => (
                <div
                  key={s.session_id}
                  onClick={() => openSession(s.session_id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && openSession(s.session_id)}
                  className={`group flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 transition hover:bg-slate-100 ${
                    s.session_id === sessionId ? 'bg-indigo-50' : ''
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-slate-700">{s.title}</p>
                    <p className="text-[11px] text-slate-400">{shortDate(s.created_at)}</p>
                  </div>
                  <button
                    onClick={(e) => removeSession(e, s.session_id)}
                    title="Xoá"
                    className="rounded p-1 text-slate-300 opacity-0 transition group-hover:opacity-100 hover:bg-red-50 hover:text-red-500"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-3 py-4">
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            <div
              className={[
                'max-w-[92%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm',
                m.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : m.error
                    ? 'bg-red-50 text-red-700'
                    : 'bg-slate-100 text-slate-800',
              ].join(' ')}
            >
              {m.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl bg-slate-100 px-3 py-2 text-sm text-slate-500">
              <Loader2 size={14} className="animate-spin" /> Đang xử lý…
            </div>
          </div>
        )}
      </div>

      {/* Gợi ý nhanh (chỉ hiện khi mới bắt đầu) */}
      {messages.length <= 1 && (
        <div className="space-y-1.5 px-3 pb-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => send(s)}
              className="w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-left text-xs text-slate-600 transition hover:border-indigo-300 hover:bg-indigo-50"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="border-t border-slate-100 p-3">
        <div className="flex items-end gap-2 rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-2 focus-within:border-indigo-400">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            placeholder="Nhập yêu cầu…"
            aria-label="Nội dung yêu cầu gửi cho AI Copilot"
            className="flex-1 resize-none bg-transparent text-sm leading-5 text-slate-800 outline-none placeholder:text-slate-400"
          />
          <button
            onClick={() => send()}
            disabled={loading || !input.trim()}
            title="Gửi"
            aria-label="Gửi yêu cầu"
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white transition hover:bg-indigo-700 disabled:opacity-40"
          >
            <Send size={15} />
          </button>
        </div>
      </div>
    </aside>
  )
}
