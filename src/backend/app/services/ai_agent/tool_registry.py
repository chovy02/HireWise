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
            "(thang 0-100). Kết quả sắp sẵn theo điểm giảm dần, nên 'N người cao nhất' chỉ "
            "cần limit=N. "
            "PHẠM VI TÌM: nếu hội thoại có 'NGỮ CẢNH GIAO DIỆN' (HR đang mở một vị trí) thì "
            "BẮT BUỘC truyền jd_id đó, kể cả khi HR không nhắc tên vị trí — bỏ trống sẽ gom "
            "cả ứng viên của vị trí khác và các tool sau sẽ thao tác nhầm sang đó. Chỉ bỏ "
            "trống jd_id khi KHÔNG có ngữ cảnh giao diện và HR đang hỏi tra cứu chung toàn "
            "hệ thống. TUYỆT ĐỐI không hỏi HR jd_id. "
            "HR hỏi người ĐIỂM THẤP NHẤT / kém nhất / cuối bảng: dùng order='asc' kèm limit=N, "
            "ĐỪNG lấy danh sách giảm dần rồi tự chọn ra người cuối. "
            "Kết quả có sẵn trường 'candidate_ids': muốn thao tác với CẢ NHÓM vừa tìm được "
            "thì CHÉP NGUYÊN mảng đó sang tool theo lô, TUYỆT ĐỐI không tự gõ lại tên."
        ),
        params=(
            Param(
                "jd_id", str,
                f"TUỲ CHỌN. {_JD_REF} Điền khi HR nêu vị trí HOẶC khi đang có ngữ cảnh "
                "giao diện; chỉ bỏ trống để tra cứu xuyên mọi vị trí.",
                default="",
            ),
            Param("min_score", float, "Điểm tối thiểu (thang 0-100).", default=0.0),
            Param("skill", str, "Kỹ năng cần có, vd 'python'.", default=""),
            Param("limit", int, "Số ứng viên tối đa trả về (trần 50).", default=20),
            Param(
                "order", str,
                "'desc' = điểm cao nhất trước (mặc định). 'asc' = điểm THẤP nhất trước, "
                "dùng khi HR hỏi về nhóm kém nhất/cuối bảng.",
                default="desc", enum=("desc", "asc"),
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
        description=(
            "Tạo 1 shortlist RỖNG cho 1 vị trí. HẦU NHƯ KHÔNG CẦN DÙNG: muốn thêm ứng viên "
            "thì gọi thẳng add_to_shortlist — nó TỰ TẠO shortlist theo tên nếu chưa có. Gọi "
            "tool này trước add_to_shortlist chỉ đẻ ra một shortlist rỗng thừa nằm lại trong "
            "hệ thống. Chỉ dùng khi HR nói rõ là muốn tạo sẵn một danh sách trống."
        ),
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
            "ai vào shortlist và trả về 'not_found' — đừng báo với HR là đã thêm xong. "
            "Nhóm trải trên NHIỀU vị trí sẽ trả error='needs_confirmation' và KHÔNG ghi gì: "
            "đó là dấu hiệu bạn đã quên giới hạn theo vị trí HR đang mở."
        ),
        params=(
            Param(
                "candidate_ids", list[str],
                f"Danh sách ứng viên, truyền TẤT CẢ cùng lúc. {_CAND_REF_BATCH}",
            ),
            Param("shortlist_name", str, "Tên shortlist, mặc định 'AI Shortlist'.", default="AI Shortlist"),
            Param(
                "allow_multiple_jds", bool,
                "true = chấp nhận tạo shortlist ở NHIỀU vị trí cùng lúc. Chỉ đặt sau khi HR "
                "đã xác nhận rõ ràng là muốn làm cho tất cả các vị trí đó.",
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
            "Đọc buổi phỏng vấn của 1 ứng viên: danh sách câu hỏi (có ĐÁNH SỐ), câu trả lời "
            "đã nhập, điểm và nhận xét của AI, điểm trung bình. "
            "PHẢI gọi tool này TRƯỚC record_interview_answers: số thứ tự câu hỏi ở đây chính "
            "là thứ tự mà lô câu trả lời phải khớp vào."
        ),
        params=(Param("candidate_id", str, _CAND_REF),),
        read_only=True, idempotent=True,
    ),
    ToolSpec(
        name="record_interview_answers",
        fn=T.record_interview_answers,
        title="Nhập câu trả lời phỏng vấn",
        description=(
            "Ghi câu trả lời của ứng viên rồi để AI CHẤM ĐIỂM từng câu (thang 10) và nhận xét. "
            "Dùng khi HR thuật lại ứng viên đã trả lời thế nào. "
            "answers khớp theo THỨ TỰ với câu hỏi mà get_interview vừa trả về: phần tử thứ i là "
            "câu trả lời cho câu hỏi index=i. Câu nào HR không nói tới thì để chuỗi rỗng ở đúng "
            "vị trí đó — TUYỆT ĐỐI không dồn danh sách lên, làm vậy là chấm câu trả lời này vào "
            "câu hỏi khác. Không tự bịa câu trả lời thay ứng viên."
        ),
        params=(
            Param("candidate_id", str, _CAND_REF),
            Param(
                "answers", list[str],
                "Câu trả lời theo đúng thứ tự câu hỏi của get_interview. Chuỗi rỗng = bỏ qua câu đó.",
            ),
            Param(
                "replace", bool,
                "true = chấp nhận GHI ĐÈ câu trả lời/điểm đã có. Chỉ đặt sau khi HR xác nhận.",
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
            "Kết thúc buổi phỏng vấn: AI đọc toàn bộ biên bản (câu hỏi + câu trả lời) rồi viết "
            "nhận xét tổng quan, và chuyển buổi phỏng vấn sang trạng thái hoàn tất. "
            "KHÔNG MỞ LẠI ĐƯỢC: mặc định confirm=false chỉ trả bản XEM TRƯỚC (đã trả lời bao "
            "nhiêu câu, còn trống bao nhiêu, điểm trung bình). Chỉ đặt confirm=true SAU KHI HR "
            "xác nhận."
        ),
        params=(
            Param("candidate_id", str, _CAND_REF),
            Param("confirm", bool, "true = kết thúc thật; false = chỉ xem trước.", default=False),
        ),
        destructive=True,  # đóng buổi phỏng vấn, không nhập thêm câu trả lời được
    ),
    ToolSpec(
        name="list_interview_results",
        fn=T.list_interview_results,
        title="Bảng điểm phỏng vấn",
        description=(
            "Liệt kê ứng viên ĐÃ PHỎNG VẤN kèm ĐIỂM TRUNG BÌNH PHỎNG VẤN (thang 10), sắp theo "
            "điểm giảm dần. Đây là tool trả lời các câu kiểu 'ai phỏng vấn trên 7 điểm'. "
            "CHÚ Ý PHÂN BIỆT: điểm ở đây là điểm PHỎNG VẤN thang 10, khác hẳn điểm sàng lọc CV "
            "thang 100 của search_candidates — HR nói 'điểm phỏng vấn/điểm trung bình' thì dùng "
            "tool này, đừng dùng search_candidates. "
            "Kết quả có sẵn 'candidate_ids' để chép sang set_candidate_decision."
        ),
        params=(
            Param(
                "jd_id", str,
                f"TUỲ CHỌN. {_JD_REF} Điền khi HR nêu vị trí hoặc đang có ngữ cảnh giao diện.",
                default="",
            ),
            Param(
                "min_avg_score", float,
                "Điểm phỏng vấn trung bình tối thiểu, THANG 10 (vd HR nói 'trên 7' -> 7).",
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
            "Ghi quyết định tuyển dụng cho MỘT HOẶC NHIỀU ứng viên đang nằm trong shortlist: "
            "accepted (nhận) / rejected (loại) / pending (để lại sau). Dùng khi HR nói 'đồng ý', "
            "'nhận', 'loại', 'từ chối' những ai đó. "
            "CHỈ GHI QUYẾT ĐỊNH, KHÔNG gửi thư — ứng viên chưa biết gì cho tới khi gọi "
            "send_decision_emails. "
            "Ứng viên chưa ở trong shortlist nào sẽ nằm trong 'not_in_shortlist' và KHÔNG được "
            "chốt: hỏi HR có muốn thêm vào shortlist trước không."
        ),
        params=(
            Param(
                "candidate_ids", list[str],
                f"Danh sách ứng viên, truyền TẤT CẢ cùng lúc. {_CAND_REF_BATCH}",
            ),
            Param(
                "decision", str, "Quyết định cho cả nhóm này.",
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
            "Gửi thư báo kết quả (nhận/loại) cho các ứng viên ĐÃ CHỐT của MỘT vị trí, dùng đúng "
            "mẫu thư HR đã cấu hình. HÀNH ĐỘNG KHÔNG THU HỒI ĐƯỢC: mặc định confirm=false chỉ "
            "trả BẢN XEM TRƯỚC (ai nhận thư gì, ai bị bỏ qua và vì sao). Chỉ đặt confirm=true "
            "SAU KHI HR đã xác nhận rõ ràng. "
            "Người đã nhận thư đúng với quyết định hiện tại sẽ tự động bị bỏ qua, không gửi trùng."
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
