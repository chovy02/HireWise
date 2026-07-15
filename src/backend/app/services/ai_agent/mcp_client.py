"""
MCP CLIENT — backend nói chuyện với HireWise MCP Server qua SSE.

Nhờ module này, agent loop của web KHÔNG còn gọi thẳng hàm Python trong agent_tools
nữa, mà: hỏi MCP server "có tool gì?" -> đưa danh sách cho LLM -> LLM chọn -> gọi
call_tool qua MCP. Tức MCP nằm THẬT trong luồng chạy của sản phẩm.

Điểm tinh tế: tham số `acting_user_id` (HR đang đăng nhập) bị LỌC khỏi schema trước
khi đưa cho LLM, và được backend tiêm vào lúc gọi -> LLM không thể mạo danh user.
"""

import json
import os
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.sse import sse_client

MCP_URL = os.getenv("MCP_SERVER_URL", "http://mcp:8001/sse")

# Tham số do backend tiêm, không bao giờ để LLM tự điền.
_INJECTED_PARAMS = {"acting_user_id"}


class MCPUnavailable(Exception):
    """Không kết nối được MCP server -> caller nên fallback sang gọi tool nội bộ."""


@asynccontextmanager
async def mcp_session():
    """Mở 1 phiên MCP (dùng cho cả 1 lượt chat, không mở/đóng mỗi lần gọi tool)."""
    try:
        async with sse_client(MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    except MCPUnavailable:
        raise
    except Exception as e:  # noqa: BLE001 - gộp mọi lỗi kết nối/handshake
        raise MCPUnavailable(f"Không kết nối được MCP server ({MCP_URL}): {e}") from e


def _to_llm_schema(tool) -> dict:
    """Đổi tool MCP -> schema function-calling của Groq/OpenAI, bỏ tham số nội bộ."""
    params = dict(tool.inputSchema or {"type": "object", "properties": {}})
    props = dict(params.get("properties") or {})
    for hidden in _INJECTED_PARAMS:
        props.pop(hidden, None)
    params["properties"] = props
    if "required" in params:
        params["required"] = [r for r in params["required"] if r not in _INJECTED_PARAMS]

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": params,
        },
    }


async def fetch_tools(session: ClientSession) -> tuple[list[dict], set[str]]:
    """Lấy danh sách tool từ MCP server. Trả (schema cho LLM, tên các tool hợp lệ)."""
    resp = await session.list_tools()
    tools = [_to_llm_schema(t) for t in resp.tools]
    names = {t.name for t in resp.tools}
    return tools, names


async def call_tool(session: ClientSession, name: str, args: dict, acting_user_id=None) -> dict:
    """
    Gọi 1 tool qua MCP và parse kết quả về dict.

    FastMCP trả kết quả dạng text content chứa JSON (vì tool của ta trả dict/list).
    """
    payload = dict(args or {})
    if acting_user_id:
        payload["acting_user_id"] = str(acting_user_id)

    try:
        res = await session.call_tool(name, payload)
    except Exception as e:  # noqa: BLE001 - trả lỗi cho LLM tự xử lý
        return {"error": f"MCP call_tool thất bại: {e}"}

    texts = [c.text for c in (res.content or []) if getattr(c, "text", None)]

    if getattr(res, "isError", False):
        return {"error": "\n".join(texts) or "MCP tool báo lỗi."}
    if not texts:
        return {}

    # LƯU Ý: khi tool trả về list, FastMCP tách MỖI PHẦN TỬ thành 1 text block riêng.
    # Vì vậy phải parse từng block, không nối chuỗi rồi mới parse (sẽ hỏng JSON).
    items = []
    for t in texts:
        try:
            items.append(json.loads(t))
        except json.JSONDecodeError:
            items.append(t)

    if len(items) == 1:
        one = items[0]
        if isinstance(one, dict):
            return one
        if isinstance(one, list):
            return {"items": one}
        return {"result": one}

    # Nhiều block -> tool đã trả về một danh sách.
    return {"items": items}
