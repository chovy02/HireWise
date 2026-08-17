import { useEffect, useState } from 'react'
import {
  Loader2,
  FileCheck2,
  Sparkles,
  MessageSquareText,
  CornerDownRight,
  PenLine,
} from 'lucide-react'
import { Badge } from './ui.jsx'
import { getCandidateInterview } from '../api/interviews.js'
import { useAgentReload } from '../utils/useAgentReload.js'
import {
  interviewAverageScore,
  isManualQuestion,
  numberInterviewQuestions,
  sortInterviewQuestions,
} from '../utils/interviewQuestions.js'

const STATUS_META = {
  pending: { variant: 'processing', label: 'Chưa chấm câu nào' },
  in_progress: { variant: 'ai', label: 'Đang phỏng vấn' },
  completed: { variant: 'completed', label: 'Đã hoàn tất' },
}

// Điểm câu hỏi theo thang 1-10 (giống InterviewPanel).
function scoreColor(score) {
  if (score == null) return 'text-slate-400'
  if (score >= 8) return 'text-emerald-600'
  if (score >= 5) return 'text-indigo-600'
  return 'text-red-500'
}

// Tóm tắt buổi phỏng vấn ở dạng chỉ-đọc — dùng cho hàng mở rộng trong tab
// Shortlist. Tự gọi API khi mount (HR bấm mũi tên mới nạp, không tải sẵn cả bảng).
export default function InterviewSummary({ candidateId }) {
  const [interview, setInterview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // `reloadKey`: agent vừa chấm/tổng kết buổi phỏng vấn thì tóm tắt này cũ ngay.
  const reloadKey = useAgentReload()

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    setInterview(null)
    getCandidateInterview(candidateId)
      .then((d) => !cancelled && setInterview(d))
      .catch((e) =>
        !cancelled && setError(e.message || 'Chưa có dữ liệu phỏng vấn.')
      )
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [candidateId, reloadKey])

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-2 text-sm text-slate-400">
        <Loader2 size={16} className="animate-spin" /> Đang tải tóm tắt phỏng vấn…
      </div>
    )
  }

  if (error || !interview) {
    return (
      <p className="py-2 text-sm text-slate-400">
        {error || 'Chưa có dữ liệu phỏng vấn.'}
      </p>
    )
  }

  const questions = sortInterviewQuestions(interview.questions)
  const { avg, scoredCount } = interviewAverageScore(questions)
  const statusMeta = STATUS_META[interview.status] || STATUS_META.pending

  return (
    <div className="space-y-3">
      {/* Trạng thái + điểm phỏng vấn trung bình */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex items-center gap-1.5 text-sm font-semibold text-slate-700">
          <MessageSquareText size={15} className="text-indigo-600" /> Kết quả phỏng vấn
        </span>
        <Badge variant={statusMeta.variant} upper={false}>
          {statusMeta.label}
        </Badge>
        <span className="text-xs text-slate-500">
          Đã chấm {scoredCount}/{questions.length} câu
        </span>
        {avg != null && (
          <span className="text-xs text-slate-500">
            Điểm trung bình:{' '}
            <span className={`text-sm font-bold ${scoreColor(avg)}`}>{avg}/10</span>
          </span>
        )}
      </div>

      {/* Tổng kết chung của AI */}
      {interview.feedback_summary && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-3.5">
          <h4 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-emerald-800">
            <FileCheck2 size={13} /> Đánh giá tổng kết của AI
          </h4>
          <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-emerald-900">
            {interview.feedback_summary}
          </p>
        </div>
      )}

      {/* Từng câu hỏi: điểm + câu trả lời + nhận xét AI */}
      {questions.length === 0 ? (
        <p className="text-sm text-slate-400">Buổi phỏng vấn chưa có câu hỏi nào.</p>
      ) : (
        <ol className="space-y-2.5">
          {numberInterviewQuestions(questions).map(({ question: q, label, isFollowUp }) => {
            const manual = isManualQuestion(q)
            return (
              <li
                key={q.id}
                className={`rounded-xl border p-3.5 ${
                  isFollowUp
                    ? 'ml-8 border-indigo-200 border-l-4 border-l-indigo-400 bg-indigo-50/50'
                    : manual
                      ? 'border-amber-200 border-l-4 border-l-amber-400 bg-amber-50/30'
                      : 'border-slate-200 bg-white'
                }`}
              >
                <div className="flex items-start gap-2.5">
                  <span
                    className={`mt-0.5 flex h-5 flex-shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${
                      isFollowUp
                        ? 'w-8 bg-indigo-100 text-indigo-700'
                        : manual
                          ? 'w-5 bg-amber-100 text-amber-700'
                          : 'w-5 bg-slate-100 text-slate-600'
                    }`}
                  >
                    {label}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      {isFollowUp ? (
                        <Badge variant="ai" upper={false}>
                          <CornerDownRight size={12} /> Câu đào sâu
                        </Badge>
                      ) : manual ? (
                        <Badge variant="warning" upper={false}>
                          <PenLine size={11} /> HR tự soạn
                        </Badge>
                      ) : (
                        q.category && (
                          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                            {q.category}
                          </span>
                        )
                      )}
                      <span className={`text-sm font-bold ${scoreColor(q.score)}`}>
                        {q.score != null ? `${q.score}/10` : 'Chưa chấm'}
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-slate-800">{q.question}</p>

                    {q.answer_text && (
                      <p className="mt-1.5 text-sm leading-relaxed text-slate-600">
                        <span className="font-semibold text-slate-500">Trả lời: </span>
                        {q.answer_text}
                      </p>
                    )}

                    {q.ai_evaluation && (
                      <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50/80 p-2.5">
                        <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-indigo-600">
                          <Sparkles size={11} /> AI nhận xét
                        </p>
                        <p className="mt-1 text-sm leading-relaxed text-slate-600">
                          {q.ai_evaluation}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
