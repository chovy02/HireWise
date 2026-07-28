// Sắp xếp & đánh số câu hỏi phỏng vấn — dùng chung cho khung phỏng vấn và
// khung tóm tắt trong tab Shortlist để hai chỗ luôn hiện cùng một số thứ tự.

// Câu đào sâu do AI sinh ra sau khi chấm một câu trả lời (backend đặt
// category = "Đào sâu (Follow-up)").
export function isFollowUpQuestion(q) {
  return !!q?.category?.toLowerCase().includes('follow')
}

export function sortInterviewQuestions(list) {
  return [...(list || [])].sort((a, b) => a.order_index - b.order_index)
}

// Gắn nhãn số cho từng câu: câu chính là 1, 2, 3… còn câu đào sâu ăn theo câu
// chính ngay trước nó -> 1.1, 1.2, 1.3…
// Nhận vào danh sách ĐÃ sắp theo order_index.
export function numberInterviewQuestions(questions) {
  let main = 0
  let sub = 0
  return (questions || []).map((q) => {
    if (isFollowUpQuestion(q)) {
      sub += 1
      // Dữ liệu lạ (câu đào sâu đứng trước mọi câu chính) -> vẫn gán vào nhóm 1.
      return { question: q, label: `${main || 1}.${sub}`, isFollowUp: true }
    }
    main += 1
    sub = 0
    return { question: q, label: String(main), isFollowUp: false }
  })
}
