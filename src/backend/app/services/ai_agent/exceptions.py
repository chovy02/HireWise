class AIServiceError(Exception):
    """
    Lỗi phía dịch vụ AI (Gemini): mất mạng, hết quota, thiếu/sai API key, hoặc
    model trả về dữ liệu không phải JSON hợp lệ.
    """
