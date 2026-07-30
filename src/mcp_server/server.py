"""
HireWise MCP Server (Streamable HTTP, cổng 8001)
================================================

Phơi các năng lực tuyển dụng THẬT của HireWise ra cho client MCP: web Copilot của
chính HireWise (qua `app.services.ai_agent.mcp_client`) và các client ngoài như
Claude Desktop.

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
2. DANH TÍNH. `acting_user_id` được XÁC MINH với bảng users (tồn tại, đúng vai trò,
   chưa bị khoá) chứ không tin suông. Bản trước, không có acting_user_id thì server
   tự lấy tài khoản admin đầu tiên làm chủ thể — nghĩa là client ẩn danh thao tác
   với quyền admin. Giờ danh tính mặc định phải được KHAI BÁO TƯỜNG MINH qua
   MCP_DEFAULT_USER_EMAIL, không có thì từ chối.
3. PHẠM VI DỮ LIỆU. `owner_id` được tiêm vào MỌI tool ở `_run` (không chỉ tool ghi),
   nên một tool mới thêm sau này không thể vô tình đọc dữ liệu của HR khác.
"""

import contextlib
import hmac
import inspect
import json
import logging
import os
import sys
import uuid as uuid_mod
from typing import Annotated, Any, Literal

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy import text as sql_text
from starlette.responses import JSONResponse

from app.database import SessionLocal
from app import models
from app.services.ai_agent import agent_tools as T
from app.services.ai_agent import tool_registry as R
from app.services.logging import write_tool_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hirewise.mcp")

HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8001"))
AUTH_TOKEN = (os.getenv("MCP_AUTH_TOKEN") or "").strip()
# Danh tính dùng cho client MCP ngoài (không có phiên đăng nhập của web) và cho các
# resource/prompt. Phải là email của một tài khoản hr_staff/admin có thật.
DEFAULT_USER_EMAIL = (os.getenv("MCP_DEFAULT_USER_EMAIL") or "").strip()

INSTRUCTIONS = """\
Đây là hệ thống tuyển dụng HireWise. Các tool ở đây thao tác trên DỮ LIỆU THẬT của
bộ phận nhân sự.

Quy ước bắt buộc:
- KHÔNG hiển thị UUID cho người dùng và KHÔNG hỏi họ cung cấp id. Mọi tool nhận cả
  TÊN: jd_id="Backend Developer", candidate_id="Nguyễn Minh Khoa".
- Người dùng hỏi chung chung không nêu vị trí (vd "tìm người biết Python"): gọi
  search_candidates với skill="python" và BỎ TRỐNG jd_id để tìm xuyên mọi vị trí.
- Không bịa điểm số, tên ứng viên hay id. Chỉ nói những gì tool trả về.
- send_interview_invite gửi email thật, KHÔNG THU HỒI ĐƯỢC: phải hỏi xác nhận rồi
  mới gọi với confirm=true.
- generate_interview_questions có thể trả error="needs_confirmation" khi ứng viên đã
  có buổi phỏng vấn HR đang dùng dở: hỏi xác nhận rồi mới gọi lại với replace=true.
- Ngôn ngữ làm việc là tiếng Việt.
"""

mcp = FastMCP("HireWise MCP Server", instructions=INSTRUCTIONS, host=HOST, port=PORT)


# --------------------------------------------------------------------------- #
# Danh tính
# --------------------------------------------------------------------------- #
class IdentityError(Exception):
    """Không xác định được HR nào đang thao tác -> từ chối, KHÔNG đoán."""


def _resolve_actor(db, acting_user_id: str) -> models.User:
    """Đổi `acting_user_id` (hoặc danh tính mặc định) thành một User đã xác minh.

    Xác minh chứ không tin suông: id do CLIENT gửi lên. Client hợp lệ duy nhất trong
    kiến trúc này là backend HireWise (đã kèm bearer token) nhưng vẫn kiểm tra vai trò
    và trạng thái khoá — token bị lộ thì đây là lớp phòng thủ còn lại.
    """
    ref = (acting_user_id or "").strip()
    if ref:
        try:
            uid = uuid_mod.UUID(ref)
        except (ValueError, AttributeError, TypeError):
            raise IdentityError(f"acting_user_id không phải UUID hợp lệ: {ref!r}")
        user = db.get(models.User, uid)
        if user is None:
            raise IdentityError("acting_user_id không ứng với tài khoản nào.")
    elif DEFAULT_USER_EMAIL:
        user = db.query(models.User).filter(models.User.email == DEFAULT_USER_EMAIL).first()
        if user is None:
            raise IdentityError(
                f"MCP_DEFAULT_USER_EMAIL={DEFAULT_USER_EMAIL!r} không ứng với tài khoản nào."
            )
    else:
        raise IdentityError(
            "Không xác định được người dùng. Client phải truyền acting_user_id, "
            "hoặc server phải đặt MCP_DEFAULT_USER_EMAIL."
        )

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

    LUÔN trả `dict` — mọi tool khai `-> dict[str, Any]`, mà mcp>=1.10 validate kết quả
    theo annotation đó. Trả list/str trần ở nhánh lỗi sẽ biến thành ToolError và LLM
    chỉ nhận được stack trace pydantic thay vì thông báo đọc được.
    """
    db = SessionLocal()
    actor_id = None
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
        result = {"error": f"Không được phép: {e}"}
    except Exception as e:  # noqa: BLE001 - trả lỗi có cấu trúc cho client MCP
        db.rollback()
        log.exception("Tool %s thất bại", spec.name)
        result = {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()

    failed = "error" in result
    write_tool_log(
        tool_name=spec.name,
        input_params=kwargs,
        result=result,
        status="error" if failed else "success",
        user_id=actor_id,
    )
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
    """

    def impl(**kwargs: Any) -> dict[str, Any]:
        acting = kwargs.pop("acting_user_id", "") or ""
        # Bỏ tham số LLM để trống: để hàm Python dùng default của chính nó thay vì
        # nhận chuỗi rỗng (vd jd_id="" phải nghĩa là "mọi vị trí", không phải id rỗng).
        return _run(spec, kwargs, acting)

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
    # Tham số TIÊM bởi client tin cậy (backend HireWise). Nó nằm trong schema MCP,
    # nhưng mcp_client lọc khỏi schema trước khi đưa cho LLM -> model không mạo danh
    # được; còn server thì vẫn xác minh lại ở `_resolve_actor`.
    params.append(P(
        "acting_user_id",
        P.KEYWORD_ONLY,
        default="",
        annotation=Annotated[str, Field(
            description="NỘI BỘ. Id HR đang thao tác, do backend HireWise tiêm. Client khác bỏ trống."
        )],
    ))

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
def health() -> dict[str, Any]:
    """Kiểm tra MCP server + kết nối DB + danh tính mặc định."""
    db = SessionLocal()
    try:
        info: dict[str, Any] = {"status": "ok", "tools": len(R.REGISTRY) + 1}
        info["job_descriptions"] = db.query(models.JobDescription).count()
        try:
            info["default_identity"] = _resolve_actor(db, "").email
        except IdentityError as e:
            info["default_identity"] = None
            info["default_identity_error"] = str(e)
        return info
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# RESOURCES — dữ liệu để ĐỌC/đính kèm ngữ cảnh, không phải hành động
#
# Client ngoài (Claude Desktop) gắn resource vào hội thoại mà không tốn một lượt gọi
# tool. Chúng chạy dưới DANH TÍNH MẶC ĐỊNH (MCP_DEFAULT_USER_EMAIL) vì giao thức
# resource không có chỗ truyền acting_user_id.
# --------------------------------------------------------------------------- #
def _as_default_user(fn) -> str:
    """Chạy `fn(db, owner_id)` dưới danh tính mặc định, trả JSON đã format."""
    db = SessionLocal()
    try:
        actor = _resolve_actor(db, "")
        data = fn(db, str(actor.id))
    except IdentityError as e:
        data = {"error": f"Không được phép: {e}"}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        data = {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()
    return json.dumps(data, ensure_ascii=False, default=str, indent=2)


@mcp.resource(
    "hirewise://jds",
    name="Danh sách vị trí tuyển dụng",
    description="Toàn bộ vị trí tuyển dụng, dạng JSON.",
    mime_type="application/json",
)
def resource_jds() -> str:
    return _as_default_user(lambda db, oid: T.list_jds(db, status="all", owner_id=oid))


@mcp.resource(
    "hirewise://jd/{jd_id}",
    name="Chi tiết vị trí tuyển dụng",
    description="Yêu cầu đã cấu trúc + mô tả của một vị trí. jd_id nhận UUID hoặc tên.",
    mime_type="application/json",
)
def resource_jd(jd_id: str) -> str:
    return _as_default_user(lambda db, oid: T.get_jd(db, jd_id, owner_id=oid))


@mcp.resource(
    "hirewise://candidate/{candidate_id}",
    name="Hồ sơ ứng viên",
    description="Điểm, giải thích của AI, kỹ năng của một ứng viên. Nhận UUID hoặc tên.",
    mime_type="application/json",
)
def resource_candidate(candidate_id: str) -> str:
    return _as_default_user(lambda db, oid: T.get_candidate(db, candidate_id, owner_id=oid))


# --------------------------------------------------------------------------- #
# PROMPTS — quy trình lặp lại của HR, client hiện thành lệnh sẵn dùng
# --------------------------------------------------------------------------- #
@mcp.prompt(
    name="bao_cao_sang_loc",
    title="Báo cáo sàng lọc một vị trí",
    description="Dựng báo cáo sàng lọc ứng viên cho một vị trí tuyển dụng.",
)
def prompt_screening_report(jd_id: str, top_n: str = "5") -> str:
    return (
        f"Hãy lập báo cáo sàng lọc cho vị trí '{jd_id}'.\n"
        f"1. Dùng get_jd để nắm yêu cầu của vị trí.\n"
        f"2. Dùng search_candidates để lấy danh sách ứng viên đã chấm điểm.\n"
        f"3. Dùng compare_candidates với top_n={top_n} để so sánh nhóm dẫn đầu.\n"
        f"4. Kết luận: nên mời phỏng vấn ai, vì sao, và rủi ro cần kiểm chứng thêm.\n"
        f"Không nêu UUID trong báo cáo."
    )


@mcp.prompt(
    name="chuan_bi_phong_van",
    title="Chuẩn bị phỏng vấn một ứng viên",
    description="Tóm tắt hồ sơ và chuẩn bị bộ câu hỏi phỏng vấn cho một ứng viên.",
)
def prompt_interview_prep(candidate_id: str, aspect: str = "") -> str:
    focus = f" Tập trung vào: {aspect}." if aspect else ""
    return (
        f"Hãy chuẩn bị buổi phỏng vấn cho ứng viên '{candidate_id}'.{focus}\n"
        f"1. Dùng get_candidate để nắm điểm mạnh/điểm yếu AI đã chỉ ra.\n"
        f"2. Dùng generate_interview_questions để sinh và LƯU bộ câu hỏi.\n"
        f"3. Tóm tắt cho tôi: 3 điểm cần đào sâu và 3 dấu hiệu cảnh báo cần kiểm chứng.\n"
        f"Nếu tool báo needs_confirmation thì hỏi tôi trước, đừng tự ghi đè."
    )


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


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request):
    """Cho docker healthcheck: chỉ khẳng định tiến trình sống và DB nhận kết nối."""
    db = SessionLocal()
    try:
        db.execute(sql_text("SELECT 1"))
        return JSONResponse({"status": "ok", "tools": len(R.REGISTRY) + 1})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)
    finally:
        with contextlib.suppress(Exception):
            db.close()


def main() -> None:
    if not AUTH_TOKEN:
        log.critical(
            "Thiếu MCP_AUTH_TOKEN. Server này đọc/ghi thẳng dữ liệu tuyển dụng nên "
            "không được phép chạy không xác thực. Đặt MCP_AUTH_TOKEN trong .env "
            "(gợi ý: python -c \"import secrets;print(secrets.token_urlsafe(32))\")."
        )
        sys.exit(1)

    if not DEFAULT_USER_EMAIL:
        log.warning(
            "Chưa đặt MCP_DEFAULT_USER_EMAIL: client MCP ngoài (Claude Desktop) sẽ bị "
            "từ chối vì không có danh tính. Web Copilot vẫn chạy bình thường vì nó tự "
            "truyền acting_user_id."
        )

    # Streamable HTTP (endpoint /mcp) — transport hiện hành của MCP; SSE đã bị đánh
    # dấu deprecated trong đặc tả. Dựng app rồi bọc middleware xác thực, thay vì
    # mcp.run(), để kiểm soát được lớp HTTP.
    app = BearerAuthMiddleware(mcp.streamable_http_app(), AUTH_TOKEN)
    log.info("HireWise MCP nghe tại http://%s:%d/mcp (đã bật xác thực bearer)", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
