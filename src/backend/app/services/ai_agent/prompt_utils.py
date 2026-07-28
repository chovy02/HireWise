"""Tiện ích dùng chung cho các prompt."""


def clean_json_response(text: str) -> str:
    """Bóc rào ```json ... ``` nếu model lỡ bọc markdown quanh JSON."""
    text = (text or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text
