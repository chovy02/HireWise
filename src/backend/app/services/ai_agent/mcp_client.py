"""
MCP CLIENT — backend nói chuyện với HireWise MCP Server qua Streamable HTTP.

Nhờ module này, agent loop của web KHÔNG gọi thẳng hàm Python trong agent_tools nữa,
mà: hỏi MCP server "có tool gì?" -> đưa danh sách cho LLM -> LLM chọn -> gọi
`call_tool` qua MCP. Tức MCP nằm THẬT trong luồng chạy của sản phẩm.

Ba điểm đáng chú ý
------------------
1. DANH TÍNH ĐI THEO PHIÊN, KHÔNG THEO LỜI GỌI TOOL. Backend gắn header
   `X-HireWise-Actor` khi mở phiên MCP, nên `acting_user_id` không còn là tham số của
   tool nữa -> nó không nằm trong schema, LLM không nhìn thấy và không mạo danh được.
   (Server vẫn xác minh lại danh tính đó với bảng users.)
2. PHÂN BIỆT LỖI KẾT NỐI VỚI LỖI NGHIỆP VỤ. Lỗi nghiệp vụ ("không tìm thấy ứng viên")
   trả về cho LLM tự xử lý; lỗi kết nối ném `MCPUnavailable` để agent rơi về đường
   fallback. Bản trước gộp cả hai thành `{"error": ...}`, nên khi MCP chết GIỮA lượt
   thì LLM nhận một thông báo vô nghĩa rồi tự bịa câu trả lời.
3. TIMEOUT. Mỗi lời gọi tool có trần thời gian riêng; không có nó, một tool treo giữ
   request của HR tới 5 phút (mặc định đọc của transport).
"""

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import timedelta

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.exceptions import McpError

log = logging.getLogger(__name__)

MCP_URL = os.getenv("MCP_SERVER_URL", "http://mcp:8001/mcp")
MCP_AUTH_TOKEN = (os.getenv("MCP_AUTH_TOKEN") or "").strip()

# Bắt tay + đọc: giữ ngắn để MCP hỏng thì rơi về fallback nhanh, HR không ngồi đợi.
CONNECT_TIMEOUT = float(os.getenv("MCP_CONNECT_TIMEOUT", "8"))
# Trần cho MỘT lời gọi tool. Tool nặng nhất là generate_interview_questions theo lô:
# mỗi ứng viên một lượt gọi Gemini chạy tuần tự, tối đa 8 người (_MAX_BATCH).
TOOL_TIMEOUT = float(os.getenv("MCP_TOOL_TIMEOUT", "150"))
# Bao lâu thì hỏi lại MCP server danh sách tool. Danh sách gần như không đổi, mà
# list_tools mỗi lượt chat là một vòng round-trip thừa trước cả khi LLM chạy.
TOOLS_CACHE_TTL = float(os.getenv("MCP_TOOLS_CACHE_TTL", "300"))

# Header khai báo HR đang thao tác (server đọc bằng hằng ACTOR_HEADER cùng tên).
ACTOR_HEADER = "X-HireWise-Actor"

# Tham số do backend tiêm, không bao giờ để LLM tự điền. Từ khi danh tính chuyển sang
# header thì server KHÔNG còn phơi tham số nào như vậy nữa; giữ bộ lọc lại làm lưới an
# toàn cho trường hợp chạy với một MCP server bản cũ.
_INJECTED_PARAMS = {"acting_user_id"}

# Tool của riêng server, KHÔNG phải năng lực nghiệp vụ -> không đưa cho LLM.
#
# `health` chỉ có ý nghĩa với người vận hành (docker healthcheck, gỡ lỗi). Đưa nó vào danh sách
# tool của model thì đường MCP có 15 tool còn đường fallback có 14 — đúng kiểu lệch mà
# `tool_registry` sinh ra để dẹp, và model thỉnh thoảng gọi nó thay vì làm việc thật.
_SERVER_ONLY_TOOLS = {"health"}

# Các lỗi có nghĩa "không nói chuyện được với MCP server" (khác với "tool báo lỗi").
_CONNECTION_ERRORS = (
    httpx.HTTPError,
    ConnectionError,
    OSError,
    anyio.BrokenResourceError,
    anyio.ClosedResourceError,
    anyio.EndOfStream,
    asyncio.TimeoutError,
)


class MCPUnavailable(Exception):
    """Không nói chuyện được với MCP server -> caller nên fallback sang tool nội bộ."""


def _headers(acting_user_id=None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {MCP_AUTH_TOKEN}"} if MCP_AUTH_TOKEN else {}
    if acting_user_id:
        headers[ACTOR_HEADER] = str(acting_user_id)
    return headers


@asynccontextmanager
async def mcp_session(acting_user_id=None):
    """Mở 1 phiên MCP (dùng cho cả 1 lượt chat, không mở/đóng mỗi lần gọi tool).

    `acting_user_id` là HR đang đăng nhập; nó đi kèm MỌI request của phiên này dưới
    dạng header. Một phiên = một lượt chat của một người, nên buộc danh tính vào phiên
    là đúng cấp: không lời gọi tool nào trong phiên có thể mang danh tính khác.

    Chỉ lỗi ở GIAI ĐOẠN KẾT NỐI (mở transport + handshake) mới thành `MCPUnavailable`.
    Sau khi bắt tay xong, mọi exception từ thân lệnh `with` được ném NGUYÊN VẸN: nếu
    gộp luôn cả chúng thành "MCP không kết nối được" thì một bug bình thường trong
    agent loop sẽ bị chẩn đoán sai, và `run_agent` chạy lại cả lượt một cách vô ích.
    Mất kết nối GIỮA chừng vẫn được nhận diện — `call_tool` tự ném `MCPUnavailable`.
    """
    if not MCP_AUTH_TOKEN:
        raise MCPUnavailable(
            "Thiếu MCP_AUTH_TOKEN ở phía backend — không thể xác thực với MCP server."
        )
    connected = False
    try:
        async with streamablehttp_client(
            MCP_URL,
            headers=_headers(acting_user_id),
            timeout=timedelta(seconds=CONNECT_TIMEOUT),
            sse_read_timeout=timedelta(seconds=TOOL_TIMEOUT + 30),
        ) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT)
                connected = True
                yield session
    except MCPUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        if connected:
            raise  # lỗi của thân lệnh with (hoặc lúc dọn dẹp) — không phải lỗi kết nối
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


# Cache tiến trình: (thời điểm lấy, schema cho LLM, tên tool hợp lệ).
_tools_cache: tuple[float, list[dict], set[str]] | None = None


async def fetch_tools(session: ClientSession) -> tuple[list[dict], set[str]]:
    """Lấy danh sách tool từ MCP server. Trả (schema cho LLM, tên các tool hợp lệ)."""
    global _tools_cache

    now = time.monotonic()
    if _tools_cache and now - _tools_cache[0] < TOOLS_CACHE_TTL:
        return _tools_cache[1], _tools_cache[2]

    try:
        resp = await asyncio.wait_for(session.list_tools(), timeout=CONNECT_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        raise MCPUnavailable(f"Không lấy được danh sách tool từ MCP: {e}") from e

    usable = [t for t in resp.tools if t.name not in _SERVER_ONLY_TOOLS]
    tools = [_to_llm_schema(t) for t in usable]
    names = {t.name for t in usable}
    _tools_cache = (now, tools, names)
    return tools, names


def invalidate_tools_cache() -> None:
    """Quên schema đã cache (dùng khi phiên MCP hỏng — server có thể vừa đổi)."""
    global _tools_cache
    _tools_cache = None


def _parse_result(res) -> dict:
    """Kết quả MCP -> dict.

    Ưu tiên `structuredContent`: mọi tool của HireWise khai `-> dict[str, Any]` nên
    server gửi kèm bản đã cấu trúc, khỏi phải parse lại chuỗi. Vẫn giữ nhánh text để
    không phụ thuộc hoàn toàn vào một tính năng của server.
    """
    structured = getattr(res, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    texts = [c.text for c in (res.content or []) if getattr(c, "text", None)]
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
    return {"items": items}


async def call_tool(session: ClientSession, name: str, args: dict) -> dict:
    """Gọi 1 tool qua MCP và parse kết quả về dict.

    Ném `MCPUnavailable` nếu MẤT KẾT NỐI (để agent fallback cả lượt); trả
    `{"error": ...}` nếu tool chạy được nhưng báo lỗi nghiệp vụ (để LLM tự xử lý).

    Danh tính KHÔNG đi ở đây mà ở header của phiên — xem `mcp_session`.
    """
    payload = dict(args or {})

    try:
        res = await session.call_tool(
            name, payload, read_timeout_seconds=timedelta(seconds=TOOL_TIMEOUT)
        )
    except _CONNECTION_ERRORS as e:
        invalidate_tools_cache()
        raise MCPUnavailable(f"Mất kết nối MCP khi gọi tool {name}: {e}") from e
    except McpError as e:
        # Timeout ở tầng giao thức cũng là McpError; coi như tool hỏng chứ không phải
        # kết nối chết, vì phiên vẫn dùng tiếp được cho các bước sau.
        log.warning("MCP tool %s lỗi giao thức: %s", name, e)
        return {"error": f"Tool {name} không hoàn thành: {e}"}
    except Exception as e:  # noqa: BLE001
        log.warning("MCP tool %s thất bại: %s", name, e)
        return {"error": f"Gọi tool {name} thất bại: {e}"}

    if getattr(res, "isError", False):
        texts = [c.text for c in (res.content or []) if getattr(c, "text", None)]
        return {"error": "\n".join(texts) or f"Tool {name} báo lỗi."}

    return _parse_result(res)
