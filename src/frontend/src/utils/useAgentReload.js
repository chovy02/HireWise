import { useSearchParams } from 'react-router-dom'

/**
 * NONCE LÀM MỚI DO AI COPILOT GỬI KÈM (`?t=...` trên URL).
 *
 * Vì sao cần: agent thao tác xong thì điều hướng tới ĐÚNG màn hình chứa thứ vừa làm —
 * mà rất thường là chính màn hình HR đang đứng. React Router coi "vẫn URL cũ" là không
 * có gì xảy ra, nên không component nào nạp lại và HR nhìn thấy y nguyên dữ liệu cũ.
 * Backend vì thế gắn `t` khác nhau vào MỌI directive điều hướng (xem `dieu_huong()`
 * trong agent_tools.py), và bên này chỉ việc đặt nó vào deps của effect nạp dữ liệu.
 *
 * VÌ SAO LÀ HOOK CHỨ KHÔNG TRUYỀN PROP: mỗi component tự fetch dữ liệu của mình
 * (InterviewPanel, InterviewSummary, CandidateDetailModal…) đều phải nghe nonce này.
 * Truyền prop thì phải xuyên qua nhiều tầng, và chỉ cần một tầng quên là component
 * dưới đứng im — đúng lỗi đã gặp: nonce tới được trang Shortlisting nhưng KHÔNG xuống
 * tới InterviewPanel, nên agent chấm xong 2 câu mà bảng phỏng vấn vẫn trống cho tới
 * khi HR F5.
 *
 * Dùng: `const reloadKey = useAgentReload()` rồi thêm `reloadKey` vào deps của effect
 * fetch. Không đổi gì khác trong component.
 */
export function useAgentReload() {
  const [searchParams] = useSearchParams()
  return searchParams.get('t') || ''
}
