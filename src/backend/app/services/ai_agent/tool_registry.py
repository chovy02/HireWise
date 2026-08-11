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
#
# BA HẰNG SỐ NÀY LẶP Ở ~15 TOOL nên mỗi chữ thừa bị nhân lên 15 lần trong prompt.
# Giữ chúng ngắn nhất có thể mà vẫn đủ nghĩa.
_JD_REF = "UUID vị trí (ưu tiên) hoặc tên ĐÚNG như hệ thống có. Không tự nghĩ ra tên."
# Với tool thao tác trên MỘT người: ƯU TIÊN TÊN, không ưu tiên UUID.
#
# Lỗi thật đã gặp: HR hỏi "xem buổi phỏng vấn của Nguyễn Minh Khoa", agent đi
# search_candidates lấy danh sách rồi TỰ CHỌN một uuid trong đó — và chọn nhầm người
# đứng đầu bảng (Hoàng Văn Đạt). Tool không có cách nào phát hiện: uuid nào cũng hợp lệ.
# Còn khi truyền TÊN thì `_name_matches` bắt buộc mọi token phải trùng, nên không thể
# trả nhầm người; tên nhập nhằng thì tool báo lỗi và liệt kê người thật cho agent chọn.
_CAND_REF = (
    "TÊN ứng viên đúng như HR gọi (ưu tiên — tool tự tra chính xác), hoặc UUID nếu tool "
    "trước vừa trả về đúng người đó. HR gọi đích danh ai thì truyền THẲNG tên đó."
)
# Với thao tác theo lô, TÊN là không đủ: một người có thể ứng tuyển nhiều vị trí và
# mỗi lần là một hồ sơ RIÊNG. Tra theo tên chỉ ra được một hồ sơ, nên nếu agent truyền
# tên thì các hồ sơ còn lại bị bỏ sót lặng lẽ (đã gặp thật: 7 hồ sơ chỉ xử lý được 4).
_CAND_REF_BATCH = "Ưu tiên UUID từ search_candidates; tên chỉ khi HR gọi đích danh."

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
        # Vì sao mô tả phải NGẮN: schema của cả REGISTRY được gửi kèm MỌI lời gọi LLM,
        # hai lần mỗi lượt chat. Mỗi câu giải thích thừa ở đây bị nhân lên gấp đôi rồi
        # cộng vào trần token/phút của Groq — đo được: bộ mô tả dài trước đây ngốn 5.085
        # token, đủ để một lượt chat bình thường vượt trần 12.000 và phải ngồi chờ 429.
        # Lý do/bối cảnh thuộc về comment như dòng này, không thuộc về `description`.
        description=(
            "Tìm ứng viên ĐÃ CHẤM ĐIỂM (thang 100). 'N người cao nhất' = order='desc' + "
            "limit=N; 'N người THẤP NHẤT' = order='asc' + limit=N. "
            "HR nêu KHOẢNG ĐIỂM ('từ 50 đến 60', 'dưới 40') thì BẮT BUỘC dùng min_score "
            "và max_score — chỉ đặt limit là lấy nhầm người ngoài khoảng. "
            "Có NGỮ CẢNH GIAO DIỆN thì BẮT BUỘC truyền jd_id đó dù HR không nhắc tên. "
            "Chép nguyên 'candidate_ids' trong kết quả sang tool theo lô."
        ),
        params=(
            Param(
                "jd_id", str,
                f"TUỲ CHỌN. {_JD_REF} Bỏ trống = mọi vị trí.",
                default="",
            ),
            Param("min_score", float, "Điểm SÀN, tính cả bằng (thang 0-100).", default=0.0),
            # Không có tham số này thì "lấy 3 người từ 50 đến 60 điểm" là câu KHÔNG
            # diễn đạt được: LLM chỉ điền nổi min_score=50, rồi limit cắt từ trên
            # xuống và trả về 77/68/55. Hai người đầu nằm ngoài khoảng HR vừa nêu.
            Param(
                "max_score", float,
                "Điểm TRẦN, tính cả bằng. 0 = không chặn trên. HR nói 'từ A đến B' thì "
                "min_score=A và max_score=B; 'dưới B' thì max_score=B.",
                default=0.0,
            ),
            Param("skill", str, "Kỹ năng cần có, vd 'python'.", default=""),
            Param("limit", int, "Số ứng viên tối đa trả về (trần 50).", default=20),
            # KHÔNG CÓ DEFAULT — cố ý. Với default='desc', LLM bỏ trống tham số này là
            # lặng lẽ nhận danh sách CAO NHẤT: HR hỏi "so sánh 3 người điểm thấp nhất"
            # thì nhận đúng 3 người đứng đầu bảng, kèm câu trả lời gọi họ là "thấp
            # nhất". Bắt buộc điền thì LLM phải chọn chiều một cách có ý thức ở mọi lượt.
            Param(
                "order", str,
                "BẮT BUỘC chọn theo lời HR. 'desc' = cao nhất/giỏi nhất/top/dẫn đầu. "
                "'asc' = THẤP NHẤT/kém nhất/yếu nhất/tệ nhất/cuối bảng/để loại.",
                enum=("desc", "asc"),
            ),
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
            "So sánh 2+ ứng viên CÙNG 1 vị trí bằng AI. CHỈ để so sánh, không phải cách lấy "
            "danh sách (việc đó dùng search_candidates). 'So sánh 3 người CAO nhất' = jd_id "
            "+ count=3 + order='desc'; 'so sánh 3 người THẤP nhất' = order='asc'. "
            "candidate_ids chỉ khi HR gọi đích danh từng người."
        ),
        params=(
            Param("jd_id", str, f"{_JD_REF} Dùng kèm count.", default=""),
            # Tên cũ là `top_n` — chính cái tên đó gài bẫy: HR hỏi "3 người THẤP nhất"
            # mà tham số tên "top" thì LLM vẫn điền 3 và nhận về 3 người đứng đầu bảng.
            Param("count", int, "So sánh bao nhiêu người của vị trí đó.", default=0),
            # KHÔNG CÓ DEFAULT — cùng lý do như search_candidates.order: bỏ trống mà
            # ngầm hiểu là "cao nhất" thì sai lặng lẽ, và sai đúng vào câu HR dùng để
            # quyết định loại người.
            Param(
                "order", str,
                "Đi kèm count, BẮT BUỘC chọn theo lời HR. 'desc' = cao nhất/giỏi nhất/"
                "top. 'asc' = THẤP NHẤT/kém nhất/yếu nhất/cuối bảng/để loại.",
                enum=("desc", "asc"),
            ),
            Param(
                "candidate_ids", list[str],
                "Từng ứng viên, chỉ khi HR gọi đích danh.",
                default=None,
            ),
            Param("aspect", str, "Khía cạnh trọng tâm (tuỳ chọn).", default=""),
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
            "Sinh và LƯU bộ câu hỏi phỏng vấn bám CV + JD cho một hoặc nhiều ứng viên. "
            "Nhiều người thì truyền HẾT vào MỘT lời gọi. HR nêu số câu thì PHẢI đặt "
            "num_questions. Ai đã có dữ liệu phỏng vấn sẽ nằm ở 'needs_confirmation': hỏi HR "
            "rồi gọi lại CHỈ những người đó kèm replace=true."
        ),
        params=(
            Param(
                "candidate_ids", list[str],
                f"Danh sách ứng viên, truyền TẤT CẢ cùng lúc. {_CAND_REF_BATCH}",
            ),
            Param("aspect", str, "Trọng tâm phỏng vấn (tuỳ chọn).", default=""),
            Param(
                "num_questions", int,
                "Số câu hỏi MỖI người. Đúng con số HR yêu cầu; 0 = AI tự quyết.",
                default=0,
            ),
            Param(
                "replace", bool, "true = GHI ĐÈ bộ câu hỏi cũ, chỉ sau khi HR xác nhận.",
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
        description=(
            "Tạo shortlist RỖNG. HẦU NHƯ KHÔNG CẦN: add_to_shortlist tự tạo theo tên. Chỉ "
            "dùng khi HR nói rõ muốn tạo sẵn một danh sách trống. Vị trí đó đã có danh sách "
            "cùng tên thì tool DÙNG LẠI danh sách cũ và trả status='exists' — khi đó phải "
            "nói với HR là danh sách đã có sẵn, đừng báo là vừa tạo mới."
        ),
        params=(
            Param("jd_id", str, _JD_REF),
            Param(
                "name", str,
                "Tên shortlist, CHÉP NGUYÊN VĂN từ tin nhắn của HR — đúng từng dấu "
                "tiếng Việt, không viết lại, không bỏ dấu, không tự dịch.",
            ),
        ),
        user_bound="created_by",
    ),
    ToolSpec(
        name="add_to_shortlist",
        fn=T.add_to_shortlist,
        title="Thêm ứng viên vào shortlist",
        description=(
            "Đưa một hoặc nhiều ứng viên vào shortlist của vị trí họ ứng tuyển (tự tạo nếu "
            "chưa có, chống trùng). Lấy danh sách bằng search_candidates rồi chép nguyên "
            "candidate_ids vào MỘT lời gọi. Một ứng viên tra không ra là KHÔNG thêm ai "
            "('not_found'). Nhóm trải nhiều vị trí trả 'needs_confirmation' và không ghi gì."
        ),
        params=(
            Param(
                "candidate_ids", list[str],
                f"Danh sách ứng viên, truyền TẤT CẢ cùng lúc. {_CAND_REF_BATCH}",
            ),
            # LLM viết lại tiếng Việt rất tuỳ tiện, và tên shortlist là thứ HR nhìn
            # thấy hằng ngày: gõ "cặn bã" mà màn hình hiện "càn bả" thì HR mất niềm tin
            # vào cả lượt vừa chạy, dù mọi việc khác đều đúng.
            Param(
                "shortlist_name", str,
                "Tên shortlist, CHÉP NGUYÊN VĂN từ tin nhắn của HR — đúng từng dấu "
                "tiếng Việt, không viết lại, không bỏ dấu, không tự dịch.",
                default="AI Shortlist",
            ),
            Param(
                "allow_multiple_jds", bool,
                "true = chấp nhận làm cho NHIỀU vị trí, chỉ sau khi HR xác nhận.",
                default=False,
            ),
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
    # ----------------------------- SAU PHỎNG VẤN ---------------------------- #
    # Khép nốt vòng đời: phỏng vấn xong -> chấm -> tổng kết -> chốt nhận/loại -> báo
    # cho ứng viên. Trước đây agent dừng ở chỗ sinh câu hỏi, phần còn lại HR phải rời
    # khung chat làm tay.
    ToolSpec(
        name="get_interview",
        fn=T.get_interview,
        title="Xem buổi phỏng vấn",
        description=(
            "Đọc buổi phỏng vấn của 1 ứng viên: câu hỏi (CÓ ĐÁNH SỐ), câu trả lời, điểm và "
            "nhận xét AI. PHẢI gọi trước record_interview_answers — số thứ tự ở đây là thứ tự "
            "mà lô câu trả lời phải khớp vào."
        ),
        params=(Param("candidate_id", str, _CAND_REF),),
        read_only=True, idempotent=True,
    ),
    ToolSpec(
        name="record_interview_answers",
        fn=T.record_interview_answers,
        title="Nhập câu trả lời phỏng vấn",
        description=(
            "Ghi câu trả lời của ứng viên rồi để AI chấm điểm từng câu (thang 10). Dùng khi HR "
            "thuật lại ứng viên trả lời thế nào. answers khớp THỨ TỰ với câu hỏi của "
            "get_interview: phần tử thứ i ứng với index=i, câu không nhắc tới để chuỗi rỗng "
            "ĐÚNG vị trí (dồn lên là chấm nhầm câu). Không bịa câu trả lời thay ứng viên."
        ),
        params=(
            Param("candidate_id", str, _CAND_REF),
            Param(
                "answers", list[str],
                "Đúng thứ tự câu hỏi của get_interview. Chuỗi rỗng = bỏ qua câu đó.",
            ),
            Param(
                "replace", bool,
                "true = GHI ĐÈ câu trả lời/điểm đã có, chỉ sau khi HR xác nhận.",
                default=False,
            ),
        ),
        # destructive: ghi đè câu trả lời/điểm đã có của câu hỏi tương ứng.
        destructive=True,
    ),
    ToolSpec(
        name="finish_interview",
        fn=T.finish_interview,
        title="Kết thúc & tổng kết phỏng vấn",
        description=(
            "Kết thúc buổi phỏng vấn: AI đọc biên bản rồi viết nhận xét tổng quan và đóng lại. "
            "KHÔNG MỞ LẠI ĐƯỢC: confirm=false (mặc định) chỉ xem trước; confirm=true sau khi "
            "HR xác nhận."
        ),
        params=(
            Param("candidate_id", str, _CAND_REF),
            Param("confirm", bool, "true = kết thúc thật; false = xem trước.", default=False),
        ),
        destructive=True,  # đóng buổi phỏng vấn, không nhập thêm câu trả lời được
    ),
    ToolSpec(
        name="list_interview_results",
        fn=T.list_interview_results,
        title="Bảng điểm phỏng vấn",
        description=(
            "Ứng viên ĐÃ PHỎNG VẤN kèm điểm trung bình phỏng vấn THANG 10, giảm dần. Dùng cho "
            "câu hỏi về 'điểm phỏng vấn' — khác điểm sàng lọc CV thang 100 của "
            "search_candidates. HR nêu KHOẢNG thì dùng cả hai cận. "
            "Chép 'candidate_ids' sang set_candidate_decision."
        ),
        params=(
            Param("jd_id", str, f"TUỲ CHỌN. {_JD_REF}", default=""),
            Param(
                "min_avg_score", float, "Điểm SÀN phỏng vấn, tính cả bằng. THANG 10.",
                default=0.0,
            ),
            Param(
                "max_avg_score", float,
                "Điểm TRẦN phỏng vấn, tính cả bằng. 0 = không chặn trên. THANG 10.",
                default=0.0,
            ),
        ),
        read_only=True, idempotent=True,
    ),
    ToolSpec(
        name="set_candidate_decision",
        fn=T.set_candidate_decision,
        title="Chốt nhận / loại ứng viên",
        description=(
            "Chốt kết quả cho ứng viên ĐANG trong shortlist: accepted / rejected / pending. "
            "Dùng khi HR nói 'nhận', 'đồng ý', 'loại', 'từ chối'. CHỈ ghi quyết định, KHÔNG "
            "gửi thư (việc đó là send_decision_emails). Ai chưa ở trong shortlist nào sẽ nằm "
            "ở 'not_in_shortlist' và không được chốt."
        ),
        params=(
            Param(
                "candidate_ids", list[str],
                f"Danh sách ứng viên, truyền TẤT CẢ cùng lúc. {_CAND_REF_BATCH}",
            ),
            Param(
                "decision", str, "Quyết định cho cả nhóm.",
                enum=("accepted", "rejected", "pending"),
            ),
        ),
        # KHÔNG destructive: quyết định là một trường trạng thái, đổi lại được bất cứ lúc
        # nào và ứng viên chưa hề biết gì. Thứ không rút lại được là THƯ BÁO, và chỗ đó
        # mới cần rào xác nhận (send_decision_emails.confirm). Bắt xác nhận hai lần liên
        # tiếp chỉ khiến HR bấm đồng ý theo quán tính, làm loãng đúng cái rào quan trọng.
        idempotent=True,  # gọi lại cùng quyết định -> 'already_set', không đổi gì thêm
    ),
    ToolSpec(
        name="send_decision_emails",
        fn=T.send_decision_emails,
        title="Gửi thư báo kết quả",
        description=(
            "Gửi thư báo kết quả cho ứng viên ĐÃ CHỐT của MỘT vị trí, theo mẫu HR đã cấu hình. "
            "KHÔNG THU HỒI ĐƯỢC: confirm=false (mặc định) chỉ trả BẢN XEM TRƯỚC; chỉ đặt "
            "confirm=true sau khi HR xác nhận rõ ràng. Ai đã nhận thư đúng quyết định hiện tại "
            "sẽ tự động bị bỏ qua."
        ),
        params=(
            Param("jd_id", str, f"BẮT BUỘC. {_JD_REF}"),
            Param("confirm", bool, "true = gửi thật; false = chỉ xem trước.", default=False),
        ),
        destructive=True,  # thư đã gửi không rút lại được
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
