import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, Send, Loader2, Wrench } from 'lucide-react'
import { chatWithAgent } from '../api/agent.js'
import { useProjects } from '../context/ProjectContext.jsx'

const SUGGESTIONS = [
  'Đang mở tuyển những vị trí nào?',
  'Tạo JD tuyển Backend Python 3 năm kinh nghiệm, cần Docker & PostgreSQL',
  'Mở vị trí Backend ra xem',
]

// AI Copilot: cột trái. HR chat -> agent tự gọi tool -> điều hướng/ làm mới phần
// giao diện bên phải qua `ui_actions` do backend trả về.
export default function CopilotChat() {
  const navigate = useNavigate()
  const { refreshProjects } = useProjects()

  const [messages, setMessages] = useState([
    {
      role: 'ai',
      text: 'Xin chào! Mình là trợ lý tuyển dụng. Bạn cứ ra lệnh, mình sẽ thao tác và mở đúng màn hình bên phải cho bạn.',
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

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

    // Lịch sử gửi lên backend (chỉ role + text, đổi 'ai' -> 'assistant').
    const history = messages
      .filter((m) => m.role === 'user' || m.role === 'ai')
      .map((m) => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.text }))

    setMessages((m) => [...m, { role: 'user', text: content }])
    setInput('')
    setLoading(true)
    try {
      const res = await chatWithAgent(content, history)
      setMessages((m) => [
        ...m,
        { role: 'ai', text: res.reply || '(không có phản hồi)', tools: res.tool_calls },
      ])
      runUiActions(res.ui_actions)
    } catch (err) {
      setMessages((m) => [...m, { role: 'ai', text: `⚠️ ${err.message}`, error: true }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <aside className="flex h-screen w-1/5 min-w-[280px] max-w-sm flex-shrink-0 flex-col border-l border-slate-200 bg-white">
      {/* Header */}
      <div className="flex items-center gap-2.5 border-b border-slate-100 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 text-white">
          <Sparkles size={16} />
        </div>
        <div>
          <p className="text-sm font-semibold text-slate-900">AI Copilot</p>
          <p className="text-xs text-slate-400">Trợ lý tuyển dụng</p>
        </div>
      </div>

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
              {m.tools?.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {[...new Set(m.tools)].map((t) => (
                    <span
                      key={t}
                      className="inline-flex items-center gap-1 rounded bg-white/70 px-1.5 py-0.5 text-[10px] font-medium text-slate-500"
                    >
                      <Wrench size={9} /> {t}
                    </span>
                  ))}
                </div>
              )}
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
            className="max-h-28 flex-1 resize-none bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400"
          />
          <button
            onClick={() => send()}
            disabled={loading || !input.trim()}
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white transition hover:bg-indigo-700 disabled:opacity-40"
          >
            <Send size={15} />
          </button>
        </div>
      </div>
    </aside>
  )
}
