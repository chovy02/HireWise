"""
Tra cứu ứng viên / vị trí theo TÊN — nơi một tên do LLM bịa đã biến thành ghi dữ liệu thật.

SỰ CỐ GỐC (có trong agent_tool_logs). HR gõ: "lấy 3 người có điểm cao nhất bỏ vào
shortlist đặt tên là tiềm năng và đặt câu hỏi phỏng vấn ... mỗi người 3 câu".
  1. agent gọi compare_candidates với jd_id="Backend Developer" -> lỗi, vì vị trí thật
     tên "Backend Python" (chuỗi "Backend Developer" chính là VÍ DỤ trong mô tả schema
     lúc đó — model lấy luôn làm dữ liệu);
  2. không có danh sách ứng viên, agent tự nghĩ ra ["Nguyễn Văn A", "Trần Thị B",
     "Lê Văn C"];
  3. `_resolve_candidate` so bằng ILIKE %ref% nên "Trần Thị B" khớp "TRẦN THỊ BẢO NGỌC"
     -> add_to_shortlist thêm một người thật mà HR chưa từng nhắc, generate_interview_
     questions sinh luôn 3 câu hỏi cho người đó;
  4. HR nhận câu trả lời "đã thêm ... tuy nhiên không tìm thấy Nguyễn Văn A và Lê Văn C".

Bộ test này khoá lại từng mắt của chuỗi đó. Không cần DB thật: chỉ cần thay
`_owner_filter` bằng một query giả trả về danh sách ứng viên/JD dựng sẵn.

Chạy:  docker exec hirewise_mcp python -m pytest /app/tests/test_agent_tools_resolve.py -q
"""

import types
import uuid

import pytest

from app.services.ai_agent import agent_tools as T


# --------------------------------------------------------------------------- #
# Bản giả: chỉ cần đủ cho `_find_candidate` / `_find_jd`
# --------------------------------------------------------------------------- #
class FakeQuery:
    """Query giả. `.all()` trả bộ dữ liệu; `.filter(...)` bỏ qua điều kiện.

    Được phép bỏ qua điều kiện vì các hàm đang test KHÔNG lọc tên ở tầng SQL nữa —
    đó chính là thay đổi cần kiểm chứng: lọc tên giờ nằm trong Python (`_name_matches`).
    Nhánh tra theo UUID được xử lý riêng qua `by_id`.
    """

    def __init__(self, rows, by_id=None, unfiltered=None):
        self._rows = rows
        self._by_id = by_id
        # Kết quả cho `.first()` KHÔNG qua filter — `compare_candidates` tra JD kiểu đó.
        self._unfiltered = unfiltered
        self._loc_id = False

    def join(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        # Lần filter đầu trong `_find_*` là lọc theo id; đánh dấu để `.first()` trả
        # đúng thứ nhánh UUID mong đợi.
        self._loc_id = True
        return self

    def first(self):
        if self._loc_id:
            return self._by_id
        if self._unfiltered is not None:
            return self._unfiltered
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows

    def order_by(self, *_a, **_k):
        return self


class FakeDB:
    def query(self, *_a, **_k):
        return FakeQuery([])


def _cand(name, jd_title="Backend Python", cid=None, email="a@b.c"):
    jd = types.SimpleNamespace(title=jd_title)
    return types.SimpleNamespace(
        id=cid or uuid.uuid4(), name=name, email=email, jd=jd,
        jd_id=uuid.uuid4(), status="scored", skills=[], evaluation=None,
    )


def _jd(title, so_cv=0):
    return types.SimpleNamespace(
        id=uuid.uuid4(), title=title, cvs=[None] * so_cv, requirements={}
    )


@pytest.fixture
def ung_vien(monkeypatch):
    """Đặt sẵn danh sách ứng viên mà `_find_candidate` sẽ nhìn thấy."""

    def dat(rows, by_id=None, unfiltered=None):
        monkeypatch.setattr(
            T, "_owner_filter", lambda q, oid: FakeQuery(rows, by_id, unfiltered)
        )
        return rows

    return dat


@pytest.fixture
def vi_tri(monkeypatch):
    def dat(rows, by_id=None):
        monkeypatch.setattr(T, "_owner_filter", lambda q, oid: FakeQuery(rows, by_id))
        return rows

    return dat


# --------------------------------------------------------------------------- #
# Chuẩn hoá tên
# --------------------------------------------------------------------------- #
def test_bo_dau_va_hoa_thuong_khong_lam_truot_ten():
    """LLM viết lại tên rất tuỳ tiện; đây là những cách viết PHẢI vẫn khớp."""
    for viet in ("TRẦN THỊ BẢO NGỌC", "tran thi bao ngoc", "  Trần  Thị  Bảo Ngọc "):
        assert T._name_matches(viet, "Trần Thị Bảo Ngọc"), viet


def test_goi_tat_hop_le_van_khop():
    """HR/agent gọi tên rút gọn là chuyện thường và phải chấp nhận."""
    for viet in ("Khoa", "Minh Khoa", "Nguyễn Khoa"):
        assert T._name_matches(viet, "Nguyễn Minh Khoa"), viet


@pytest.mark.parametrize("bia", ["Nguyễn Văn A", "Trần Thị B", "Lê Văn C"])
def test_ten_giu_cho_khong_khop_ai(bia):
    """LỖI GỐC. "Trần Thị B" từng khớp "Trần Thị Bảo Ngọc" vì ILIKE '%Trần Thị B%'.

    Token 'b' không phải một token đầy đủ của tên nào, nên tên mẫu do LLM bịa phải
    trượt sạch — đó là điều kiện để tool ghi không chạm vào người thật.
    """
    for ten_that in ("Trần Thị Bảo Ngọc", "Nguyễn Minh Khoa", "Hoàng Văn Đạt"):
        assert not T._name_matches(bia, ten_that), f"{bia} vs {ten_that}"


def test_tien_to_giua_tu_khong_con_duoc_coi_la_khop():
    """Chặn cả lớp lỗi, không chỉ ba cái tên trong sự cố."""
    assert not T._name_matches("Ngu", "Nguyễn Minh Khoa")
    assert not T._name_matches("Nguyễn Minh Kh", "Nguyễn Minh Khoa")


# --------------------------------------------------------------------------- #
# _find_candidate
# --------------------------------------------------------------------------- #
def test_ten_dung_thi_tra_ve_ung_vien(ung_vien):
    rows = ung_vien([_cand("Trần Thị Bảo Ngọc")])
    c, err = T._find_candidate(FakeDB(), "trần thị bảo ngọc")
    assert c is rows[0] and err is None


def test_ten_bia_thi_khong_tra_ve_ai(ung_vien):
    ung_vien([_cand("Trần Thị Bảo Ngọc"), _cand("Nguyễn Minh Khoa")])
    c, err = T._find_candidate(FakeDB(), "Trần Thị B")
    assert c is None
    assert "Trần Thị B" in err


def test_ten_khop_nhieu_nguoi_thi_bao_nhap_nhang(ung_vien):
    """Bản trước lấy `.first()` -> âm thầm chọn một người; HR không biết mình vừa
    thao tác lên ai. Nhập nhằng phải thành lỗi có tên cụ thể để agent hỏi lại."""
    ung_vien([
        _cand("Nguyễn Minh Khoa", "Backend Python"),
        _cand("Nguyễn Minh Khoa", "Software Engineer"),
    ])
    c, err = T._find_candidate(FakeDB(), "Nguyễn Minh Khoa")
    assert c is None
    assert "2 hồ sơ" in err and "Backend Python" in err and "Software Engineer" in err


def test_uuid_khong_ton_tai_thi_khong_di_so_ten(ung_vien):
    """Một UUID bịa không được rơi xuống nhánh so tên rồi khớp bừa vào ai đó."""
    ung_vien([_cand("Trần Thị Bảo Ngọc")], by_id=None)
    c, err = T._find_candidate(FakeDB(), str(uuid.uuid4()))
    assert c is None and "id" in err


def test_uuid_dung_thi_lay_thang_khong_can_ten(ung_vien):
    muc_tieu = _cand("Trần Thị Bảo Ngọc")
    ung_vien([muc_tieu], by_id=muc_tieu)
    c, err = T._find_candidate(FakeDB(), str(muc_tieu.id))
    assert c is muc_tieu and err is None


# --------------------------------------------------------------------------- #
# _find_jd — lỗi phải DẠY được cho agent
# --------------------------------------------------------------------------- #
def test_sai_ten_vi_tri_thi_loi_liet_ke_vi_tri_that(vi_tri):
    """Đúng bước 1 của sự cố: agent đoán "Backend Developer".

    Lỗi cũ ("Không tìm thấy vị trí: Backend Developer") là ngõ cụt — agent chỉ còn
    cách đoán tiếp. Lỗi mới phải chứa tên thật để nó tự gọi lại cho đúng.
    """
    vi_tri([_jd("Backend Python"), _jd("Software Engineer")])
    jd, err = T._find_jd(FakeDB(), "Backend Developer")
    assert jd is None
    assert "Backend Python" in err and "Software Engineer" in err


def test_ten_vi_tri_trung_nhau_thi_chon_cai_co_nhieu_cv_nhat(vi_tri):
    """HR tạo trùng tên là chuyện thật (DB hiện có 2 JD 'Backend Python'). Chính HR
    cũng không phân biệt được, nên đây KHÔNG phải nhập nhằng cần hỏi lại."""
    it, nhieu = _jd("Backend Python", 1), _jd("Backend Python", 9)
    vi_tri([it, nhieu])
    jd, err = T._find_jd(FakeDB(), "Backend Python")
    assert jd is nhieu and err is None


def test_ten_khop_nhieu_vi_tri_khac_nhau_thi_hoi_lai(vi_tri):
    vi_tri([_jd("Backend Python"), _jd("Backend Java")])
    jd, err = T._find_jd(FakeDB(), "Backend")
    assert jd is None
    assert "Backend Python" in err and "Backend Java" in err


def test_chua_co_vi_tri_nao_thi_noi_dung_su_that(vi_tri):
    vi_tri([])
    jd, err = T._find_jd(FakeDB(), "Backend Python")
    assert jd is None and "chưa có vị trí" in err


# --------------------------------------------------------------------------- #
# TOOL GHI: cả lô hoặc không gì cả
# --------------------------------------------------------------------------- #
def test_add_to_shortlist_khong_ghi_gi_khi_danh_sach_co_ten_bia(ung_vien, monkeypatch):
    """MẮT QUAN TRỌNG NHẤT. Với danh sách bịa của sự cố, tool phải KHÔNG ghi gì.

    Bản trước thêm 1 người (khớp nhầm) rồi cảnh báo 2 người còn lại — tác dụng phụ đã
    xảy ra và không rút lại được.
    """
    ung_vien([_cand("Trần Thị Bảo Ngọc"), _cand("Nguyễn Minh Khoa")])
    da_tao_shortlist = []
    monkeypatch.setattr(
        T, "_shortlist_for",
        lambda *a, **k: da_tao_shortlist.append(a) or types.SimpleNamespace(id=uuid.uuid4()),
    )

    ket_qua = T.add_to_shortlist(
        FakeDB(),
        candidate_ids=["Nguyễn Văn A", "Trần Thị B", "Lê Văn C"],
        created_by=str(uuid.uuid4()),
        shortlist_name="Tiềm năng",
    )

    assert "error" in ket_qua
    assert set(ket_qua["not_found"]) == {"Nguyễn Văn A", "Trần Thị B", "Lê Văn C"}
    assert not da_tao_shortlist, "KHÔNG được tạo/đụng shortlist khi danh sách hỏng"
    assert "added" not in ket_qua and "ui_action" not in ket_qua


def test_add_to_shortlist_chan_ca_lo_du_chi_mot_ten_sai(ung_vien, monkeypatch):
    """Hai người đúng + một người bịa cũng KHÔNG được ghi: một ref hỏng nghĩa là
    agent đang đoán, và không có cách nào biết nó đoán đúng mấy phần."""
    rows = ung_vien([_cand("Trần Thị Bảo Ngọc"), _cand("Nguyễn Minh Khoa")])
    monkeypatch.setattr(T, "_shortlist_for", lambda *a, **k: pytest.fail("không được ghi"))

    ket_qua = T.add_to_shortlist(
        FakeDB(),
        candidate_ids=[rows[0].name, rows[1].name, "Lê Văn C"],
        created_by=str(uuid.uuid4()),
    )

    assert ket_qua["not_found"] == ["Lê Văn C"]
    assert sorted(ket_qua["resolved"]) == sorted([rows[0].name, rows[1].name])


def test_generate_questions_khong_goi_ai_khi_danh_sach_hong(ung_vien, monkeypatch):
    """Chặn TRƯỚC khi gọi Gemini: mỗi ứng viên là một lượt gọi AI, đốt hạn mức cho một
    lô sai là mất thật (và bộ câu hỏi ghi ra là của người HR không hề chọn)."""
    ung_vien([_cand("Trần Thị Bảo Ngọc")])
    monkeypatch.setattr(
        T, "_generate_questions_for", lambda *a, **k: pytest.fail("không được gọi AI")
    )

    ket_qua = T.generate_interview_questions(
        FakeDB(), candidate_ids=["Nguyễn Văn A", "Trần Thị B"], num_questions=3
    )

    assert "error" in ket_qua and ket_qua["not_found"] == ["Nguyễn Văn A", "Trần Thị B"]


def test_tool_ghi_khu_trung_truoc_khi_thao_tac(ung_vien, monkeypatch):
    """LLM hay truyền cùng một người hai lần (một lần tên, một lần id)."""
    c = _cand("Nguyễn Minh Khoa")
    ung_vien([c], by_id=c)
    goi = []
    monkeypatch.setattr(T, "_generate_questions_for",
                        lambda db, cand, *a: goi.append(cand) or {"candidate": cand.name,
                                                                  "status": "created"})

    T.generate_interview_questions(FakeDB(), candidate_ids=[str(c.id), str(c.id)])
    assert len(goi) == 1


# --------------------------------------------------------------------------- #
# Tool ĐỌC vẫn được xử lý một phần
# --------------------------------------------------------------------------- #
def test_compare_candidates_van_so_phan_tim_duoc_va_canh_bao(ung_vien, monkeypatch):
    """Ranh giới cố ý: tool ĐỌC không có tác dụng phụ nào để mất, nên một bản so sánh
    thiếu người vẫn hữu ích hơn là không có gì — miễn là nói rõ ai bị thiếu."""
    rows = [_cand("Trần Thị Bảo Ngọc"), _cand("Nguyễn Minh Khoa")]
    for c in rows:  # cùng một JD mới so sánh được
        c.jd_id = rows[0].jd_id
        c.raw_text = "cv"
    # `unfiltered`: chỗ compare_candidates tra JD của nhóm (không qua nhánh lọc id).
    ung_vien(rows, unfiltered=_jd("Backend Python"))
    monkeypatch.setattr(T, "compare_candidates_ai", lambda *a, **k: {"summary": "ok"})

    ket_qua = T.compare_candidates(
        FakeDB(), candidate_ids=[rows[0].name, rows[1].name, "Lê Văn C"]
    )

    assert ket_qua["compared_count"] == 2
    assert ket_qua["not_found"] == ["Lê Văn C"]
    assert "PHẢI báo" in ket_qua["warning"]
