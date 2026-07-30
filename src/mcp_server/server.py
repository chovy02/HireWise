"""
HireWise MCP Server (Streamable HTTP, cổng 8001)
================================================

Phơi các năng lực tuyển dụng THẬT của HireWise ra cho MỘT client duy nhất: web Copilot
của chính HireWise (qua `app.services.ai_agent.mcp_client`).

SERVICE NỘI BỘ, KHÔNG PHẢI CỔNG CÔNG KHAI. Cổng 8001 cố ý không publish ra host
(xem docker-compose.yml) — chỉ container `api` gọi tới, qua tên `mcp` trong network của
Docker. Đây là sản phẩm web: đường vào duy nhất của người dùng là đăng nhập ở `api`,
không phải nói chuyện thẳng với MCP server.

BỀ MẶT ĐÚNG BẰNG NHU CẦU CỦA SẢN PHẨM: chỉ `tools/list` + `tools/call`. Không resource,
không prompt, không `instructions`, không danh tính dùng chung — những thứ đó chỉ có
nghĩa với một app chat đa dụng ở ngoài, tự đi tìm dữ liệu và tự soạn prompt. HireWise
KHÔNG có luồng đó: người dùng nói chuyện với agent qua khung chat trên web, và chính
`agent.py` là thứ chọn tool rồi soạn prompt. Giữ chúng lại chỉ tạo ra code không ai
gọi, và riêng `instructions` còn là một bản sao thứ hai của SYSTEM_PROMPT trong
`agent.py` — đúng kiểu hai bản mô tả song song rồi trôi lệch mà `tool_registry` được
dựng ra để dẹp.

Server này KHÔNG mô tả tool lần thứ hai. Nó duyệt `app.services.ai_agent.tool_registry`
— nguồn sự thật duy nhất — rồi tự dựng hàm có đúng chữ ký và đăng ký với FastMCP. Thêm
tool = thêm 1 `ToolSpec` trong registry, ở đây không phải sửa gì.

Chạy trong container `mcp` (build từ image backend, mount ./src/backend vào /app,
PYTHONPATH=/app) nên import được app.*. Kết nối DB qua DATABASE_URL trong .env.

BA ĐIỂM AN TOÀN
---------------
1. XÁC THỰC. Cổng này nói chuyện thẳng với DB tuyển dụng, nên mọi request phải mang
   `Authorization: Bearer $MCP_AUTH_TOKEN`. Thiếu biến môi trường -> server TỪ CHỐI
   khởi động (im lặng chạy tiếp là cách sinh ra một endpoint đọc/ghi ẩn danh).
2. DANH TÍNH. Ai đang thao tác được khai qua HEADER `X-HireWise-Actor` của chính
   request, KHÔNG phải qua tham số tool — xem `_actor_ref_from_request`. Danh tính đó
   vẫn được XÁC MINH với bảng users (tồn tại, đúng vai trò, chưa bị khoá) chứ không
   tin suông. KHÔNG CÓ ĐƯỜNG NÀO KHÁC: không header thì từ chối, không có danh tính
   mặc định để mượn. Mọi thao tác phải thuộc về đúng HR đang đăng nhập ở `api`.
3. PHẠM VI DỮ LIỆU. `owner_id` được tiêm vào MỌI tool ở `_run` (không chỉ tool ghi),
   nên một tool mới thêm sau này không thể vô tình đọc dữ liệu của HR khác.

MỌI TOOL CHẠY TRONG WORKER THREAD
---------------------------------
FastMCP gọi tool đồng bộ THẲNG trên event loop (mcp 1.12: `func_metadata.py`,
`if fn_is_async: await fn(...) else: fn(...)`). Mà tool ở đây là code chặn: query DB
psycopg2, gọi Gemini/Groq, `time.sleep` của rate limiter. Để nguyên thì một lượt
`generate_interview_questions` cho 8 ứng viên giữ loop hàng chục giây — cả tiến trình
đứng im: client thứ hai không được đọc request, `/healthz` không trả lời (docker đánh
dấu unhealthy), và stream Streamable HTTP không gửi nổi keep-alive nên phiên đứt giữa
chừng. Vì vậy mọi tool ở đây là `async def` và đẩy phần chặn qua
`anyio.to_thread.run_sync`.
"""

import contextlib
import hmac
import inspect
import logging
import os
import sys
import uuid as uuid_mod
from functools import partial
from typing import Annotated, Any, Literal

import anyio
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy import text as sql_text
from starlette.responses import JSONResponse

from app.database import SessionLocal
from app import models
from app.services.ai_agent import tool_registry as R
from app.services.logging import write_tool_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hirewise.mcp")

HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8001"))
AUTH_TOKEN = (os.getenv("MCP_AUTH_TOKEN") or "").strip()

# Header khai báo HR đang thao tác, do backend HireWise đặt khi mở phiên MCP.
#
# VÌ SAO LÀ HEADER CHỨ KHÔNG PHẢI THAM SỐ TOOL: bản trước nhận `acting_user_id` như
# một tham số bình thường, nên nó nằm trong inputSchema mà LLM nhìn thấy — phải nhớ
# lọc nó ở phía client, và chỉ cần quên một chỗ là model tự điền được id người khác.
# Danh tính là thuộc tính của KẾT NỐI (ai đang đăng nhập), không phải của lời gọi tool,
# nên chỗ đúng của nó là header. Lợi thêm: schema sạch, không còn tham số "nội bộ" nào
# để lọc.
#
# LƯU Ý PHẠM VI: header này chỉ loại LLM ra khỏi việc chọn danh tính. Ai cầm được
# MCP_AUTH_TOKEN vẫn tự đặt được header, nên token phải được coi là bí mật cấp hệ
# thống; muốn chặt hơn thì phải cấp token riêng cho từng client và buộc token vào một
# danh tính cố định.
ACTOR_HEADER = "x-hirewise-actor"

# Không truyền `instructions`: client duy nhất của server này là web Copilot, và nó đã
# có SYSTEM_PROMPT riêng trong `agent.py`. Khai lần nữa ở đây chỉ tạo bản sao thứ hai
# của cùng một bộ quy ước, để rồi sửa một bên quên bên kia.
mcp = FastMCP("HireWise MCP Server", host=HOST, port=PORT)


# --------------------------------------------------------------------------- #
# Danh tính
# --------------------------------------------------------------------------- #
class IdentityError(Exception):
    """Không xác định được HR nào đang thao tác -> từ chối, KHÔNG đoán."""


def _actor_ref_from_request() -> str:
    """Đọc `X-HireWise-Actor` của request đang xử lý; "" nếu client không khai.

    `request_context.request` là đối tượng Request của Starlette, do transport
    Streamable HTTP đính kèm vào từng message. Ngoài ngữ cảnh một request (vd gọi
    trực tiếp trong test) thì không có gì để đọc -> trả "", và `_resolve_actor` sẽ từ
    chối vì không có danh tính nào để mượn.
    """
    try:
        request = mcp.get_context().request_context.request
    except (LookupError, ValueError, AttributeError):
        return ""
    headers = getattr(request, "headers", None)
    if headers is None:
        return ""
    return (headers.get(ACTOR_HEADER) or "").strip()


def _resolve_actor(db, acting_user_id: str) -> models.User:
    """Đổi id HR ở header ACTOR_HEADER thành một User đã xác minh.

    Xác minh chứ không tin suông: id do CLIENT gửi lên. Client hợp lệ duy nhất trong
    kiến trúc này là backend HireWise (đã kèm bearer token) nhưng vẫn kiểm tra vai trò
    và trạng thái khoá — token bị lộ thì đây là lớp phòng thủ còn lại.

    KHÔNG CÓ DANH TÍNH MẶC ĐỊNH: thiếu header = từ chối. Bản trước có một
    MCP_DEFAULT_USER_EMAIL để một client MCP chạy ngoài web vẫn thao tác được, nhưng
    đó là một đường vào KHÔNG qua đăng nhập, và mọi việc nó làm bị audit trail ghi cho
    một tài khoản dùng chung chứ không phải người thật đã bấm.
    """
    ref = (acting_user_id or "").strip()
    if not ref:
        raise IdentityError(
            f"Không xác định được người dùng: request thiếu header {ACTOR_HEADER}."
        )
    try:
        uid = uuid_mod.UUID(ref)
    except (ValueError, AttributeError, TypeError):
        raise IdentityError(f"{ACTOR_HEADER} không phải UUID hợp lệ: {ref!r}")
    user = db.get(models.User, uid)
    if user is None:
        raise IdentityError(f"{ACTOR_HEADER} không ứng với tài khoản nào.")

    if user.role not in ("admin", "hr_staff"):
        raise IdentityError(f"Tài khoản {user.email} không có quyền tuyển dụng.")
    if user.is_banned:
        raise IdentityError(f"Tài khoản {user.email} đang bị khoá.")
    return user


# --------------------------------------------------------------------------- #
# Thực thi tool
# --------------------------------------------------------------------------- #
def _run(spec: R.ToolSpec, kwargs: dict, acting_user_id: str) -> dict[str, Any]:
    """Mở 1 session DB, xác minh danh tính, gọi tool, ghi audit trail, đóng session.

    Hàm này CHẶN (DB + gọi AI) nên luôn được chạy trong worker thread — xem docstring
    đầu module.

    HAI LOẠI LỖI, HAI CÁCH TRẢ:
      - Lỗi NGHIỆP VỤ (tool chạy xong và tự trả `{"error": "Không tìm thấy JD."}`):
        trả về như kết quả bình thường để LLM tự xử lý và nói lại cho HR.
      - Lỗi HỆ THỐNG (không xác định được danh tính, exception ngoài dự liệu): ném
        `ToolError` -> FastMCP đánh dấu `isError=True` trên CallToolResult. Bản trước
        gộp cả hai thành một dict "thành công", nên phía gọi chỉ thấy tool chạy trót
        lọt trong khi thực ra nó đã nổ.

    Nhánh thành công LUÔN trả `dict` — mọi tool khai `-> dict[str, Any]`, mà mcp>=1.10
    validate kết quả theo annotation đó.
    """
    db = SessionLocal()
    actor_id = None
    # Lời nhắn lỗi HỆ THỐNG; None nghĩa là tool đã chạy tới nơi tới chốn (dù kết quả
    # của nó có thể là một lỗi nghiệp vụ).
    failure: str | None = None
    try:
        actor = _resolve_actor(db, acting_user_id)
        actor_id = str(actor.id)

        call = dict(kwargs)
        if spec.user_bound:
            call[spec.user_bound] = actor_id
        # Phạm vi dữ liệu: GHI ĐÈ chứ không setdefault — owner_id không nằm trong
        # schema đưa cho LLM, nên nếu nó vẫn xuất hiện thì đó là giá trị bịa.
        call["owner_id"] = actor_id

        result = spec.fn(db, **call)
        if not isinstance(result, dict):  # giao kèo bị vi phạm -> bọc lại, đừng vỡ
            result = {"result": result}
    except IdentityError as e:
        db.rollback()
        failure = f"Không được phép: {e}"
        result = {"error": failure}
    except Exception as e:  # noqa: BLE001 - ghi log rồi mới ném lại dưới dạng ToolError
        db.rollback()
        log.exception("Tool %s thất bại", spec.name)
        failure = f"{type(e).__name__}: {e}"
        result = {"error": failure}
    finally:
        db.close()

    failed = failure is not None or "error" in result
    write_tool_log(
        tool_name=spec.name,
        input_params=kwargs,
        result=result,
        status="error" if failed else "success",
        user_id=actor_id,
    )
    if failure is not None:
        raise ToolError(failure)
    return result


def _annotation_for(p: R.Param):
    """Kiểu Python cho 1 tham số, kèm mô tả -> FastMCP sinh JSON Schema từ đây."""
    base: Any = Literal[p.enum] if p.enum else p.type  # type: ignore[valid-type]
    # Tham số mặc định None (vd candidate_ids) phải là Optional, nếu không pydantic
    # từ chối chính giá trị mặc định của nó.
    if not p.required and p.default is None:
        base = base | None
    return Annotated[base, Field(description=p.description)]


def _build_tool(spec: R.ToolSpec):
    """Dựng một hàm có ĐÚNG chữ ký mà FastMCP cần, từ mô tả trong registry.

    FastMCP đọc chữ ký bằng `inspect.signature()` (tôn trọng `__signature__`) nên hàm
    dựng động vẫn sinh ra inputSchema đầy đủ: kiểu, mô tả, giá trị mặc định, required.

    `async def` là BẮT BUỘC, không phải sở thích: FastMCP chỉ nhả event loop cho tool
    async (`_is_async_callable` -> `inspect.iscoroutinefunction`). Xem docstring đầu
    module về việc vì sao chạy tool đồng bộ trên loop làm chết cả tiến trình.
    """

    async def impl(**kwargs: Any) -> dict[str, Any]:
        # Đọc header TRƯỚC khi rời event loop: `request_context` là một ContextVar gắn
        # với task đang xử lý request.
        acting = _actor_ref_from_request()
        return await anyio.to_thread.run_sync(partial(_run, spec, kwargs, acting))

    P = inspect.Parameter
    # Tham số bắt buộc trước, tuỳ chọn sau — không bắt buộc với KEYWORD_ONLY nhưng
    # giữ thứ tự này để schema đọc ra giống hệt bản viết tay trước đây.
    ordered = sorted(spec.params, key=lambda p: not p.required)
    params = [
        P(
            p.name,
            P.KEYWORD_ONLY,
            default=P.empty if p.required else p.default,
            annotation=_annotation_for(p),
        )
        for p in ordered
    ]
    # KHÔNG có tham số danh tính ở đây: nó đi bằng header ACTOR_HEADER. Nhờ vậy
    # inputSchema chỉ còn đúng những gì LLM được phép điền, và không chỗ nào phải nhớ
    # lọc bớt trước khi đưa schema cho model. Client cũ còn gửi kèm `acting_user_id`
    # thì pydantic bỏ qua (model tham số mặc định `extra='ignore'`), không vỡ.
    impl.__signature__ = inspect.Signature(params, return_annotation=dict[str, Any])
    impl.__name__ = spec.name
    impl.__doc__ = spec.description
    return impl


for _spec in R.REGISTRY:
    mcp.add_tool(
        _build_tool(_spec),
        name=_spec.name,
        title=_spec.title,
        description=_spec.description,
        annotations=ToolAnnotations(
            title=_spec.title,
            readOnlyHint=_spec.read_only,
            destructiveHint=_spec.destructive,
            idempotentHint=_spec.idempotent,
            openWorldHint=_spec.open_world,
        ),
    )
log.info("Đã đăng ký %d tool từ tool_registry: %s",
         len(R.REGISTRY), ", ".join(s.name for s in R.REGISTRY))


# --------------------------------------------------------------------------- #
# Tool riêng của server (không phải năng lực nghiệp vụ nên không nằm trong registry)
# --------------------------------------------------------------------------- #
@mcp.tool(
    title="Kiểm tra tình trạng server",
    annotations=ToolAnnotations(title="Kiểm tra tình trạng server", readOnlyHint=True, idempotentHint=True),
)
async def health() -> dict[str, Any]:
    """Kiểm tra MCP server + kết nối DB."""
    return await anyio.to_thread.run_sync(_health_sync)


def _health_sync() -> dict[str, Any]:
    db = SessionLocal()
    try:
        return {
            "status": "ok",
            "tools": len(R.REGISTRY) + 1,
            "job_descriptions": db.query(models.JobDescription).count(),
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


# KHÔNG CÓ RESOURCE VÀ PROMPT Ở ĐÂY — CỐ Ý.
#
# `resources/*` (dữ liệu để client tự đính kèm vào hội thoại) và `prompts/*` (mẫu câu
# lệnh để client hiện thành lệnh sẵn dùng) chỉ có tác dụng khi client là một app chat
# đa dụng ở ngoài. Client duy nhất của server này là agent loop trong `agent.py`: nó
# lấy dữ liệu bằng chính các tool đọc ở trên và đã có SYSTEM_PROMPT riêng, nên hai bề
# mặt kia là code không ai gọi — mà vẫn phải bảo trì, và vẫn là một đường đọc dữ liệu
# nữa cần tự canh phạm vi `owner_id`.


# --------------------------------------------------------------------------- #
# HTTP: xác thực bearer token + healthcheck
# --------------------------------------------------------------------------- #
class BearerAuthMiddleware:
    """Chặn mọi request không mang đúng `Authorization: Bearer <token>`.

    Viết ở tầng ASGI (không dùng BaseHTTPMiddleware) để không đụng vào luồng streaming
    của Streamable HTTP. `/healthz` được miễn để docker healthcheck không cần token.
    """

    PUBLIC_PATHS = frozenset({"/healthz"})

    def __init__(self, app, token: str):
        self.app = app
        self._expected = f"Bearer {token}"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in self.PUBLIC_PATHS:
            return await self.app(scope, receive, send)

        header = ""
        for key, value in scope.get("headers") or ():
            if key == b"authorization":
                header = value.decode("latin-1")
                break

        # compare_digest: so sánh thời gian hằng định, không rò rỉ độ dài/tiền tố token.
        if not hmac.compare_digest(header, self._expected):
            response = JSONResponse(
                {"error": "unauthorized", "detail": "Thiếu hoặc sai MCP_AUTH_TOKEN."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            return await response(scope, receive, send)

        await self.app(scope, receive, send)


def _ping_db() -> None:
    db = SessionLocal()
    try:
        db.execute(sql_text("SELECT 1"))
    finally:
        with contextlib.suppress(Exception):
            db.close()


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request):
    """Cho docker healthcheck: chỉ khẳng định tiến trình sống và DB nhận kết nối.

    Cú `SELECT 1` cũng phải rời event loop: đây chính là endpoint cần trả lời ĐƯỢC
    trong lúc một tool nặng đang chạy, nên nó không được góp thêm một lần chặn nữa.
    """
    try:
        await anyio.to_thread.run_sync(_ping_db)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)
    return JSONResponse({"status": "ok", "tools": len(R.REGISTRY) + 1})


def main() -> None:
    if not AUTH_TOKEN:
        log.critical(
            "Thiếu MCP_AUTH_TOKEN. Server này đọc/ghi thẳng dữ liệu tuyển dụng nên "
            "không được phép chạy không xác thực. Đặt MCP_AUTH_TOKEN trong .env "
            "(gợi ý: python -c \"import secrets;print(secrets.token_urlsafe(32))\")."
        )
        sys.exit(1)

    log.info(
        "Danh tính đi bằng header %s và KHÔNG có danh tính mặc định: request không khai "
        "HR đang đăng nhập sẽ bị từ chối.", ACTOR_HEADER
    )

    # Streamable HTTP (endpoint /mcp) — transport hiện hành của MCP; SSE đã bị đánh
    # dấu deprecated trong đặc tả. Dựng app rồi bọc middleware xác thực, thay vì
    # mcp.run(), để kiểm soát được lớp HTTP.
    app = BearerAuthMiddleware(mcp.streamable_http_app(), AUTH_TOKEN)
    log.info("HireWise MCP nghe tại http://%s:%d/mcp (đã bật xác thực bearer)", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
