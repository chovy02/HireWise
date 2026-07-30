"""
Các BẤT BIẾN LÚC CHẠY của lớp MCP: xác thực, danh tính, phạm vi dữ liệu, giao kèo
client.

Khác với `test_mcp_contract.py` (chỉ so schema giữa registry / MCP server / đường
fallback), bộ này gọi thẳng vào các hàm quyết định AI ĐƯỢC LÀM GÌ. Trước đó những
bảo đảm đó chỉ tồn tại trong docstring: không có test nào chứng minh rằng thiếu token
thì bị 401, rằng tài khoản bị khoá thì bị từ chối, hay rằng `owner_id` do client gửi
lên bị vứt đi.

Không cần DB, không cần mạng: mọi thứ đụng tới hạ tầng đều được thay bằng bản giả.

Chạy:  docker exec hirewise_mcp python -m pytest /app/tests/test_mcp_runtime.py -q
"""

import asyncio
import importlib.util
import os
import sys
import types
import uuid
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from starlette.testclient import TestClient

from app.services.ai_agent import mcp_client
from app.services.ai_agent import tool_registry as R


# --------------------------------------------------------------------------- #
# Nạp server.py (nằm ngoài package `app`) — xem chú thích trong test_mcp_contract.
# --------------------------------------------------------------------------- #
def _find_server() -> Path | None:
    here = Path(__file__).resolve()
    ung_vien = [Path("/mcpsrv/server.py")]
    ung_vien += [parent / "mcp_server" / "server.py" for parent in here.parents]
    return next((p for p in ung_vien if p.exists()), None)


@pytest.fixture(scope="module")
def server():
    path = _find_server()
    if path is None:
        pytest.skip("Không tìm thấy mcp_server/server.py")
    os.environ.setdefault("MCP_AUTH_TOKEN", "test-token")
    spec = importlib.util.spec_from_file_location("hirewise_mcp_server", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["hirewise_mcp_server"] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# Bản giả của DB và User
# --------------------------------------------------------------------------- #
def _user(role="hr_staff", is_banned=False, email="hr@hirewise.vn", uid=None):
    return types.SimpleNamespace(
        id=uid or uuid.uuid4(), role=role, is_banned=is_banned, email=email
    )


class FakeQuery:
    def __init__(self, ket_qua):
        self._ket_qua = ket_qua

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return self._ket_qua


class FakeDB:
    """Đủ dùng cho `_resolve_actor` và `_run`: get / query / rollback / close."""

    def __init__(self, by_id=None, by_email=None):
        self._by_id = by_id
        self._by_email = by_email
        self.rolled_back = False
        self.closed = False

    def get(self, _model, _uid):
        return self._by_id

    def query(self, _model):
        return FakeQuery(self._by_email)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


# --------------------------------------------------------------------------- #
# XÁC THỰC — BearerAuthMiddleware
# --------------------------------------------------------------------------- #
@pytest.fixture
def auth_client(server):
    """App ASGI tí hon nằm sau middleware xác thực."""

    async def app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        })
        await send({"type": "http.response.body", "body": b"ok"})

    return TestClient(server.BearerAuthMiddleware(app, "token-that"))


def test_thieu_token_thi_401(auth_client):
    """Endpoint này đọc/ghi thẳng dữ liệu tuyển dụng: không token = không vào."""
    resp = auth_client.get("/mcp")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_sai_token_thi_401(auth_client):
    resp = auth_client.get("/mcp", headers={"Authorization": "Bearer token-sai"})
    assert resp.status_code == 401


def test_token_dung_tien_dung_thi_qua_duoc(auth_client):
    resp = auth_client.get("/mcp", headers={"Authorization": "Bearer token-that"})
    assert resp.status_code == 200


def test_token_dung_tien_to_van_bi_tu_choi(auth_client):
    """So sánh phải trên TOÀN CHUỖI: 'Bearer token-that-nhung-dai-hon' không hợp lệ."""
    resp = auth_client.get(
        "/mcp", headers={"Authorization": "Bearer token-that-nhung-dai-hon"}
    )
    assert resp.status_code == 401


def test_healthz_khong_can_token(auth_client):
    """Docker healthcheck không cầm token; /healthz chỉ trả trạng thái, không dữ liệu."""
    resp = auth_client.get("/healthz")
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# DANH TÍNH — _resolve_actor
# --------------------------------------------------------------------------- #
def test_danh_tinh_hop_le_thi_qua(server):
    u = _user()
    assert server._resolve_actor(FakeDB(by_id=u), str(u.id)) is u


def test_id_khong_phai_uuid_thi_tu_choi(server):
    with pytest.raises(server.IdentityError):
        server._resolve_actor(FakeDB(), "khong-phai-uuid")


def test_id_khong_ung_voi_tai_khoan_nao_thi_tu_choi(server):
    with pytest.raises(server.IdentityError):
        server._resolve_actor(FakeDB(by_id=None), str(uuid.uuid4()))


def test_tai_khoan_khong_co_quyen_tuyen_dung_thi_tu_choi(server):
    """Ứng viên/tài khoản thường không được thao tác dữ liệu tuyển dụng."""
    u = _user(role="candidate")
    with pytest.raises(server.IdentityError):
        server._resolve_actor(FakeDB(by_id=u), str(u.id))


def test_tai_khoan_bi_khoa_thi_tu_choi(server):
    u = _user(is_banned=True)
    with pytest.raises(server.IdentityError):
        server._resolve_actor(FakeDB(by_id=u), str(u.id))


def test_khong_header_thi_tu_choi(server):
    """KHÔNG được âm thầm mượn một tài khoản nào đó — thà từ chối.

    Không có nhánh "danh tính mặc định" nào để rơi vào: mọi thao tác phải thuộc về HR
    đang đăng nhập ở `api`, và `api` là thứ duy nhất đặt header này.
    """
    with pytest.raises(server.IdentityError):
        server._resolve_actor(FakeDB(), "")


def test_khong_con_danh_tinh_dung_chung(server):
    """CHỐNG HỒI QUY. Bản trước có MCP_DEFAULT_USER_EMAIL: một tài khoản dùng chung để
    client MCP chạy ngoài web vẫn thao tác được. Đó là đường vào không qua đăng nhập,
    và nó làm audit trail ghi tên tài khoản dùng chung thay vì người thật đã bấm.

    Nếu nó quay lại, `_resolve_actor` sẽ trả về user dù không có header — test ở trên
    đỏ; test này chặn cả việc cấu hình đó lặng lẽ bò về dưới một cái tên khác.
    """
    assert not hasattr(server, "DEFAULT_USER_EMAIL")
    u = _user()
    # Có sẵn một tài khoản tra theo email vẫn KHÔNG được dùng khi thiếu header.
    with pytest.raises(server.IdentityError):
        server._resolve_actor(FakeDB(by_email=u), "")


def test_khong_co_request_thi_khong_co_danh_tinh(server):
    """Ngoài ngữ cảnh HTTP thì `_actor_ref_from_request` phải trả "" chứ không nổ."""
    assert server._actor_ref_from_request() == ""


# --------------------------------------------------------------------------- #
# PHẠM VI DỮ LIỆU + phân loại lỗi — _run
# --------------------------------------------------------------------------- #
@pytest.fixture
def chay_tool(server, monkeypatch):
    """Trả về `(goi, da_ghi_log)`: gọi `_run` với DB giả và ghi lại audit log."""
    actor = _user()
    monkeypatch.setattr(server, "SessionLocal", lambda: FakeDB(by_id=actor))
    monkeypatch.setattr(server, "_resolve_actor", lambda db, ref: actor)

    da_ghi_log = []
    monkeypatch.setattr(server, "write_tool_log", lambda **kw: da_ghi_log.append(kw))

    def goi(fn, kwargs, **spec_kw):
        spec = R.ToolSpec(
            name="tool_thu", fn=fn, title="Tool thử", description="", **spec_kw
        )
        return server._run(spec, kwargs, str(actor.id))

    return types.SimpleNamespace(goi=goi, logs=da_ghi_log, actor=actor)


def test_owner_id_do_client_gui_len_bi_vut_di(chay_tool):
    """PHẠM VI DỮ LIỆU. `owner_id` không nằm trong schema, nên nếu nó xuất hiện trong
    tham số thì đó là giá trị bịa — phải bị GHI ĐÈ, không phải được tôn trọng."""
    nhan = {}

    def fn(db, **kwargs):
        nhan.update(kwargs)
        return {"ok": True}

    chay_tool.goi(fn, {"owner_id": str(uuid.uuid4()), "jd_id": "Backend"})

    assert nhan["owner_id"] == str(chay_tool.actor.id)
    assert nhan["jd_id"] == "Backend"


def test_user_bound_duoc_tiem_tu_danh_tinh(chay_tool):
    """Tool ghi phải ghi tên ĐÚNG người đang thao tác, không phải người LLM chọn."""
    nhan = {}

    def fn(db, **kwargs):
        nhan.update(kwargs)
        return {"ok": True}

    chay_tool.goi(fn, {"created_by": str(uuid.uuid4())}, user_bound="created_by")

    assert nhan["created_by"] == str(chay_tool.actor.id)


def test_loi_he_thong_thanh_ToolError(chay_tool):
    """Exception ngoài dự liệu -> ToolError -> FastMCP đánh dấu isError=True.

    Bản trước trả về `{"error": ...}` như một kết quả THÀNH CÔNG, nên phía gọi nhìn
    vào tưởng tool chạy trót lọt trong khi nó vừa nổ.
    """

    def fn(db, **_kwargs):
        raise RuntimeError("DB sập")

    with pytest.raises(ToolError, match="DB sập"):
        chay_tool.goi(fn, {})

    assert chay_tool.logs[-1]["status"] == "error"


def test_loi_nghiep_vu_van_la_ket_qua_binh_thuong(chay_tool):
    """"Không tìm thấy JD" là câu trả lời, không phải sự cố: LLM phải nhận được nó để
    nói lại cho HR, chứ không phải một CallToolResult lỗi."""
    ket_qua = chay_tool.goi(lambda db, **_k: {"error": "Không tìm thấy JD."}, {})

    assert ket_qua == {"error": "Không tìm thấy JD."}
    assert chay_tool.logs[-1]["status"] == "error"


def test_ket_qua_khong_phai_dict_thi_duoc_boc_lai(chay_tool):
    """mcp>=1.10 validate kết quả theo annotation `-> dict`; trả list trần là vỡ."""
    assert chay_tool.goi(lambda db, **_k: [1, 2], {}) == {"result": [1, 2]}


def test_danh_tinh_hong_thi_khong_goi_tool(chay_tool, server, monkeypatch):
    """Không xác minh được người dùng thì tool KHÔNG được chạy, dù chỉ là tool đọc."""
    monkeypatch.setattr(
        server, "_resolve_actor",
        lambda db, ref: (_ for _ in ()).throw(server.IdentityError("tài khoản bị khoá")),
    )
    da_chay = []

    with pytest.raises(ToolError, match="Không được phép"):
        chay_tool.goi(lambda db, **_k: da_chay.append(1) or {}, {})

    assert not da_chay


# --------------------------------------------------------------------------- #
# GIAO KÈO PHÍA CLIENT — mcp_client
# --------------------------------------------------------------------------- #
class FakeTool:
    def __init__(self, name, props=None, required=None):
        self.name = name
        self.description = f"mô tả {name}"
        self.inputSchema = {
            "type": "object",
            "properties": props or {"jd_id": {"type": "string"}},
        }
        if required is not None:
            self.inputSchema["required"] = required


class FakeSession:
    def __init__(self, tools):
        self._tools = tools

    async def list_tools(self):
        return types.SimpleNamespace(tools=self._tools)


def _fetch(tools):
    mcp_client.invalidate_tools_cache()
    try:
        return asyncio.run(mcp_client.fetch_tools(FakeSession(tools)))
    finally:
        mcp_client.invalidate_tools_cache()


def test_health_khong_bao_gio_den_tay_llm():
    """`health` là tool của người vận hành. Lọt vào danh sách của model thì đường MCP
    và đường fallback lệch nhau — đúng loại lỗi mà tool_registry sinh ra để dẹp."""
    schemas, names = _fetch([FakeTool("list_jds"), FakeTool("health")])

    assert names == {"list_jds"}
    assert [s["function"]["name"] for s in schemas] == ["list_jds"]


def test_tham_so_noi_bo_bi_loc_khoi_schema_cua_llm():
    """Lưới an toàn cho trường hợp chạy với MCP server bản cũ (còn acting_user_id)."""
    tool = FakeTool(
        "get_jd",
        props={"jd_id": {"type": "string"}, "acting_user_id": {"type": "string"}},
        required=["jd_id", "acting_user_id"],
    )
    schemas, _ = _fetch([tool])
    params = schemas[0]["function"]["parameters"]

    assert "acting_user_id" not in params["properties"]
    assert params["required"] == ["jd_id"]


def test_header_danh_tinh_duoc_gan_vao_phien():
    uid = uuid.uuid4()
    headers = mcp_client._headers(uid)

    assert headers[mcp_client.ACTOR_HEADER] == str(uid)


def test_khong_co_danh_tinh_thi_khong_gan_header():
    """Không bịa danh tính: thiếu user thì gửi request KHÔNG header và để server từ chối.

    Trên web thì `user_id` luôn có (router lấy từ `get_current_user`), nên nhánh này là
    lưới an toàn: thà thất bại rõ ràng ở server còn hơn client tự điền một id nào đó.
    """
    assert mcp_client.ACTOR_HEADER not in mcp_client._headers(None)


# --------------------------------------------------------------------------- #
# Đọc kết quả tool — _parse_result
# --------------------------------------------------------------------------- #
def _res(structured=None, texts=()):
    content = [types.SimpleNamespace(text=t) for t in texts]
    return types.SimpleNamespace(structuredContent=structured, content=content)


def test_uu_tien_structured_content():
    assert mcp_client._parse_result(_res(structured={"count": 2})) == {"count": 2}


def test_parse_mot_khoi_text_json():
    assert mcp_client._parse_result(_res(texts=['{"count": 2}'])) == {"count": 2}


def test_parse_nhieu_khoi_text_rieng_le():
    """FastMCP tách MỖI phần tử của list thành 1 text block: phải parse từng khối,
    nối chuỗi rồi mới parse là hỏng JSON."""
    ket_qua = mcp_client._parse_result(_res(texts=['{"a": 1}', '{"a": 2}']))

    assert ket_qua == {"items": [{"a": 1}, {"a": 2}]}


def test_text_khong_phai_json_van_khong_lam_vo():
    assert mcp_client._parse_result(_res(texts=["hỏng"])) == {"result": "hỏng"}


def test_khong_co_noi_dung_thi_tra_dict_rong():
    assert mcp_client._parse_result(_res()) == {}
