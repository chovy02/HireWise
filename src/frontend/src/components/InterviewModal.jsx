import { useEffect, useState } from 'react'
import {
  X,
  MessageSquareText,
  Sparkles,
  Loader2,
  Send,
  RefreshCw,
  CheckCircle2,
  FileCheck2,
  CornerDownRight,
} from 'lucide-react'
import { Badge, PrimaryButton, SecondaryButton } from './ui.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { formatName } from '../utils/formatName.js'
import {
  getCandidateInterview,
  generateInterview,
  evaluateAnswer,
  completeInterview,
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

function sortQuestions(list) {
  return [...(list || [])].sort((a, b) => a.order_index - b.order_index)
}

// Nội dung phỏng vấn (dùng chung cho cả popup lẫn tab trong Shortlisting).
// Luồng: AI sinh câu hỏi -> HR gõ tóm tắt câu trả lời -> AI chấm + đào sâu ->
// HR bấm kết thúc -> AI tổng kết năng lực.
// - onClose: nếu có -> hiện nút đóng (chế độ popup). Bỏ trống -> chế độ tab.
export function InterviewPanel({ candidateId, candidateName, onClose }) {
  const toast = useToast()
  const [interview, setInterview] = useState(null) // buổi phỏng vấn hiện tại
  const [loading, setLoading] = useState(true) // đang fetch lần đầu
  const [notFound, setNotFound] = useState(false) // chưa có -> màn hình sinh câu hỏi
  const [aspect, setAspect] = useState('')
  const [generating, setGenerating] = useState(false)
  const [completing, setCompleting] = useState(false)

  const displayName = formatName(candidateName) || 'Ứng viên'
  const completed = interview?.status === 'completed'

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setNotFound(false)
    setInterview(null)
    getCandidateInterview(candidateId)
      .then((data) => {
        if (cancelled) return
        setInterview({ ...data, questions: sortQuestions(data.questions) })
      })
      .catch(() => {
        // 404 (chưa có) hoặc lỗi khác -> hiện màn hình sinh câu hỏi.
        if (!cancelled) setNotFound(true)
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [candidateId])

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
  const answeredCount = (interview?.questions || []).filter((q) => q.answer_text).length

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
        <div className="flex items-center gap-3">
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
              Câu hỏi do AI sinh dựa trên CV &amp; JD — HR gõ lại câu trả lời để AI chấm.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {interview && !completed && (
            <SecondaryButton
              className="px-3 py-2"
              onClick={handleGenerate}
              disabled={generating}
              title="Sinh lại bộ câu hỏi (xóa buổi phỏng vấn hiện tại)"
            >
              {generating ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <RefreshCw size={15} />
              )}
              Tạo lại
            </SecondaryButton>
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
          </div>
        )}

        {/* Có buổi phỏng vấn -> danh sách câu hỏi */}
        {!loading && interview && (
          <div className="space-y-4">
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

            {interview.questions.map((q, idx) => (
              <QuestionCard
                key={q.id}
                index={idx + 1}
                question={q}
                locked={completed}
                onEvaluated={applyEvaluation}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      {!loading && interview && !completed && interview.questions.length > 0 && (
        <div className="flex items-center justify-between border-t border-slate-200 px-6 py-3.5">
          <span className="text-xs text-slate-500">
            Đã chấm {answeredCount}/{interview.questions.length} câu
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

// 1 câu hỏi: ô nhập câu trả lời, nút chấm điểm, và nhận xét AI sau khi chấm.
function QuestionCard({ index, question, locked, onEvaluated }) {
  const toast = useToast()
  const [draft, setDraft] = useState(question.answer_text || '')
  const [evaluating, setEvaluating] = useState(false)

  const answered = !!question.answer_text
  const isFollowUp = question.category?.toLowerCase().includes('follow')

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
      className={`rounded-xl border p-4 ${
        isFollowUp ? 'border-indigo-200 bg-indigo-50/40' : 'border-slate-200'
      }`}
    >
      {/* Đề bài */}
      <div className="flex items-start gap-3">
        <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-600">
          {index}
        </div>
        <div className="min-w-0 flex-1">
          {(isFollowUp || question.score != null) && (
            <div className="mb-1 flex flex-wrap items-center gap-2">
              {isFollowUp && (
                <CornerDownRight size={14} className="text-indigo-500" />
              )}
              {question.score != null && (
                <span className={`text-sm font-bold ${scoreColor(question.score)}`}>
                  {question.score}/10
                </span>
              )}
            </div>
          )}
          <p className="text-sm font-semibold text-slate-800">{question.question}</p>
        </div>
      </div>

      {/* Ô nhập câu trả lời */}
      <div className="mt-3 pl-9">
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
