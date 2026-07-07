import { apiFetch } from './client.js'

// ---- Interview API. Maps 1:1 to src/backend/app/routers/interview.py ----
// Tất cả endpoint đều yêu cầu đăng nhập + role hr_staff (backend chặn).

// GET /interviews/candidate/{candidateId} -> InterviewResponse
// Trả 404 nếu ứng viên chưa có buổi phỏng vấn nào.
export function getCandidateInterview(candidateId) {
  return apiFetch(`/interviews/candidate/${candidateId}`, { auth: true })
}

// POST /interviews/candidate/{candidateId}/generate  { aspect? } -> InterviewResponse
// AI sinh bộ câu hỏi mới. Backend XÓA buổi phỏng vấn cũ (nếu có) rồi tạo lại.
export function generateInterview(candidateId, aspect) {
  return apiFetch(`/interviews/candidate/${candidateId}/generate`, {
    method: 'POST',
    body: { aspect: aspect || null },
    auth: true,
  })
}

// POST /interviews/question/{questionId}/evaluate  { answer_text } -> EvaluationResultResponse
// AI chấm câu trả lời + có thể sinh 1 câu hỏi đào sâu (follow_up_question).
export function evaluateAnswer(questionId, answerText) {
  return apiFetch(`/interviews/question/${questionId}/evaluate`, {
    method: 'POST',
    body: { answer_text: answerText },
    auth: true,
  })
}

// PATCH /interviews/{interviewId}/complete -> { id, status, feedback_summary }
// Đóng buổi phỏng vấn; AI tổng kết năng lực ứng viên từ toàn bộ biên bản.
export function completeInterview(interviewId) {
  return apiFetch(`/interviews/${interviewId}/complete`, {
    method: 'PATCH',
    auth: true,
  })
}
