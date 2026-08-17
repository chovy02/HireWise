import { useEffect, useRef, useState } from 'react'
import {
  X,
  ArrowLeft,
  MessageSquareText,
  Sparkles,
  Loader2,
  Send,
  RefreshCw,
  CheckCircle2,
  FileCheck2,
  CornerDownRight,
  Plus,
  PenLine,
  Trash2,
  ChevronDown,
  Lightbulb,
} from 'lucide-react'
import { Badge, PrimaryButton, ProgressBar, SecondaryButton } from './ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { useAgentReload } from '../utils/useAgentReload.js'
import { formatName } from '../utils/formatName.js'
import {
  interviewAverageScore,
  isManualQuestion,
  numberInterviewQuestions,
  sortInterviewQuestions,
} from '../utils/interviewQuestions.js'
import {
  getCandidateInterview,
  generateInterview,
  evaluateAnswer,
  completeInterview,
  addInterviewQuestion,
  deleteInterviewQuestion,
} from '../api/interviews.js'

const STATUS_META = {
  pending: { variant: 'processing', label: 'Chưa bắt đầu' },
  in_progress: { variant: 'ai', label: 'Đang phỏng vấn' },
  completed: { variant: 'completed', label: 'Đã hoàn tất' },
}

// Điểm phỏng vấn theo thang 1-10.
function scoreColor(score) {
  if (score == null) return 'text-slate-400'
  if (score >= 8) return 'text-emerald-600'
  if (score >= 5) return 'text-indigo-600'
  return 'text-red-500'
}

function scoreBarColor(score) {
  if (score == null) return 'slate'
  if (score >= 8) return 'green'
  if (score >= 5) return 'indigo'
  return 'red'
}

const sortQuestions = sortInterviewQuestions

// Nội dung phỏng vấn (dùng chung cho cả popup lẫn tab trong Shortlisting).
// Luồng: AI sinh câu hỏi (hoặc HR tự thêm) -> HR gõ tóm tắt câu trả lời ->
// AI chấm + đào sâu -> HR bấm kết thúc -> AI tổng kết năng lực.
// - onClose: nếu có -> hiện nút đóng (chế độ popup). Bỏ trống -> chế độ tab.
// - onBack: nếu có -> hiện nút "Quay lại" (chế độ tab, trả HR về tab Shortlist).
export function InterviewPanel({ candidateId, candidateName, onClose, onBack }) {
  const toast = useToast()
  const [interview, setInterview] = useState(null) // buổi phỏng vấn hiện tại
  const [loading, setLoading] = useState(true) // đang fetch lần đầu
  const [notFound, setNotFound] = useState(false) // chưa có -> màn hình sinh câu hỏi
  const [aspect, setAspect] = useState('')
  const [generating, setGenerating] = useState(false)
  const [completing, setCompleting] = useState(false)
  const [composing, setComposing] = useState(false) // đang mở ô soạn câu hỏi tự thêm
  const composerRef = useRef(null)

  const displayName = formatName(candidateName) || 'Ứng viên'
  const completed = interview?.status === 'completed'

  // `reloadKey` đổi = AI Copilot vừa động vào buổi phỏng vấn này (ghi câu trả lời,
  // chấm điểm, tổng kết). Không nghe nó thì effect chỉ chạy khi ĐỔI ỨNG VIÊN, nên
  // agent chấm xong 2/2 câu mà bảng bên trái vẫn trống tới khi HR F5 — đúng lỗi đã gặp.
  const reloadKey = useAgentReload()
  const daNap = useRef(null) // ứng viên nào đã nạp xong ít nhất một lần

  useEffect(() => {
    let cancelled = false
    // ĐỔI ỨNG VIÊN thì xoá sạch rồi hiện "đang tải"; còn NẠP LẠI cùng một người thì
    // giữ nguyên nội dung đang hiện và thay êm khi có dữ liệu mới. Nếu cũng xoá trắng
    // thì mỗi lần agent làm gì đó là màn hình chớp một cái, và ô soạn câu trả lời HR
    // đang gõ dở bị dựng lại từ đầu.
    const doiNguoi = daNap.current !== candidateId
    if (doiNguoi) {
      setLoading(true)
      setNotFound(false)
      setInterview(null)
    }
    getCandidateInterview(candidateId)
      .then((data) => {
        if (cancelled) return
        setInterview({ ...data, questions: sortQuestions(data.questions) })
        setNotFound(false)
        daNap.current = candidateId
      })
      .catch(() => {
        // 404 (chưa có) hoặc lỗi khác -> hiện màn hình sinh câu hỏi.
        if (!cancelled) setNotFound(true)
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [candidateId, reloadKey])

  // Mở ô soạn câu hỏi từ nút trên header: kéo luôn ô đó vào tầm mắt, vì nó nằm
  // dưới cùng danh sách nên với bộ 10 câu thì bấm xong sẽ không thấy gì thay đổi.
  useEffect(() => {
    if (!composing) return
    const id = requestAnimationFrame(() =>
      composerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    )
    return () => cancelAnimationFrame(id)
  }, [composing])

  async function handleGenerate() {
    setGenerating(true)
    try {
      const data = await generateInterview(candidateId, aspect.trim())
      setInterview({ ...data, questions: sortQuestions(data.questions) })
      setNotFound(false)
      toast('AI đã sinh bộ câu hỏi phỏng vấn.')
    } catch (e) {
      toast(e.message || 'Không sinh được câu hỏi.')
    } finally {
      setGenerating(false)
    }
  }

  // Lưu câu hỏi HR tự soạn. Backend trả về cả buổi phỏng vấn (và tự tạo buổi mới nếu
  // ứng viên chưa có), nên chỉ cần thay state bằng dữ liệu vừa nhận.
  async function handleAddQuestion(draft) {
    const data = await addInterviewQuestion(candidateId, draft)
    setInterview({ ...data, questions: sortQuestions(data.questions) })
    setNotFound(false)
    toast('Đã thêm câu hỏi của bạn.')
  }

  // Xoá khỏi state cả câu vừa xoá lẫn các câu đào sâu treo dưới nó (backend xoá kèm).
  function handleQuestionDeleted(removed) {
    setInterview((prev) => {
      if (!prev) return prev
      const root = Math.floor(removed.order_index / 10) * 10
      return {
        ...prev,
        questions: prev.questions.filter(
          (q) => q.order_index < root || q.order_index >= root + 10
        ),
      }
    })
  }

  // Cập nhật 1 câu hỏi trong state + chèn câu hỏi đào sâu (nếu AI sinh ra).
  function applyEvaluation(evaluatedQuestion, followUp) {
    setInterview((prev) => {
      if (!prev) return prev
      let questions = prev.questions.map((q) =>
        q.id === evaluatedQuestion.id ? evaluatedQuestion : q
      )
      if (followUp && !questions.some((q) => q.id === followUp.id)) {
        questions = [...questions, followUp]
      }
      return {
        ...prev,
        status: prev.status === 'pending' ? 'in_progress' : prev.status,
        questions: sortQuestions(questions),
      }
    })
  }

  async function handleComplete() {
    if (!interview) return
    if (!window.confirm('Kết thúc buổi phỏng vấn? AI sẽ tổng kết và không thể chấm thêm.'))
      return
    setCompleting(true)
    try {
      const res = await completeInterview(interview.id)
      setInterview((prev) => ({
        ...prev,
        status: res.status || 'completed',
        feedback_summary: res.feedback_summary,
      }))
      toast('Đã kết thúc buổi phỏng vấn.')
    } catch (e) {
      toast(e.message || 'Không kết thúc được buổi phỏng vấn.')
    } finally {
      setCompleting(false)
    }
  }

  const statusMeta = STATUS_META[interview?.status] || STATUS_META.pending
  // Điểm trung bình tính ngay tại đây: trước phải thoát ra tab Shortlist rồi bung
  // hàng ứng viên mới thấy con số này, trong khi nó là thứ HR cần nhìn đúng lúc
  // đang chấm để biết ứng viên đang ở đâu.
  const { avg, scoredCount, total } = interviewAverageScore(interview?.questions)

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
        <div className="flex items-center gap-3">
          {onBack && (
            <button
              onClick={onBack}
              className="rounded-md p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
              title="Quay lại danh sách rút gọn"
            >
              <ArrowLeft size={18} />
            </button>
          )}
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
            <MessageSquareText size={20} />
          </div>
          <div>
            <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
              Phỏng vấn — {displayName}
              {interview && (
                <Badge variant={statusMeta.variant} upper={false}>
                  {statusMeta.label}
                </Badge>
              )}
            </h2>
            <p className="text-xs text-slate-400">
              Câu hỏi do AI sinh từ CV &amp; JD hoặc do bạn tự thêm — HR gõ lại câu trả
              lời để AI chấm.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {interview && !completed && (
            <>
              {/* Header hẹp (popup + tên ứng viên dài) -> chỉ còn icon, khỏi bị xuống dòng */}
              <SecondaryButton
                className="px-3 py-2"
                onClick={() => setComposing(true)}
                title="Tự soạn một câu hỏi cho ứng viên"
              >
                <Plus size={15} />
                <span className="hidden sm:inline">Thêm câu hỏi</span>
              </SecondaryButton>
              <SecondaryButton
                className="px-3 py-2"
                onClick={handleGenerate}
                disabled={generating}
                title="Sinh lại bộ câu hỏi AI (câu bạn tự soạn vẫn được giữ)"
              >
                {generating ? (
                  <Loader2 size={15} className="animate-spin" />
                ) : (
                  <RefreshCw size={15} />
                )}
                <span className="hidden sm:inline">Tạo lại</span>
              </SecondaryButton>
            </>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              title="Đóng"
            >
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        {loading && (
          <div className="flex items-center justify-center py-16 text-slate-400">
            <Loader2 size={20} className="mr-2 animate-spin" /> Đang tải buổi phỏng vấn…
          </div>
        )}

        {/* Chưa có buổi phỏng vấn -> màn hình sinh câu hỏi */}
        {!loading && notFound && !interview && (
          <div className="mx-auto max-w-lg py-8 text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
              <Sparkles size={26} />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-slate-900">
              Tạo bộ câu hỏi phỏng vấn
            </h3>
            <p className="mx-auto mt-1.5 max-w-md text-sm text-slate-500">
              AI sẽ đọc CV và yêu cầu công việc để soạn các câu hỏi sắc bén, xoáy vào
              dự án thực tế và điểm yếu của ứng viên.
            </p>
            <div className="mt-5 text-left">
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Trọng tâm muốn xoáy sâu (tùy chọn)
              </label>
              <textarea
                value={aspect}
                onChange={(e) => setAspect(e.target.value)}
                rows={2}
                placeholder="Vd: Kinh nghiệm tối ưu hiệu năng, khả năng thiết kế hệ thống…"
                className="mt-2 w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
            </div>
            <PrimaryButton className="mt-5" onClick={handleGenerate} disabled={generating}>
              {generating ? (
                <>
                  <Loader2 size={16} className="animate-spin" /> AI đang soạn câu hỏi…
                </>
              ) : (
                <>
                  <Sparkles size={16} /> Sinh câu hỏi
                </>
              )}
            </PrimaryButton>

            {/* Đường tự soạn: HR nào đã có sẵn câu hỏi trong đầu thì không phải chờ AI
                sinh một bộ rồi mới thêm được câu của mình. */}
            <div className="mt-6 flex items-center gap-3">
              <span className="h-px flex-1 bg-slate-200" />
              <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                hoặc
              </span>
              <span className="h-px flex-1 bg-slate-200" />
            </div>

            <div className="mt-4 text-left">
              {composing ? (
                <QuestionComposer
                  onSubmit={handleAddQuestion}
                  onCancel={() => setComposing(false)}
                />
              ) : (
                <SecondaryButton
                  className="w-full"
                  onClick={() => setComposing(true)}
                >
                  <PenLine size={15} /> Tự soạn câu hỏi đầu tiên
                </SecondaryButton>
              )}
            </div>
          </div>
        )}

        {/* Có buổi phỏng vấn -> danh sách câu hỏi */}
        {!loading && interview && (
          <div className="space-y-4">
            {/* Điểm trung bình — luôn nằm trên đầu, cập nhật ngay sau mỗi lần chấm */}
            {interview.questions.length > 0 && (
              <AverageScoreCard avg={avg} scoredCount={scoredCount} total={total} />
            )}

            {/* Tổng kết AI (sau khi kết thúc) */}
            {completed && interview.feedback_summary && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-4">
                <h3 className="flex items-center gap-1.5 text-sm font-bold text-emerald-800">
                  <FileCheck2 size={16} /> Tổng kết của AI
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-emerald-900">
                  {interview.feedback_summary}
                </p>
              </div>
            )}

            {interview.questions.length === 0 && (
              <p className="py-10 text-center text-sm text-slate-400">
                Buổi phỏng vấn chưa có câu hỏi nào.
              </p>
            )}

            {numberInterviewQuestions(interview.questions).map(
              ({ question, label, isFollowUp }) => (
                <QuestionCard
                  key={question.id}
                  label={label}
                  isFollowUp={isFollowUp}
                  question={question}
                  locked={completed}
                  onEvaluated={applyEvaluation}
                  onDeleted={handleQuestionDeleted}
                />
              )
            )}

            {/* Tự thêm câu hỏi — luôn nằm ở cuối bộ câu hỏi, đúng chỗ câu mới sẽ xuất hiện */}
            {!completed && (
              <div ref={composerRef}>
                {composing ? (
                  <QuestionComposer
                    onSubmit={handleAddQuestion}
                    onCancel={() => setComposing(false)}
                  />
                ) : (
                  <AddQuestionTrigger onClick={() => setComposing(true)} />
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      {!loading && interview && !completed && interview.questions.length > 0 && (
        <div className="flex items-center justify-between border-t border-slate-200 px-6 py-3.5">
          {/* Thẻ điểm ở đầu danh sách cuộn mất khi HR chấm tới câu cuối — nhắc lại
              con số ở thanh dưới (luôn dính đáy) để không phải cuộn ngược lên. */}
          <span className="text-xs text-slate-500">
            Đã chấm {scoredCount}/{total} câu
            {avg != null && (
              <>
                {' · TB '}
                <span className={`text-sm font-bold ${scoreColor(avg)}`}>{avg}/10</span>
              </>
            )}
          </span>
          <PrimaryButton
            className="px-3 py-2"
            onClick={handleComplete}
            disabled={completing}
          >
            {completing ? (
              <>
                <Loader2 size={15} className="animate-spin" /> Đang tổng kết…
              </>
            ) : (
              <>
                <CheckCircle2 size={15} /> Kết thúc &amp; tổng kết
              </>
            )}
          </PrimaryButton>
        </div>
      )}
    </>
  )
}

// Popup phỏng vấn (dùng ở CandidateDetailModal). Bọc InterviewPanel trong overlay.
export default function InterviewModal({ candidateId, candidateName, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <InterviewPanel
          candidateId={candidateId}
          candidateName={candidateName}
          onClose={onClose}
        />
      </div>
    </div>
  )
}

// Thẻ điểm trung bình đặt trên đầu danh sách câu hỏi. Chưa chấm câu nào thì vẫn
// hiện (dạng "—") để HR biết chỗ này rồi sẽ ra điểm, thay vì thấy khung nhảy ra
// bất chợt sau lần chấm đầu tiên.
function AverageScoreCard({ avg, scoredCount, total }) {
  const percent = total ? (scoredCount / total) * 100 : 0
  return (
    <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-slate-50/70 px-4 py-3">
      <div className="min-w-0">
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
          Điểm trung bình
        </p>
        <p className={`text-2xl font-bold leading-tight ${scoreColor(avg)}`}>
          {avg == null ? '—' : avg}
          <span className="text-sm font-semibold text-slate-400">/10</span>
        </p>
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-slate-500">
          Đã chấm{' '}
          <span className="font-semibold text-slate-700">
            {scoredCount}/{total}
          </span>{' '}
          câu
        </p>
        <div className="mt-1.5">
          <ProgressBar value={percent} color={scoreBarColor(avg)} />
        </div>
        {avg == null && (
          <p className="mt-1.5 text-[11px] text-slate-400">
            Chấm ít nhất một câu để có điểm trung bình.
          </p>
        )}
      </div>
    </div>
  )
}

// Ô "+" ở cuối danh sách. Viền nét đứt để nó đọc ra là một chỗ trống chờ điền, không
// phải một câu hỏi đã có.
function AddQuestionTrigger({ onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center gap-3 rounded-xl border-2 border-dashed border-slate-200 px-4 py-3.5 text-left transition-all duration-200 hover:border-indigo-300 hover:bg-indigo-50/50 focus:outline-none focus-visible:border-indigo-400 focus-visible:ring-2 focus-visible:ring-indigo-100"
    >
      <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition-all duration-200 group-hover:scale-105 group-hover:bg-indigo-100 group-hover:text-indigo-600">
        <Plus size={17} />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-slate-700 transition-colors group-hover:text-indigo-700">
          Thêm câu hỏi của bạn
        </span>
      </span>
    </button>
  )
}

// Ô soạn câu hỏi HR tự đặt. Giữ nguyên trạng thái mở sau khi lưu để nhập liền nhiều câu.
// Ctrl/⌘ + Enter lưu, Esc đóng — Enter trần vẫn xuống dòng vì câu hỏi thường dài.
function QuestionComposer({ onSubmit, onCancel }) {
  const toast = useToast()
  const [text, setText] = useState('')
  const [expected, setExpected] = useState('')
  const [showExpected, setShowExpected] = useState(false)
  const [saving, setSaving] = useState(false)
  const textRef = useRef(null)

  useEffect(() => {
    textRef.current?.focus()
  }, [])

  const tooShort = text.trim().length > 0 && text.trim().length < 5

  async function handleSave() {
    const question = text.trim()
    if (question.length < 5) {
      toast('Nhập nội dung câu hỏi (ít nhất 5 ký tự).')
      textRef.current?.focus()
      return
    }
    setSaving(true)
    try {
      await onSubmit({ question, expectedAnswer: expected.trim() })
      setText('')
      setExpected('')
      setShowExpected(false)
      textRef.current?.focus()
    } catch (e) {
      toast(e.message || 'Không thêm được câu hỏi.')
    } finally {
      setSaving(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Escape') {
      e.stopPropagation() // đừng để Esc đóng luôn cả popup phỏng vấn
      onCancel()
      return
    }
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !saving) {
      e.preventDefault()
      handleSave()
    }
  }

  return (
    <div
      onKeyDown={handleKeyDown}
      className="animate-rise-in rounded-xl border border-indigo-200 bg-indigo-50/40 p-4 shadow-sm"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-indigo-700">
          <PenLine size={13} /> Câu hỏi của bạn
        </span>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          title="Đóng"
          className="rounded-md p-1 text-slate-400 transition hover:bg-white hover:text-slate-600 disabled:opacity-50"
        >
          <X size={15} />
        </button>
      </div>

      <textarea
        ref={textRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        disabled={saving}
        placeholder="Vd: Kể về một lần bạn phải sửa lỗi trên môi trường thật — bạn khoanh vùng nguyên nhân thế nào?"
        className={`mt-2.5 w-full resize-none rounded-lg border bg-white px-3 py-2 text-sm text-slate-700 outline-none transition focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50 ${
          tooShort ? 'border-amber-300' : 'border-slate-200 focus:border-indigo-500'
        }`}
      />

      {/* Gợi ý đáp án là tùy chọn: để trống thì lúc chấm AI tự dựng chuẩn trả lời. */}
      <button
        type="button"
        onClick={() => setShowExpected((v) => !v)}
        className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 transition-colors hover:text-indigo-600"
      >
        <ChevronDown
          size={14}
          className={`transition-transform duration-200 ${showExpected ? 'rotate-180' : ''}`}
        />
        Gợi ý đáp án kỳ vọng (tùy chọn)
      </button>

      {showExpected && (
        <div className="animate-rise-in mt-1.5">
          <textarea
            value={expected}
            onChange={(e) => setExpected(e.target.value)}
            rows={2}
            disabled={saving}
            placeholder="Các từ khóa / hướng tư duy đúng để AI đối chiếu khi chấm…"
            className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
          />
          <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
            Để trống cũng được — AI sẽ tự dựng chuẩn trả lời tốt cho câu hỏi này rồi chấm
            theo đó.
          </p>
        </div>
      )}

      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="hidden text-[11px] text-slate-400 sm:block">
          Ctrl + Enter để lưu · Esc để đóng
        </span>
        <div className="flex items-center gap-2">
          <SecondaryButton
            className="px-3 py-1.5 text-xs"
            onClick={onCancel}
            disabled={saving}
          >
            Huỷ
          </SecondaryButton>
          <PrimaryButton
            className="px-3 py-1.5 text-xs"
            onClick={handleSave}
            disabled={saving || !text.trim()}
          >
            {saving ? (
              <>
                <Loader2 size={13} className="animate-spin" /> Đang lưu…
              </>
            ) : (
              <>
                <Plus size={13} /> Thêm câu hỏi
              </>
            )}
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}

// 1 câu hỏi: ô nhập câu trả lời, nút chấm điểm, và nhận xét AI sau khi chấm.
// Câu đào sâu (follow-up) được thụt vào + viền trái đậm để tách khỏi câu chính.
// Câu HR tự soạn có badge riêng + nút xoá (câu AI thì không: muốn đổi thì bấm "Tạo lại").
function QuestionCard({ label, isFollowUp, question, locked, onEvaluated, onDeleted }) {
  const toast = useToast()
  const [draft, setDraft] = useState(question.answer_text || '')
  const [evaluating, setEvaluating] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const answered = !!question.answer_text
  const manual = isManualQuestion(question)

  async function handleDelete() {
    setDeleting(true)
    try {
      await deleteInterviewQuestion(question.id)
      onDeleted?.(question)
      toast('Đã xoá câu hỏi.')
    } catch (e) {
      toast(e.message || 'Không xoá được câu hỏi.')
      setDeleting(false)
      setConfirmDelete(false)
    }
  }

  async function handleEvaluate() {
    if (!draft.trim()) {
      toast('Nhập tóm tắt câu trả lời của ứng viên trước.')
      return
    }
    setEvaluating(true)
    try {
      const res = await evaluateAnswer(question.id, draft.trim())
      onEvaluated(res.evaluated_question, res.follow_up_question)
      toast('AI đã chấm câu trả lời.')
    } catch (e) {
      toast(e.message || 'Không chấm được câu trả lời.')
    } finally {
      setEvaluating(false)
    }
  }

  return (
    <div
      className={`group/q animate-rise-in rounded-xl border p-4 transition-colors ${
        isFollowUp
          ? 'ml-8 border-indigo-200 border-l-4 border-l-indigo-400 bg-indigo-50/50'
          : manual
            ? 'border-amber-200 border-l-4 border-l-amber-400 bg-amber-50/30'
            : 'border-slate-200'
      }`}
    >
      {/* Đề bài */}
      <div className="flex items-start gap-3">
        <div
          className={`flex h-6 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold ${
            isFollowUp
              ? 'w-9 bg-indigo-100 text-indigo-700'
              : manual
                ? 'w-6 bg-amber-100 text-amber-700'
                : 'w-6 bg-slate-100 text-slate-600'
          }`}
        >
          {label}
        </div>
        <div className="min-w-0 flex-1">
          {(isFollowUp || manual || question.score != null) && (
            <div className="mb-1 flex flex-wrap items-center gap-2">
              {isFollowUp && (
                <Badge variant="ai" upper={false}>
                  <CornerDownRight size={12} /> Câu đào sâu
                </Badge>
              )}
              {manual && (
                <Badge variant="warning" upper={false}>
                  <PenLine size={11} /> Bạn tự soạn
                </Badge>
              )}
              {question.score != null && (
                <span className={`text-sm font-bold ${scoreColor(question.score)}`}>
                  {question.score}/10
                </span>
              )}
            </div>
          )}
          <p className="text-sm font-semibold text-slate-800">{question.question}</p>

          {/* Gợi ý đáp án chỉ hiện với câu HR tự gõ — để họ soát lại đúng thứ mình vừa nhập. */}
          {manual && question.expected_answer && (
            <p className="mt-1.5 flex items-start gap-1.5 text-xs leading-relaxed text-slate-500">
              <Lightbulb size={13} className="mt-0.5 flex-shrink-0 text-amber-500" />
              <span>
                <span className="font-semibold">Đáp án kỳ vọng: </span>
                {question.expected_answer}
              </span>
            </p>
          )}
        </div>

        {/* Xoá câu tự soạn. Trên máy có chuột thì ẩn tới khi trỏ vào thẻ cho danh sách
            gọn mắt; màn cảm ứng không có hover nên phải hiện sẵn (`md:` trở lên mới ẩn),
            không thì không có cách nào bấm tới. */}
        {manual && !locked && !confirmDelete && (
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            title="Xoá câu hỏi này"
            className="flex-shrink-0 rounded-md p-1.5 text-slate-300 transition hover:bg-red-50 hover:text-red-500 focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-100 md:opacity-0 md:group-hover/q:opacity-100"
          >
            <Trash2 size={15} />
          </button>
        )}
      </div>

      {/* Xác nhận xoá ngay trong thẻ — nhẹ hơn một hộp thoại chắn cả trang cho một câu hỏi. */}
      {manual && !locked && confirmDelete && (
        <div className="animate-rise-in mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
          <span className="text-xs font-medium text-red-700">
            Xoá câu hỏi này{answered ? ' cùng câu trả lời và điểm đã chấm' : ''}?
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setConfirmDelete(false)}
              disabled={deleting}
              className="rounded-md px-2.5 py-1 text-xs font-medium text-slate-600 transition hover:bg-white disabled:opacity-50"
            >
              Huỷ
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleting}
              className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-2.5 py-1 text-xs font-semibold text-white transition hover:bg-red-700 disabled:opacity-60"
            >
              {deleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
              Xoá
            </button>
          </div>
        </div>
      )}

      {/* Ô nhập câu trả lời (thẳng hàng với đề bài, chip số câu đào sâu rộng hơn) */}
      <div className={`mt-3 ${isFollowUp ? 'pl-12' : 'pl-9'}`}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={2}
          disabled={locked}
          placeholder="Gõ tóm tắt câu trả lời của ứng viên…"
          className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50 disabled:text-slate-500"
        />
        {!locked && (
          <div className="mt-2 flex justify-end">
            <PrimaryButton
              className="px-3 py-1.5 text-xs"
              onClick={handleEvaluate}
              disabled={evaluating}
            >
              {evaluating ? (
                <>
                  <Loader2 size={13} className="animate-spin" /> AI đang chấm…
                </>
              ) : (
                <>
                  <Send size={13} /> {answered ? 'Chấm lại' : 'Chấm điểm'}
                </>
              )}
            </PrimaryButton>
          </div>
        )}

        {/* Nhận xét của AI */}
        {question.ai_evaluation && (
          <div className="mt-2 rounded-lg border border-slate-200 bg-white p-3">
            <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-indigo-600">
              <Sparkles size={12} /> AI nhận xét
            </p>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">
              {question.ai_evaluation}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
