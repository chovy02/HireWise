"""
REGISTRY TOOL — MỘT nguồn sự thật duy nhất cho toàn bộ năng lực của AI Agent.

Vì sao có file này
------------------
Trước đây bộ tool được mô tả ở HAI nơi viết tay song song: `TOOLS` (JSON schema cho
Groq) trong agent_tools.py, và các wrapper `@mcp.tool()` trong mcp_server/server.py.
Hai bản đó đã trôi lệch thật: `send_interview_invite` có ở bản Groq nhưng KHÔNG hề
được đăng ký trên MCP server — trong khi system prompt vẫn dặn LLM dùng nó. Đường
chính (MCP) vì thế không có cách nào gửi thư mời phỏng vấn.

Giờ chỉ còn MỘT bản mô tả ở đây. Cả hai nơi tiêu thụ đều SINH RA từ nó:
  - MCP server  : duyệt REGISTRY, tự dựng hàm có đúng chữ ký rồi `mcp.add_tool(...)`.
  - Đường fallback: `llm_tool_schemas()` trả thẳng schema function-calling cho Groq.
Thêm một tool = thêm một `ToolSpec`. Không còn chỗ nào để quên.

Tham số TIÊM (LLM không bao giờ nhìn thấy, không bao giờ điền được)
-------------------------------------------------------------------
  owner_id   : id HR đang thao tác — mọi tool lọc dữ liệu theo nó (đa người dùng).
  created_by : chỉ với tool GHI, khai báo qua `user_bound`.
Hai tên này KHÔNG được xuất hiện trong `params` của bất kỳ spec nào; `_ASSERT` ở cuối
file canh giữ điều đó.

Annotation an toàn (read_only / destructive / idempotent / open_world)
---------------------------------------------------------------------
Đây là hint chuẩn của MCP, và ở HireWise chúng được DÙNG THẬT chứ không phải khai cho
đủ bộ: `agent.py` đọc `read_only` để biết trong lượt vừa rồi đã có tool GHI nào chạy
xong hay chưa — nếu MCP đứt giữa lượt sau một tool ghi thì KHÔNG được chạy lại cả lượt
ở đường fallback (sẽ tạo JD lần hai, gửi email lần hai). Không khai thì `create_jd` và
`list_jds` nguy hiểm ngang nhau dưới mắt tầng gọi.
"""

from dataclasses import dataclass
from typing import Any, Callable

from app.services.ai_agent import agent_tools as T

# Tham số do tầng gọi tiêm vào, tuyệt đối không lộ ra schema của LLM.
INJECTED_KWARGS = ("owner_id", "created_by")

_REQUIRED = object()  # sentinel: tham số bắt buộc (khác hẳn "mặc định là None")


@dataclass(frozen=True)
class Param:
    """Một tham số mà LLM được phép điền."""

    name: str
    type: Any  # str | int | float | bool | list[str]
    description: str
    default: Any = _REQUIRED
    enum: tuple[str, ...] | None = None

    @property
    def required(self) -> bool:
        return self.default is _REQUIRED


@dataclass(frozen=True)
class ToolSpec:
    name: str
    fn: Callable
    title: str  # nhãn tiếng Việt cho con người đọc (client MCP hiển thị)
    description: str  # mô tả cho LLM — đây là "prompt" quan trọng nhất của tool
    params: tuple[Param, ...] = ()
    user_bound: str | None = None  # tên kwarg nhận id HR, vd "created_by"
    read_only: bool = False  # không đổi dữ liệu
    destructive: bool = False  # có thể phá/mất dữ liệu hoặc không thu hồi được
    idempotent: bool = False  # gọi lại cùng tham số cho cùng kết quả
    open_world: bool = False  # chạm ra thế giới ngoài hệ thống (gửi mail...)


# --------------------------------------------------------------------------- #
# Sinh JSON Schema
# --------------------------------------------------------------------------- #
_SCALARS = {str: "string", int: "integer", float: "number", bool: "boolean"}

# `list[str]` tạo một object MỚI ở mỗi lần viết, nên phải so bằng `==` (GenericAlias
# so theo origin + args) chứ không phải `is` — dùng `is` thì mọi so sánh đều sai.
LIST_OF_STR = list[str]


def is_list_of_str(t: Any) -> bool:
    return t == LIST_OF_STR


def param_schema(p: Param) -> dict:
    """JSON Schema cho 1 tham số (dùng chung cho Groq; MCP tự sinh từ chữ ký hàm)."""
    if is_list_of_str(p.type):
        schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    else:
        schema = {"type": _SCALARS[p.type]}
    schema["description"] = p.description
    if p.enum:
        schema["enum"] = list(p.enum)
    return schema


def llm_tool_schemas() -> list[dict]:
    """Schema function-calling (OpenAI/Groq) cho ĐƯỜNG FALLBACK.

    Đường chính lấy schema từ MCP server; hàm này chỉ dùng khi MCP không kết nối
    được. Cả hai cùng sinh từ REGISTRY nên LLM thấy y hệt nhau ở hai đường —
    trước đây hai bản khác nhau khiến lỗi chỉ tái hiện ở một đường.
    """
    out = []
    for spec in REGISTRY:
        props = {p.name: param_schema(p) for p in spec.params}
        params: dict[str, Any] = {"type": "object", "properties": props}
        required = [p.name for p in spec.params if p.required]
        if required:
            params["required"] = required
        out.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": params,
            },
        })
    return out


# --------------------------------------------------------------------------- #
# REGISTRY
# --------------------------------------------------------------------------- #
# KHÔNG đặt tên ví dụ cụ thể ở đây. Bản trước ghi "vd 'Backend Developer'" và
# "vd 'Nguyễn Minh Khoa'" — model đã lấy ĐÚNG chuỗi "Backend Developer" trong mô tả
# này làm jd_id thật (log agent_tool_logs còn ghi), trong khi vị trí thật tên khác.
# Ví dụ đặt trong schema không phải minh hoạ vô hại: với model yếu nó là dữ liệu mồi.
_JD_REF = (
    "UUID của vị trí (ưu tiên, lấy từ kết quả list_jds/search_candidates) HOẶC tên vị "
    "trí ĐÚNG NHƯ hệ thống đang có. Không tự nghĩ ra tên vị trí."
)
_CAND_REF = (
    "UUID của ứng viên (ưu tiên, lấy từ kết quả search_candidates) HOẶC tên đầy đủ "
    "đúng như tool đã trả về. Không tự nghĩ ra tên."
)
# Với thao tác theo lô, TÊN là không đủ: một người có thể ứng tuyển nhiều vị trí và
# mỗi lần là một hồ sơ RIÊNG. Tra theo tên chỉ ra được một hồ sơ, nên nếu agent truyền
# tên thì các hồ sơ còn lại bị bỏ sót lặng lẽ (đã gặp thật: 7 hồ sơ chỉ xử lý được 4).
_CAND_REF_BATCH = (
    "Ưu tiên truyền candidate_id (UUID) mà search_candidates vừa trả về — chính xác hơn "
    "tên khi nhiều người trùng tên hoặc một người ứng tuyển nhiều vị trí. Chỉ dùng tên "
    "khi HR gọi đích danh và chưa hề tra cứu."
)

REGISTRY: tuple[ToolSpec, ...] = (
    # ----------------------------- ĐỌC / TRA CỨU ---------------------------- #
    ToolSpec(
        name="list_jds",
        fn=T.list_jds,
        title="Liệt kê vị trí tuyển dụng",
        description="Liệt kê các vị trí tuyển dụng (Job Description) của HR đang thao tác.",
        params=(
            Param(
                "status", str,
                "Lọc theo trạng thái, mặc định 'active'.",
                default="active", enum=("active", "closed", "all"),
            ),
        ),
        read_only=True, idempotent=True,
    ),
    ToolSpec(
        name="get_jd",
        fn=T.get_jd,
        title="Xem chi tiết vị trí",
        description="Xem chi tiết 1 vị trí tuyển dụng: yêu cầu đã cấu trúc + nội dung JD.",
        params=(Param("jd_id", str, _JD_REF),),
        read_only=True, idempotent=True,
    ),
    ToolSpec(
        name="search_candidates",
        fn=T.search_candidates,
        title="Tìm ứng viên",
        description=(
            "Tìm ứng viên ĐÃ ĐƯỢC CHẤM ĐIỂM, lọc theo kỹ năng và/hoặc điểm tối thiểu "
            "(thang 0-100). jd_id là TUỲ CHỌN: nếu HR chỉ nói 'tìm người biết Python' mà "
            "KHÔNG nhắc vị trí nào thì BỎ TRỐNG jd_id để tìm xuyên mọi vị trí — TUYỆT ĐỐI "
            "không hỏi HR jd_id. "
            "Kết quả có sẵn trường 'candidate_ids': muốn thao tác với CẢ NHÓM vừa tìm được "
            "thì CHÉP NGUYÊN mảng đó sang tool theo lô, TUYỆT ĐỐI không tự gõ lại tên."
        ),
        params=(
            Param("jd_id", str, f"TUỲ CHỌN. {_JD_REF} Chỉ điền khi HR có nêu vị trí.", default=""),
            Param("min_score", float, "Điểm tối thiểu (thang 0-100).", default=0.0),
            Param("skill", str, "Kỹ năng cần có, vd 'python'.", default=""),
            Param("limit", int, "Số ứng viên tối đa trả về (trần 50).", default=20),
        ),
        read_only=True, idempotent=True,
    ),
    ToolSpec(
        name="get_candidate",
        fn=T.get_candidate,
        title="Xem chi tiết ứng viên",
        description=(
            "Chi tiết 1 ứng viên: thông tin liên hệ, điểm, giải thích của AI, bằng chứng, kỹ năng."
        ),
        params=(Param("candidate_id", str, _CAND_REF),),
        read_only=True, idempotent=True,
    ),
    ToolSpec(
        name="list_shortlists",
        fn=T.list_shortlists,
        title="Liệt kê shortlist",
        description="Liệt kê các shortlist của 1 vị trí kèm số ứng viên trong mỗi shortlist.",
        params=(Param("jd_id", str, _JD_REF),),
        read_only=True, idempotent=True,
    ),
    # ------------------------ PHÂN TÍCH (đọc + gọi AI) ---------------------- #
    ToolSpec(
        name="compare_candidates",
        fn=T.compare_candidates,
        title="So sánh ứng viên",
        description=(
            "So sánh 2+ ứng viên CÙNG 1 vị trí, trả về phân tích của AI. "
            "CHỈ dùng khi HR muốn SO SÁNH — đây KHÔNG phải cách để lấy danh sách top N mang "
            "sang tool khác; việc đó dùng search_candidates với limit=N. "
            "Nếu HR nói 'so sánh top 3' thì truyền jd_id + top_n=3, tool tự lấy đúng N người "
            "điểm cao nhất. Chỉ dùng candidate_ids khi HR gọi đích danh từng người."
        ),
        params=(
            Param("jd_id", str, f"{_JD_REF} Dùng kèm top_n.", default=""),
            Param("top_n", int, "So sánh N ứng viên điểm cao nhất của vị trí đó.", default=0),
            Param(
                "candidate_ids", list[str],
                "UUID HOẶC tên từng ứng viên (chỉ khi HR gọi đích danh).",
                default=None,
            ),
            Param("aspect", str, "Khía cạnh trọng tâm, vd 'Python và hạ tầng'.", default=""),
        ),
        # Không ghi gì vào DB, nhưng KHÔNG idempotent: mỗi lần gọi là một lượt sinh
        # văn bản mới của AI, kết quả không lặp lại y hệt.
        read_only=True, idempotent=False,
    ),
    # ------------------------------- GHI DỮ LIỆU ---------------------------- #
    ToolSpec(
        name="create_jd",
        fn=T.create_jd,
        title="Tạo vị trí tuyển dụng mới",
        description=(
            "Chuẩn hóa 1 mô tả tuyển dụng ngôn ngữ tự nhiên bằng AI rồi LƯU thành vị trí mới. "
            "raw_text PHẢI lấy từ chính tin nhắn mới nhất của HR, không tái sử dụng nội dung "
            "của các lượt trước."
        ),
        params=(Param("raw_text", str, "Nội dung mô tả vị trí do HR viết."),),
        user_bound="created_by",
    ),
    ToolSpec(
        name="generate_interview_questions",
        fn=T.generate_interview_questions,
        title="Sinh câu hỏi phỏng vấn",
        description=(
            "Sinh bộ câu hỏi phỏng vấn bám CV + JD cho MỘT HOẶC NHIỀU ứng viên VÀ LƯU vào buổi "
            "phỏng vấn của họ (HR xem được trong màn hình phỏng vấn). "
            "QUAN TRỌNG: cần làm cho nhiều người thì truyền HẾT vào candidate_ids trong MỘT lời "
            "gọi, TUYỆT ĐỐI không gọi lặp lại từng người. "
            "Nếu HR nói rõ số câu (vd 'mỗi người 3 câu') thì PHẢI đặt num_questions. "
            "Ai đã có buổi phỏng vấn mà HR nhập dữ liệu sẽ nằm trong 'needs_confirmation' — hỏi "
            "HR rồi mới gọi lại CHỈ với những người đó kèm replace=true. "
            "CẢ LÔ HOẶC KHÔNG GÌ CẢ: chỉ cần một ứng viên trong danh sách không tra ra được là "
            "tool KHÔNG sinh câu hỏi cho ai và trả về 'not_found'. Khi đó hãy gọi "
            "search_candidates để lấy candidate_ids đúng rồi gọi lại."
        ),
        params=(
            Param(
                "candidate_ids", list[str],
                f"Danh sách ứng viên, truyền TẤT CẢ cùng lúc. {_CAND_REF_BATCH}",
            ),
            Param("aspect", str, "Trọng tâm phỏng vấn (tuỳ chọn).", default=""),
            Param(
                "num_questions", int,
                "Số câu hỏi cho MỖI người. Đặt đúng con số HR yêu cầu; 0 = để AI tự quyết.",
                default=0,
            ),
            Param(
                "replace", bool,
                "true = chấp nhận GHI ĐÈ bộ câu hỏi cũ. Chỉ đặt sau khi HR đã xác nhận.",
                default=False,
            ),
        ),
        # destructive: có thể ghi đè bộ câu hỏi HR đang dùng (đã có rào replace).
        destructive=True,
    ),
    ToolSpec(
        name="create_shortlist",
        fn=T.create_shortlist,
        title="Tạo shortlist",
        description="Tạo 1 shortlist mới (rỗng) cho 1 vị trí.",
        params=(
            Param("jd_id", str, _JD_REF),
            Param("name", str, "Tên shortlist."),
        ),
        user_bound="created_by",
    ),
    ToolSpec(
        name="add_to_shortlist",
        fn=T.add_to_shortlist,
        title="Thêm ứng viên vào shortlist",
        description=(
            "Đưa MỘT HOẶC NHIỀU ứng viên vào shortlist của vị trí họ ứng tuyển (tự tạo shortlist "
            "nếu chưa có, chống trùng). Dùng khi HR muốn 'đưa/thêm ứng viên vào shortlisting'. "
            "QUAN TRỌNG: HR nói 'tất cả những người ...' hay 'N người điểm cao nhất' thì dùng "
            "search_candidates để lấy danh sách trước, rồi CHÉP NGUYÊN candidate_ids vào MỘT "
            "lời gọi — TUYỆT ĐỐI không gọi lặp lại từng người và không tự gõ tên. "
            "CẢ LÔ HOẶC KHÔNG GÌ CẢ: chỉ cần một ứng viên không tra ra được là tool KHÔNG thêm "
            "ai vào shortlist và trả về 'not_found' — đừng báo với HR là đã thêm xong."
        ),
        params=(
            Param(
                "candidate_ids", list[str],
                f"Danh sách ứng viên, truyền TẤT CẢ cùng lúc. {_CAND_REF_BATCH}",
            ),
            Param("shortlist_name", str, "Tên shortlist, mặc định 'AI Shortlist'.", default="AI Shortlist"),
        ),
        user_bound="created_by",
        idempotent=True,  # đã có sẵn thì trả 'already_in', không thêm lần hai
    ),
    ToolSpec(
        name="send_interview_invite",
        fn=T.send_interview_invite,
        title="Gửi thư mời phỏng vấn",
        description=(
            "Gửi email mời phỏng vấn cho ứng viên. HÀNH ĐỘNG KHÔNG THU HỒI ĐƯỢC: mặc định "
            "confirm=false chỉ trả về bản XEM TRƯỚC. Chỉ đặt confirm=true SAU KHI HR đã xác "
            "nhận rõ ràng."
        ),
        params=(
            Param("candidate_id", str, _CAND_REF),
            Param("when", str, "Thời gian phỏng vấn, vd '10h00 thứ Ba 14/07'."),
            Param("location", str, "Nơi/link phỏng vấn.", default="Google Meet (link gửi sau)"),
            Param("confirm", bool, "true = gửi thật; false = chỉ xem trước.", default=False),
        ),
        destructive=True,  # email đã gửi không rút lại được
        open_world=True,  # chạm ra ngoài hệ thống (SMTP)
    ),
    # -------------------------- ĐIỀU HƯỚNG GIAO DIỆN ------------------------ #
    # Các tool này trả về 'ui_action' — một directive để khung chat trên web tự điều
    # khiển giao diện bên phải (nhảy trang, làm mới danh sách). Chúng chỉ có nghĩa với
    # client duy nhất của hệ thống: Copilot trên web. Xem `_agent_loop` trong agent.py,
    # chỗ gom 'ui_action' từ kết quả tool rồi gửi kèm câu trả lời cho frontend.
    ToolSpec(
        name="open_jd",
        fn=T.open_jd,
        title="Mở trang vị trí",
        description=(
            "Điều hướng GIAO DIỆN sang trang chi tiết của 1 vị trí. Dùng khi HR muốn "
            "'mở/xem/vào' một vị trí cụ thể."
        ),
        params=(Param("jd_id", str, _JD_REF),),
        read_only=True, idempotent=True,
    ),
    ToolSpec(
        name="open_dashboard",
        fn=T.open_dashboard,
        title="Mở Dashboard",
        description="Điều hướng giao diện về màn hình Dashboard (danh sách các vị trí tuyển dụng).",
        read_only=True, idempotent=True,
    ),
    ToolSpec(
        name="open_shortlisting",
        fn=T.open_shortlisting,
        title="Mở màn hình Shortlisting",
        description="Điều hướng giao diện sang màn hình Shortlisting.",
        read_only=True, idempotent=True,
    ),
)

SPECS: dict[str, ToolSpec] = {s.name: s for s in REGISTRY}


# --------------------------------------------------------------------------- #
# Canh giữ tại thời điểm import — sai sót ở REGISTRY phải nổ NGAY lúc khởi động,
# chứ không phải lúc HR đang chat.
# --------------------------------------------------------------------------- #
def _assert_registry_sane() -> None:
    import inspect

    seen: set[str] = set()
    for spec in REGISTRY:
        if spec.name in seen:
            raise RuntimeError(f"Tool trùng tên trong REGISTRY: {spec.name}")
        seen.add(spec.name)

        sig = inspect.signature(spec.fn)
        accepted = set(sig.parameters)

        for p in spec.params:
            if p.name in INJECTED_KWARGS:
                raise RuntimeError(
                    f"{spec.name}: tham số tiêm '{p.name}' không được lộ ra cho LLM."
                )
            if p.name not in accepted:
                raise RuntimeError(f"{spec.name}: hàm không nhận tham số '{p.name}'.")
            if not is_list_of_str(p.type) and p.type not in _SCALARS:
                raise RuntimeError(f"{spec.name}.{p.name}: kiểu không hỗ trợ {p.type!r}.")

        if "owner_id" not in accepted:
            raise RuntimeError(f"{spec.name}: hàm phải nhận 'owner_id' để lọc theo chủ sở hữu.")
        if spec.user_bound and spec.user_bound not in accepted:
            raise RuntimeError(f"{spec.name}: hàm không nhận '{spec.user_bound}'.")

        # Mọi tham số BẮT BUỘC của hàm (trừ db + tham số tiêm) phải được khai trong
        # spec, nếu không tool sẽ ném TypeError ngay lần gọi đầu.
        for name, param in sig.parameters.items():
            if name == "db" or name in INJECTED_KWARGS:
                continue
            if param.default is inspect.Parameter.empty and name not in {p.name for p in spec.params}:
                raise RuntimeError(f"{spec.name}: thiếu khai báo tham số bắt buộc '{name}'.")


_assert_registry_sane()
