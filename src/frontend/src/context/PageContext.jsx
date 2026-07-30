import { createContext, useContext, useState, useEffect } from 'react'

/**
 * NGỮ CẢNH TRANG ĐANG MỞ — thứ HR đang nhìn, để Copilot khỏi phải đoán.
 *
 * Vì sao cần: khung chat nằm ở cột phải, còn "đang mở vị trí nào" là state CỤC BỘ của
 * từng trang (Shortlisting giữ trong useState, ProjectDetail lấy từ URL). Không có
 * đường nào để CopilotChat đọc được, nên khi HR gõ "lấy 3 người điểm cao nhất" mà
 * không nêu vị trí thì agent phải tự đoán tên vị trí — và nó đã đoán sai thật
 * ("Backend Developer" trong khi vị trí đang mở là "Backend Python"), rồi từ chỗ đó
 * bịa tiếp cả tên ứng viên.
 *
 * Trang nào có một vị trí đang mở thì gọi `usePublishPageContext({ jdId, jdTitle })`;
 * CopilotChat đọc và gửi kèm mỗi tin nhắn.
 *
 * ĐÂY CHỈ LÀ GỢI Ý, KHÔNG PHẢI QUYỀN. Backend vẫn giới hạn mọi tool theo owner_id của
 * HR đang đăng nhập, nên một jd_id gửi lên từ client không mở được dữ liệu của tài
 * khoản khác.
 */
const PageContext = createContext(null)

export function PageContextProvider({ children }) {
  const [pageContext, setPageContext] = useState(null)
  return (
    <PageContext.Provider value={{ pageContext, setPageContext }}>
      {children}
    </PageContext.Provider>
  )
}

export function usePageContext() {
  return useContext(PageContext) || { pageContext: null, setPageContext: () => {} }
}

/**
 * Công bố ngữ cảnh của trang hiện tại, tự xoá khi rời trang.
 *
 * Xoá lúc unmount là phần quan trọng: nếu để sót, HR rời trang vị trí sang Dashboard
 * mà agent vẫn tưởng đang mở vị trí cũ — còn tệ hơn là không có ngữ cảnh, vì lúc đó
 * nó thao tác lên đúng dữ liệu của một vị trí HR không hề nhìn thấy.
 */
export function usePublishPageContext({ page, jdId, jdTitle }) {
  const { setPageContext } = usePageContext()

  useEffect(() => {
    setPageContext({ page, jd_id: jdId || null, jd_title: jdTitle || null })
    return () => setPageContext(null)
  }, [setPageContext, page, jdId, jdTitle])
}
