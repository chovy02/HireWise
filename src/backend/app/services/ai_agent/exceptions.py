class AIServiceError(Exception):
    """
    Lỗi phía dịch vụ AI (Groq): mất mạng, thiếu/sai API key, hoặc model trả về dữ
    liệu không phải JSON hợp lệ.
    """


class LLMBudgetExhausted(AIServiceError):
    """
    Hết ngân sách token/request của Groq (trần theo phút hoặc theo ngày).

    KHÁC HẲN các lỗi AI còn lại ở chỗ: CV không hề có vấn đề gì, chỉ là chưa tới
    lượt. Vì vậy nó KHÔNG được đánh CV thành FAILED — Celery bắt riêng exception này
    để hẹn giờ chấm lại sau `retry_after` giây.
    """

    def __init__(self, message: str, retry_after: float = 60.0):
        super().__init__(message)
        # Thời gian Groq (hoặc bộ đếm ngân sách) yêu cầu chờ, tính bằng giây.
        self.retry_after = retry_after


class LLMResponseTruncated(AIServiceError):
    """
    Model trả về JSON bị cắt giữa chừng vì chạm trần output token.

    Tách riêng vì đây là lỗi TẤT ĐỊNH (thử lại y nguyên vẫn cắt đúng chỗ đó) và
    trước đây nó hiện ra dưới dạng "không parse được JSON", rất dễ bị đổ oan cho
    rate limit trong khi cách sửa hoàn toàn khác.
    """
