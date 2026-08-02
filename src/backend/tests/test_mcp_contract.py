"""
Giao kèo giữa REGISTRY, MCP server và đường fallback.

Đây là bộ test chống lại đúng LỚP LỖI đã từng xảy ra thật: bộ tool được mô tả ở hai
nơi viết tay song song, rồi trôi lệch — `send_interview_invite` có ở bản Groq nhưng
không hề được đăng ký trên MCP server, trong khi system prompt vẫn dặn LLM dùng nó.

Chạy:  docker exec hirewise_mcp python -m pytest /app/tests/test_mcp_contract.py -q
(hoặc bất kỳ container nào có PYTHONPATH=/app và /mcpsrv được mount).
"""

import asyncio
import importlib.util
import inspect
import os
import sys
from pathlib import Path

import pytest

from app.services.ai_agent import agent_tools as T
from app.services.ai_agent import tool_registry as R
from app.services.ai_agent.agent import SYSTEM_PROMPT

# server.py sống ngoài package `app`: trong container nó ở /mcpsrv, còn khi chạy từ
# cây mã nguồn thì ở src/mcp_server/ (anh em với src/backend/).
def _find_server() -> Path | None:
    here = Path(__file__).resolve()
    ung_vien = [Path("/mcpsrv/server.py")]
    ung_vien += [
        parent / "mcp_server" / "server.py" for parent in here.parents
    ]
    return next((p for p in ung_vien if p.exists()), None)


_SERVER_PATH = _find_server()


def _load_server():
    if _SERVER_PATH is None:
        pytest.skip("Không tìm thấy mcp_server/server.py")
    # server.py từ chối khởi động khi thiếu token, nhưng chỉ ở main(); import thì
    # không sao. Vẫn đặt sẵn để _resolve_actor không phàn nàn lúc import.
    os.environ.setdefault("MCP_AUTH_TOKEN", "test-token")
    spec = importlib.util.spec_from_file_location("hirewise_mcp_server", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["hirewise_mcp_server"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def server():
    return _load_server()


@pytest.fixture(scope="module")
def mcp_tools(server):
    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}


# --------------------------------------------------------------------------- #
# Parity: registry <-> MCP server <-> schema cho LLM
# --------------------------------------------------------------------------- #
def test_moi_tool_trong_registry_deu_co_tren_mcp(mcp_tools):
    """Lỗi gốc: một tool có trong registry nhưng quên đăng ký trên MCP server."""
    thieu = {s.name for s in R.REGISTRY} - set(mcp_tools)
    assert not thieu, f"Tool có trong registry nhưng KHÔNG có trên MCP server: {thieu}"


def test_mcp_khong_co_tool_la(mcp_tools):
    """Chiều ngược lại: MCP không được phơi ra thứ gì registry không biết ('health'
    là tool của riêng server, không phải năng lực nghiệp vụ)."""
    la = set(mcp_tools) - {s.name for s in R.REGISTRY} - {"health"}
    assert not la, f"MCP phơi ra tool không có trong registry: {la}"


def test_schema_fallback_khop_voi_mcp(mcp_tools):
    """Hai đường phải cho LLM thấy CÙNG một bộ tool, nếu không lỗi chỉ tái hiện ở một
    đường và cực khó lần ra."""
    fallback = {t["function"]["name"] for t in R.llm_tool_schemas()}
    assert fallback == {s.name for s in R.REGISTRY}
    assert fallback == set(mcp_tools) - {"health"}


def test_tham_so_khop_nhau(mcp_tools):
    """Khớp TUYỆT ĐỐI, không còn ngoại lệ nào.

    Trước đây phải trừ ra `acting_user_id` vì danh tính là một tham số tool. Giờ danh
    tính đi bằng header nên schema chỉ còn đúng những gì LLM được phép điền — nếu một
    tham số "nội bộ" nào lại bò vào schema, test này phải đỏ.
    """
    for spec in R.REGISTRY:
        mcp_props = set((mcp_tools[spec.name].inputSchema.get("properties") or {}))
        assert mcp_props == {p.name for p in spec.params}, spec.name


def test_tham_so_bat_buoc_khop_nhau(mcp_tools):
    for spec in R.REGISTRY:
        mcp_required = set(mcp_tools[spec.name].inputSchema.get("required") or [])
        assert mcp_required == {p.name for p in spec.params if p.required}, spec.name


def test_khong_tool_nao_con_tham_so_danh_tinh(mcp_tools):
    """Danh tính phải đi bằng header, không bao giờ bằng tham số tool.

    Chỉ cần một tool lỡ khai lại `acting_user_id` là LLM nhìn thấy nó và tự điền được
    id của HR khác — chính lỗ hổng mà việc chuyển sang header dựng lên để đóng.
    """
    for name, tool in mcp_tools.items():
        props = set(tool.inputSchema.get("properties") or {})
        assert "acting_user_id" not in props, name


# --------------------------------------------------------------------------- #
# Các bất biến về an toàn
# --------------------------------------------------------------------------- #
def test_moi_tool_deu_chay_ngoai_event_loop(server):
    """CHỐNG HỒI QUY LỖI CHẶN EVENT LOOP.

    FastMCP gọi tool đồng bộ THẲNG trên event loop (mcp 1.12, func_metadata.py). Tool
    của HireWise đều chặn (DB, gọi AI, sleep của rate limiter) nên một tool `def`
    thường là đủ làm cả tiến trình MCP đứng im hàng chục giây: client thứ hai không
    được phục vụ, `/healthz` không trả lời, stream Streamable HTTP đứt giữa chừng.
    """
    for tool in server.mcp._tool_manager.list_tools():
        assert tool.is_async, (
            f"Tool {tool.name} là hàm đồng bộ -> sẽ chặn event loop của MCP server. "
            f"Dùng `async def` + anyio.to_thread.run_sync."
        )


def test_be_mat_chi_gom_tool(server):
    """BỀ MẶT ĐÚNG BẰNG NHU CẦU: chỉ `tools/*`, không resource, không prompt.

    Client duy nhất của server này là agent loop trong `agent.py` — nó lấy dữ liệu
    bằng tool đọc và đã có SYSTEM_PROMPT riêng. `resources/*` và `prompts/*` chỉ có ý
    nghĩa với một app chat đa dụng ở ngoài; thêm chúng vào là thêm code không ai gọi,
    và riêng resource còn là một đường đọc dữ liệu nữa phải tự canh phạm vi owner_id.
    """
    rm = server.mcp._resource_manager
    assert not rm._resources, f"Có resource không nằm trong luồng sản phẩm: {list(rm._resources)}"
    assert not rm._templates, f"Có resource template không dùng tới: {list(rm._templates)}"
    assert not server.mcp._prompt_manager._prompts, "Có prompt không nằm trong luồng sản phẩm"


def test_khong_lo_tham_so_tiem_ra_llm():
    """owner_id/created_by mà lọt vào schema thì LLM có thể tự điền -> đọc dữ liệu
    của HR khác, hoặc mạo danh người tạo."""
    for tool in R.llm_tool_schemas():
        props = set(tool["function"]["parameters"].get("properties") or {})
        assert not props & set(R.INJECTED_KWARGS), tool["function"]["name"]


def test_moi_tool_deu_tra_ve_dict(mcp_tools):
    """mcp>=1.10 validate kết quả theo annotation trả về. Khai `-> list[dict]` rồi trả
    dict lỗi sẽ biến thành ToolError, LLM chỉ nhận stack trace pydantic."""
    for spec in R.REGISTRY:
        ret = inspect.signature(spec.fn).return_annotation
        assert ret is dict, f"{spec.name} phải khai `-> dict`, đang là {ret!r}"
    for name, tool in mcp_tools.items():
        schema = tool.outputSchema
        assert schema is None or schema.get("type") == "object", name


def test_tool_ghi_khong_bi_danh_dau_read_only():
    """readOnlyHint sai là nguy hiểm: `agent.py` dựa vào nó để biết lượt vừa rồi đã có
    tác dụng phụ nào chưa, tức có được phép chạy lại cả lượt ở đường fallback không."""
    for spec in R.REGISTRY:
        if spec.read_only:
            assert not spec.user_bound, f"{spec.name}: tool ghi (user_bound) không thể read_only"
            assert not spec.destructive, f"{spec.name}: vừa read_only vừa destructive"


def test_annotation_len_toi_mcp(mcp_tools):
    for spec in R.REGISTRY:
        ann = mcp_tools[spec.name].annotations
        assert ann is not None, spec.name
        assert ann.readOnlyHint == spec.read_only, spec.name
        assert ann.destructiveHint == spec.destructive, spec.name
        assert ann.idempotentHint == spec.idempotent, spec.name


def test_hanh_dong_khong_dao_nguoc_deu_co_rao_xac_nhan():
    """Mọi tool `destructive` phải có một cờ để agent buộc phải hỏi HR trước."""
    rao = {
        "send_interview_invite": "confirm",
        "generate_interview_questions": "replace",
        "record_interview_answers": "replace",
        "finish_interview": "confirm",
        "send_decision_emails": "confirm",
    }
    for spec in R.REGISTRY:
        if not spec.destructive:
            continue
        co = rao.get(spec.name)
        assert co, f"{spec.name} là destructive nhưng chưa khai cờ xác nhận trong test"
        p = next((p for p in spec.params if p.name == co), None)
        assert p is not None and p.default is False, f"{spec.name}.{co} phải mặc định False"


# --------------------------------------------------------------------------- #
# System prompt không được nhắc tới tool không tồn tại
# --------------------------------------------------------------------------- #
def test_system_prompt_chi_nhac_tool_co_that(mcp_tools):
    """Chính lỗi cũ: prompt dặn LLM dùng send_interview_invite trong khi MCP không có
    tool đó, nên trên đường chính agent chỉ có thể bịa là đã gửi."""
    import re

    nhac = set(re.findall(r"\b([a-z_]+(?:_[a-z]+)+)\b", SYSTEM_PROMPT))
    ung_vien = nhac & (
        {s.name for s in R.REGISTRY}
        | {"send_interview_invite", "generate_interview_questions", "add_to_shortlist"}
    )
    thieu = ung_vien - set(mcp_tools)
    assert not thieu, f"SYSTEM_PROMPT nhắc tới tool không có trên MCP: {thieu}"


# --------------------------------------------------------------------------- #
# Không còn hồi quy: các lỗi thật đã sửa
# --------------------------------------------------------------------------- #
def test_list_jds_tra_envelope_dict():
    """Từng khai `-> list[dict]`; nhánh lỗi trả dict làm vỡ validate outputSchema."""
    assert inspect.signature(T.list_jds).return_annotation is dict


def test_run_async_chay_duoc_ben_trong_event_loop():
    """`send_interview_invite` gọi coroutine gửi mail từ code sync, mà nó lại nằm
    trong agent loop async -> asyncio.run() cũ luôn ném RuntimeError."""

    async def ket_qua():
        return 42

    async def trong_loop():
        return T._run_async(ket_qua())

    assert asyncio.run(trong_loop()) == 42
    assert T._run_async(ket_qua()) == 42  # ngoài loop cũng phải chạy
