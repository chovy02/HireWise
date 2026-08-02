"""
Các RÀO CHẮN trong agent_tools — những chỗ tool phải TỪ CHỐI thay vì làm bừa.

Bổ sung cho `test_agent_tools_resolve.py` (lo phần tra tên ứng viên/vị trí). Ở đây là
hai lỗi đã xảy ra thật khi HR dùng khung chat, cùng thuộc loại nguy hiểm nhất: tool
vẫn báo "xong" trong khi việc nó làm không phải việc HR muốn.

Không cần DB, không cần mạng, không tốn token AI: mọi thứ đụng tới hạ tầng đều được
thay bằng bản giả.

Chạy:  docker exec hirewise_mcp python -m pytest /app/tests/test_agent_tools_guards.py -q
"""

import types
import uuid

import pytest

from app.services.ai_agent import agent_tools as T
from app.services.ai_agent import interviewer


class FakeDB:
    """Chỉ cần đủ để chứng minh tool KHÔNG ghi gì."""

    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def query(self, *_a, **_k):
        raise AssertionError("Tool đã đụng tới DB trong khi lẽ ra phải dừng lại trước đó.")

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _cand(ten: str, jd_id, jd_title: str):
    return types.SimpleNamespace(
        id=uuid.uuid4(), name=ten, jd_id=jd_id,
        jd=types.SimpleNamespace(title=jd_title, id=jd_id),
    )


# --------------------------------------------------------------------------- #
# add_to_shortlist — không được lặng lẽ thao tác lan sang vị trí khác
# --------------------------------------------------------------------------- #
def test_nhom_trai_nhieu_vi_tri_thi_hoi_lai_va_khong_ghi_gi(monkeypatch):
    """LỖI THẬT: HR đang mở vị trí A, gõ 'lấy 4 người cao nhất bỏ vào shortlist'.

    Agent bỏ trống jd_id lúc search nên lấy top 4 của CẢ HỆ THỐNG, và tool cũ lặng lẽ
    tạo shortlist ở cả hai vị trí. HR nhìn màn hình vị trí A chỉ thấy 2 người, không
    hiểu 2 người kia đi đâu.

    Sửa bằng prompt thôi thì không đủ — prompt chỉ là xác suất. Đây là rào xác định.
    """
    a, b = uuid.uuid4(), uuid.uuid4()
    nhom = [_cand("Người A", a, "Backend Python"), _cand("Người B", b, "Data Science")]
    monkeypatch.setattr(T, "_resolve_refs", lambda db, refs, owner_id=None: (nhom, [], []))

    db = FakeDB()
    ket_qua = T.add_to_shortlist(
        db, candidate_ids=["x", "y"], created_by=str(uuid.uuid4()),
        shortlist_name="Vòng 1", owner_id=str(uuid.uuid4()),
    )

    assert ket_qua["error"] == "needs_confirmation"
    assert ket_qua["by_jd"] == {"Backend Python": 1, "Data Science": 1}
    # Quan trọng nhất: KHÔNG ghi gì cả.
    assert not db.committed and not db.added


def test_dong_y_ro_rang_thi_van_lam_duoc(monkeypatch):
    """Rào chắn là để HỎI, không phải để cấm: HR xác nhận thì tool phải chạy tiếp."""
    a, b = uuid.uuid4(), uuid.uuid4()
    nhom = [_cand("Người A", a, "Backend Python"), _cand("Người B", b, "Data Science")]
    monkeypatch.setattr(T, "_resolve_refs", lambda db, refs, owner_id=None: (nhom, [], []))
    # Qua được rào thì tool bắt đầu đụng DB — chứng minh bằng chính việc FakeDB nổ.
    with pytest.raises(AssertionError, match="đụng tới DB"):
        T.add_to_shortlist(
            FakeDB(), candidate_ids=["x", "y"], created_by=str(uuid.uuid4()),
            shortlist_name="Vòng 1", allow_multiple_jds=True, owner_id=str(uuid.uuid4()),
        )


def test_cung_mot_vi_tri_thi_khong_bi_chan(monkeypatch):
    """Không được chặn nhầm luồng bình thường (cả nhóm cùng một vị trí)."""
    a = uuid.uuid4()
    nhom = [_cand("Người A", a, "Backend Python"), _cand("Người B", a, "Backend Python")]
    monkeypatch.setattr(T, "_resolve_refs", lambda db, refs, owner_id=None: (nhom, [], []))
    with pytest.raises(AssertionError, match="đụng tới DB"):
        T.add_to_shortlist(
            FakeDB(), candidate_ids=["x", "y"], created_by=str(uuid.uuid4()),
            owner_id=str(uuid.uuid4()),
        )


# --------------------------------------------------------------------------- #
# record_interview_answers — AI hỏng thì KHÔNG được ghi điểm 0
# --------------------------------------------------------------------------- #
def _fake_question(text="Câu hỏi?", answer=None):
    return types.SimpleNamespace(
        question=text, expected_answer="Gợi ý", answer_text=answer,
        ai_evaluation=None, score=None, order_index=10,
    )


def _dung_phong_van(monkeypatch, cau_hoi, status="pending"):
    c = _cand("Ứng viên X", uuid.uuid4(), "Backend Python")
    interview = types.SimpleNamespace(questions=cau_hoi, status=status, feedback_summary=None)
    monkeypatch.setattr(T, "_find_candidate", lambda db, ref, owner_id=None: (c, None))
    monkeypatch.setattr(T, "_interview_of", lambda db, cand: interview)
    return c, interview


def test_ai_cham_hong_thi_khong_ghi_diem_0(monkeypatch):
    """LỖI THẬT: hết ngân sách token Groq -> `evaluate_interview_answer_ai` trả về bản
    giữ chỗ 0 điểm, và tool lưu thẳng xuống DB.

    Hậu quả: "chưa chấm được" biến thành "bị 0 điểm" — mà 0 điểm chính là con số HR
    dùng để loại người. Về sau không có cách nào phân biệt lại.
    """
    q = _fake_question()
    _, interview = _dung_phong_van(monkeypatch, [q])
    monkeypatch.setattr(
        interviewer, "evaluate_interview_answer_ai",
        lambda **_k: {"evaluation": interviewer.EVAL_FAILED, "score": 0, "error": "hết quota"},
    )

    db = FakeDB()
    ket_qua = T.record_interview_answers(db, "Ứng viên X", ["Em trả lời thế này"], owner_id="x")

    assert "error" in ket_qua
    assert q.score is None and q.answer_text is None  # không đụng vào câu hỏi
    assert db.rolled_back and not db.committed
    assert interview.status == "pending"  # không bị đẩy sang in_progress


def test_cham_duoc_thi_ghi_binh_thuong(monkeypatch):
    q = _fake_question()
    _, interview = _dung_phong_van(monkeypatch, [q])
    monkeypatch.setattr(
        interviewer, "evaluate_interview_answer_ai",
        lambda **_k: {"evaluation": "Trả lời tốt", "score": 8.5},
    )

    db = FakeDB()
    ket_qua = T.record_interview_answers(db, "Ứng viên X", ["Em trả lời thế này"], owner_id="x")

    assert ket_qua["recorded"] == 1
    assert q.score == 8.5 and q.ai_evaluation == "Trả lời tốt"
    assert db.committed and interview.status == "in_progress"


def test_mot_phan_cham_hong_thi_bao_ro_phan_do(monkeypatch):
    """Ghi phần chấm được, nhưng phải NÓI RÕ câu nào chưa chấm — im lặng ở đây khiến
    điểm trung bình bị hiểu nhầm là đã đầy đủ."""
    q1, q2 = _fake_question("Câu 1"), _fake_question("Câu 2")
    _dung_phong_van(monkeypatch, [q1, q2])

    goi = {"n": 0}

    def cham(**_k):
        goi["n"] += 1
        if goi["n"] == 1:
            return {"evaluation": "Tốt", "score": 9.0}
        return {"evaluation": interviewer.EVAL_FAILED, "score": 0}

    monkeypatch.setattr(interviewer, "evaluate_interview_answer_ai", cham)

    ket_qua = T.record_interview_answers(FakeDB(), "Ứng viên X", ["A", "B"], owner_id="x")

    assert ket_qua["recorded"] == 1
    assert [f["index"] for f in ket_qua["failed"]] == [2]
    assert "warning" in ket_qua
    assert q1.score == 9.0
    assert q2.score is None  # câu hỏng vẫn TRỐNG, không phải 0


def test_khong_ghi_de_cau_da_co_cau_tra_loi(monkeypatch):
    """Câu đã có câu trả lời = công sức đã nhập; ghi đè phải hỏi HR trước."""
    q = _fake_question(answer="Câu trả lời cũ")
    q.score = 7.0
    _dung_phong_van(monkeypatch, [q], status="in_progress")

    ket_qua = T.record_interview_answers(FakeDB(), "Ứng viên X", ["Câu trả lời mới"], owner_id="x")

    assert ket_qua["error"] == "needs_confirmation"
    assert q.answer_text == "Câu trả lời cũ" and q.score == 7.0


def test_so_cau_tra_loi_nhieu_hon_so_cau_hoi_thi_tu_choi(monkeypatch):
    """Lệch số lượng nghĩa là agent đang khớp câu trả lời vào nhầm câu hỏi."""
    _dung_phong_van(monkeypatch, [_fake_question()])

    ket_qua = T.record_interview_answers(FakeDB(), "Ứng viên X", ["A", "B", "C"], owner_id="x")

    assert "error" in ket_qua and ket_qua["question_count"] == 1


def test_eval_failed_nhan_dien_dung_ban_giu_cho():
    assert interviewer.eval_failed({"evaluation": interviewer.EVAL_FAILED, "score": 0})
    assert interviewer.eval_failed({})
    assert not interviewer.eval_failed({"evaluation": "Trả lời tốt", "score": 8.0})


# --------------------------------------------------------------------------- #
# Câu trả lời khi lượt LLM chết — không được PHỦ NHẬN việc đã làm
# --------------------------------------------------------------------------- #
_QUOTA = Exception("Error code: 429 - rate_limit_exceeded. Please try again in 21m30s")


def test_het_quota_va_chua_lam_gi_thi_noi_thang():
    from app.services.ai_agent.agent import _friendly_error

    cau = _friendly_error(_QUOTA)
    assert "hết hạn mức" in cau.lower()
    assert "ĐÃ kịp thực hiện" not in cau


def test_da_ghi_du_lieu_roi_moi_chet_thi_phai_noi_ra():
    """LỖI THẬT (thấy trên màn hình HR): tool đã thêm 4 người vào shortlist và sinh
    xong câu hỏi, rồi lượt gọi LLM CUỐI mới cạn hạn mức. Câu trả lời khi đó là "chưa
    xử lý được yêu cầu này" — HR tưởng chưa có gì nên gõ lại, và hệ thống làm lần hai.
    """
    from app.services.ai_agent.agent import _friendly_error

    cau = _friendly_error(_QUOTA, ["add_to_shortlist", "generate_interview_questions"])

    assert "ĐÃ kịp thực hiện" in cau
    assert "shortlist" in cau.lower() and "câu hỏi phỏng vấn" in cau.lower()
    # Lời dặn quan trọng nhất: đừng gửi lại, nếu không sẽ bị làm hai lần.
    assert "ĐỪNG gửi lại" in cau
    # Và tuyệt đối không được nói là chưa xử lý.
    assert "chưa xử lý được" not in cau


def test_ten_viec_lay_tu_registry_nen_tool_moi_tu_dong_dung():
    """Không hard-code tên tool: thêm ToolSpec mới là câu thông báo tự có tên tiếng Việt."""
    from app.services.ai_agent.agent import _friendly_error
    from app.services.ai_agent.tool_registry import SPECS

    cau = _friendly_error(_QUOTA, ["send_decision_emails"])
    assert SPECS["send_decision_emails"].title.lower() in cau


def test_tool_doc_khong_bi_tinh_la_da_ghi():
    """Chỉ tool GHI mới đáng cảnh báo. Kể cả khi đã gọi vài tool đọc mà lượt chết giữa
    chừng thì cũng không có tác dụng phụ nào để HR phải đi kiểm tra."""
    from app.services.ai_agent.agent import _friendly_error
    from app.services.ai_agent.tool_registry import SPECS

    assert SPECS["search_candidates"].read_only  # đúng phân loại thì mới chặn được
    cau = _friendly_error(_QUOTA)
    assert "ĐÃ kịp thực hiện" not in cau
