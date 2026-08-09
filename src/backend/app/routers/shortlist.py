from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.dependencies import get_current_user, require_role
from app.core.ownership import get_owned_candidate, get_owned_jd, get_owned_shortlist
from app.core.ranking import as_utc, score_sort_key
from app.database import SessionLocal, get_db
from app.services.email_notification import (
    ERR_INVALID_EMAIL,
    ERR_NO_EMAIL,
    is_valid_email,
    send_shortlist_email,
)
from app.services.logging import write_audit_log

# Quyết định đã chốt -> mới có mail kết quả để gửi.
DECIDED_STATUSES = ("accepted", "rejected")

# Một item mắc ở trạng thái "sending" lâu hơn mốc này coi như lô gửi đã chết (API
# restart giữa BackgroundTasks, container bị kill…) và được phép xếp hàng lại. Không có
# mốc này thì một lần restart là ứng viên đó "Đang gửi" vĩnh viễn, không ai gửi lại được.
SENDING_STALE_AFTER = timedelta(minutes=10)

# Cột notify_error là Text nên không có giới hạn cứng, nhưng thông báo lỗi SMTP có thể
# kèm cả trang HTML của nhà cung cấp — cắt để bảng DB và UI không phình ra.
MAX_ERROR_LEN = 800


# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────
def _candidate_summary(candidate: models.Candidate) -> schemas.ShortlistCandidate:
    """Rút gọn Candidate + điểm đánh giá để hiển thị trong shortlist."""
    evaluation = candidate.evaluation
    return schemas.ShortlistCandidate(
        id=candidate.id,
        name=candidate.name,
        email=candidate.email,
        status=candidate.status,
        score=evaluation.score if evaluation else None,
        # Kỹ năng đã khử trùng, giữ thứ tự, cắt bớt cho gọn (giống leaderboard).
        skills=list(dict.fromkeys(s.skill_name for s in candidate.skills))[:15],
        is_overridden=evaluation.is_overridden if evaluation else False,
        interview_status=candidate.interview.status if candidate.interview else None,
        created_at=candidate.created_at,
    )


def _item_response(item: models.ShortlistItem) -> schemas.ShortlistItemResponse:
    return schemas.ShortlistItemResponse(
        id=item.id,
        candidate_status=item.candidate_status,
        added_at=item.added_at,
        candidate=_candidate_summary(item.cv),
        # getattr thay vì item.notified_at: các cột này thêm ở migration 9e35c9fe2f0f và
        # f2b6d4a8c910, DB chưa nâng cấp thì đọc thẳng sẽ nổ 500 trên MỌI lần mở
        # shortlist — không chỉ riêng tính năng gửi mail.
        notified_at=getattr(item, "notified_at", None),
        notified_status=getattr(item, "notified_status", None),
        notify_state=getattr(item, "notify_state", None),
        notify_error_code=getattr(item, "notify_error_code", None),
        notify_error=getattr(item, "notify_error", None),
        notify_attempts=getattr(item, "notify_attempts", 0) or 0,
        notify_last_attempt_at=getattr(item, "notify_last_attempt_at", None),
    )


def _mark_notify_failure(
    item: models.ShortlistItem,
    code: str,
    message: str,
    *,
    attempted: bool,
    now: datetime | None = None,
) -> None:
    """Ghi lý do thất bại lên item.

    `attempted=False` cho các lỗi phát hiện TRƯỚC khi mở kết nối (thiếu email, sai định
    dạng): không tính là một lượt thử, vì không có lượt nào diễn ra — nếu đếm thì
    notify_attempts phồng lên mỗi lần HR bấm gửi cả lô.
    """
    now = now or datetime.now(timezone.utc)
    item.notify_state = "failed"
    item.notify_error_code = code
    item.notify_error = (message or "")[:MAX_ERROR_LEN]
    if attempted:
        item.notify_attempts = (getattr(item, "notify_attempts", 0) or 0) + 1
        item.notify_last_attempt_at = now


def _classify_notify_target(
    item: models.ShortlistItem, now: datetime
) -> tuple[str, str | None, str | None]:
    """Ứng viên này có nằm trong lô gửi kế tiếp không, và nếu không thì vì sao?

    Trả về (verdict, error_code, error_message). Đây là NGUỒN SỰ THẬT DUY NHẤT cho điều
    kiện gửi: cả endpoint gửi cả lô, con số báo về UI và nút "Thử lại" đều đi qua đây,
    nên UI không thể hứa một con số mà backend gửi một con số khác.
    """
    if item.candidate_status not in DECIDED_STATUSES:
        return "not_decided", None, None

    # Đã gửi thành công ĐÚNG quyết định hiện tại -> thôi, không spam ứng viên.
    if (
        getattr(item, "notified_at", None)
        and getattr(item, "notified_status", None) == item.candidate_status
    ):
        return "already_sent", None, None

    email = ((item.cv.email if item.cv else None) or "").strip()
    if not email:
        return (
            "no_email",
            ERR_NO_EMAIL,
            "CV không trích được địa chỉ email nên không thể gửi thông báo.",
        )
    if not is_valid_email(email):
        return (
            "invalid_email",
            ERR_INVALID_EMAIL,
            f"Địa chỉ email “{email}” không đúng định dạng nên không gửi được. "
            "Hãy sửa email của ứng viên rồi thử lại.",
        )

    # Đang có tiến trình nền gửi cho item này -> bỏ qua để hai lần bấm liên tiếp (hoặc
    # hai HR bấm cùng lúc) không gửi hai lần cho cùng một ứng viên.
    last_attempt = as_utc(getattr(item, "notify_last_attempt_at", None))
    if getattr(item, "notify_state", None) == "sending" and last_attempt:
        if now - last_attempt < SENDING_STALE_AFTER:
            return "in_flight", None, None

    return "send", None, None


def _load_hr_templates(db: Session, hr_user_id: UUID) -> tuple[dict, dict]:
    """Đọc mẫu email tuỳ chỉnh + file đính kèm của HR, gom theo template_type.

    Đọc MỘT LẦN cho mỗi lô: quan hệ `attachments` là lazy-load, để trong vòng lặp thì
    một lô 200 người thành 200 lượt query cho cùng hai bộ file.
    """
    templates = (
        db.query(models.EmailTemplate)
        .filter(
            models.EmailTemplate.user_id == hr_user_id,
            models.EmailTemplate.is_active == True,
        )
        .all()
    )
    template_map = {t.template_type: t for t in templates}
    attachment_map = {t_type: list(tpl.attachments) for t_type, tpl in template_map.items()}
    return template_map, attachment_map


def _get_shortlist_or_404(
    db: Session, shortlist_id: UUID, user: models.User
) -> models.Shortlist:
    """Bắt buộc truyền `user`: shortlist chỉ thấy được nếu JD chứa nó là của người này."""
    return get_owned_shortlist(db, shortlist_id, user)

def _record_send_result(
    db: Session, item_id: UUID, cand_status: str, result
) -> None:
    """Lưu kết quả một lượt gửi lên shortlist_items, rồi commit ngay.

    Commit theo TỪNG ứng viên chứ không dồn tới cuối lô: nếu tiến trình nền bị kill giữa
    một lô 200 người (deploy, container restart), gom hết vào một commit là mất sạch dấu
    vết của những người ĐÃ nhận mail — và lượt gửi sau sẽ gửi trùng cho họ.
    """
    item = (
        db.query(models.ShortlistItem)
        .filter(models.ShortlistItem.id == item_id)
        .first()
    )
    if not item:  # HR gỡ khỏi shortlist trong lúc mail đang gửi
        return

    now = datetime.now(timezone.utc)
    item.notify_attempts = (getattr(item, "notify_attempts", 0) or 0) + 1
    item.notify_last_attempt_at = now

    if result.ok:
        # notified_status ghi quyết định ĐÃ ĐƯỢC GỬI, không phải quyết định hiện tại:
        # HR có thể đổi accepted -> rejected trong lúc mail đang bay, và lúc đó ứng viên
        # cần được gửi lại (UI hiện "Cần gửi lại" nhờ đúng phép so sánh này).
        item.notified_at = now
        item.notified_status = cand_status
        item.notify_state = "sent"
        item.notify_error_code = None
        item.notify_error = None
    else:
        item.notify_state = "failed"
        item.notify_error_code = result.error_code
        item.notify_error = (result.error_message or "")[:MAX_ERROR_LEN]

    db.commit()


def _background_send_notifications(
    items_to_notify: list[tuple[UUID, str, str, str, str]],
    hr_user_id: UUID,  # [MỚI] Truyền thêm ID của HR để query template
    hr_email: str,
    hr_name: str,
):
    db = SessionLocal()
    try:
        # Mẫu tuỳ chỉnh của HR (nếu có), gom theo type: {"accepted": obj, "rejected": obj}
        template_map, attachment_map = _load_hr_templates(db, hr_user_id)

        for item_id, cand_email, cand_name, jd_title, cand_status in items_to_notify:
            # Mỗi ứng viên là một khối try RIÊNG: một mẫu mail lỗi hay một item bị xoá
            # giữa đường không được phép chặn mail của những người còn lại trong lô.
            try:
                result = send_shortlist_email(
                    to_email=cand_email,
                    hr_email=hr_email,
                    hr_name=hr_name,
                    candidate_name=cand_name or "Ứng viên",
                    jd_title=jd_title,
                    status=cand_status,
                    custom_template=template_map.get(cand_status),
                    attachments=attachment_map.get(cand_status),
                )
                _record_send_result(db, item_id, cand_status, result)
            except Exception as e:
                print(f"[ERROR] Lỗi khi gửi mail shortlist item {item_id}: {e}")
                db.rollback()
    except Exception as e:
        print(f"[ERROR] Lỗi tiến trình chạy nền gửi mail Shortlist: {e}")
        db.rollback()
    finally:
        db.close()

# ────────────────────────────────────────────────────────────
# Router 1: shortlists lồng dưới một JD (tạo / liệt kê)
# ────────────────────────────────────────────────────────────
# Shortlist thuộc pipeline tuyển dụng -> chỉ HR (không phải admin).
jd_shortlist_router = APIRouter(
    prefix="/jds",
    tags=["Shortlists"],
    dependencies=[Depends(require_role("hr_staff"))],
)


@jd_shortlist_router.post(
    "/{jd_id}/shortlists",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.ShortlistResponse,
)
def create_shortlist(
    jd_id: UUID,
    payload: schemas.ShortlistCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Tạo một shortlist mới cho vị trí tuyển dụng.

    Trùng tên bị TỪ CHỐI (409) chứ không lặng lẽ tạo thêm: một vị trí có hai danh
    sách cùng tên thì dropdown trên màn hình Shortlisting hiện hai dòng y hệt nhau và
    HR không có cách nào biết mình đang mở cái nào.
    """
    jd = get_owned_jd(db, jd_id, current_user)
    ten = " ".join(payload.name.split())
    if not ten:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tên danh sách không được để trống.")

    shortlist = models.Shortlist(jd_id=jd.id, name=ten, created_by=current_user.id)
    db.add(shortlist)
    try:
        db.commit()
    except IntegrityError:
        # Chốt cuối là unique index uq_shortlists_jd_ten. Bắt ở đây thay vì chỉ tra
        # trước khi ghi, vì tra-rồi-ghi vẫn hở khi HR bấm nút hai lần thật nhanh —
        # hai request cùng đọc "chưa có" rồi cùng INSERT.
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Vị trí này đã có danh sách rút gọn tên “{ten}”. Hãy đặt tên khác.",
        )
    db.refresh(shortlist)

    return schemas.ShortlistResponse(
        id=shortlist.id,
        jd_id=shortlist.jd_id,
        name=shortlist.name,
        created_by=shortlist.created_by,
        created_at=shortlist.created_at,
        items=[],
    )


@jd_shortlist_router.get(
    "/{jd_id}/shortlists",
    response_model=list[schemas.ShortlistListItem],
)
def list_shortlists(
    jd_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Liệt kê các shortlist của một JD (kèm số ứng viên)."""
    jd = get_owned_jd(db, jd_id, current_user)
    shortlists = (
        db.query(models.Shortlist)
        .filter(models.Shortlist.jd_id == jd.id)
        .order_by(models.Shortlist.created_at.desc())
        .all()
    )
    return [
        schemas.ShortlistListItem(
            id=s.id,
            jd_id=s.jd_id,
            name=s.name,
            item_count=len(s.items),
            created_at=s.created_at,
        )
        for s in shortlists
    ]


# ────────────────────────────────────────────────────────────
# Router 2: thao tác trên một shortlist cụ thể
# ────────────────────────────────────────────────────────────
shortlist_router = APIRouter(
    prefix="/shortlists",
    tags=["Shortlists"],
    dependencies=[Depends(require_role("hr_staff"))],
)


@shortlist_router.get("/{shortlist_id}", response_model=schemas.ShortlistResponse)
def get_shortlist(
    shortlist_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Chi tiết một shortlist kèm danh sách ứng viên (sắp theo điểm giảm dần)."""
    shortlist = _get_shortlist_or_404(db, shortlist_id, current_user)

    items = [_item_response(item) for item in shortlist.items]
    # Ứng viên có điểm xếp trước, điểm cao trước; chưa có điểm (None) xếp cuối.
    #
    # CHỐT PHÁ HOÀ là created_at của CV rồi tới id — CHỦ Ý dùng cùng một chốt với
    # leaderboard (GET /jds/{id}/candidates) chứ không phải added_at của shortlist item.
    # Trước đây shortlist phá hoà theo "lúc được thêm vào shortlist", nên hai ứng viên
    # trùng điểm hiện thứ tự này ở tab Leaderboard và thứ tự ngược lại ở tab Shortlist.
    items.sort(key=lambda i: score_sort_key(i.candidate))

    return schemas.ShortlistResponse(
        id=shortlist.id,
        jd_id=shortlist.jd_id,
        name=shortlist.name,
        created_by=shortlist.created_by,
        created_at=shortlist.created_at,
        items=items,
    )


@shortlist_router.delete("/{shortlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shortlist(
    shortlist_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Xóa cả shortlist (kèm các item bên trong, do cascade)."""
    shortlist = _get_shortlist_or_404(db, shortlist_id, current_user)
    # Chụp lại TRƯỚC khi xóa — sau db.delete() object không còn đọc được.
    removed = {
        "name": shortlist.name,
        "jd_id": str(shortlist.jd_id),
        "items": len(shortlist.items),
    }
    db.delete(shortlist)
    db.commit()

    write_audit_log(
        db, user_id=current_user.id, action="DELETE_SHORTLIST", entity_type="shortlist",
        entity_id=shortlist_id,
        old_data=removed,
        new_data=None,  # đã xóa -> không có trạng thái "sau"
    )


@shortlist_router.post(
    "/{shortlist_id}/items",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.ShortlistItemResponse,
)
def add_item(
    shortlist_id: UUID,
    payload: schemas.ShortlistItemAdd,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Thêm 1 ứng viên vào shortlist. Ứng viên phải thuộc đúng JD của shortlist."""
    shortlist = _get_shortlist_or_404(db, shortlist_id, current_user)

    candidate = get_owned_candidate(db, payload.candidate_id, current_user)

    # Ứng viên phải cùng JD với shortlist (tránh xếp nhầm ứng viên vị trí khác).
    if candidate.jd_id != shortlist.jd_id:
        raise HTTPException(
            status_code=400,
            detail="Ứng viên không thuộc vị trí tuyển dụng của shortlist này.",
        )

    # Chống thêm trùng cùng một ứng viên vào một shortlist.
    existing = (
        db.query(models.ShortlistItem)
        .filter(
            models.ShortlistItem.shortlist_id == shortlist.id,
            models.ShortlistItem.cv_id == candidate.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Ứng viên đã có trong shortlist này.",
        )

    item = models.ShortlistItem(shortlist_id=shortlist.id, cv_id=candidate.id)
    db.add(item)
    db.commit()
    db.refresh(item)

    return _item_response(item)


@shortlist_router.patch(
    "/{shortlist_id}/items/{item_id}",
    response_model=schemas.ShortlistItemResponse,
)
def update_item_status(
    shortlist_id: UUID,
    item_id: UUID,
    payload: schemas.ShortlistItemStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """HR quyết định ứng viên trong shortlist: accepted / rejected / pending."""
    # Chốt quyền trên shortlist trước: thiếu bước này thì chỉ cần đoán đúng cặp
    # (shortlist_id, item_id) là sửa/xoá được dữ liệu của tài khoản khác.
    shortlist = _get_shortlist_or_404(db, shortlist_id, current_user)
    item = (
        db.query(models.ShortlistItem)
        .filter(
            models.ShortlistItem.id == item_id,
            models.ShortlistItem.shortlist_id == shortlist.id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy ứng viên trong shortlist.")

    old_status = item.candidate_status
    item.candidate_status = payload.candidate_status

    # Đổi quyết định -> lỗi gửi mail của quyết định CŨ hết liên quan: xoá đi để dòng đó
    # quay về "Chưa gửi" cho quyết định mới, thay vì treo mãi một thông báo lỗi thuộc về
    # bức thư khác. Giữ nguyên notified_at/notified_status (lịch sử ai đã nhận thư gì) và
    # KHÔNG chạm vào trạng thái "sending" — lúc đó vẫn còn một mail đang bay.
    if old_status != payload.candidate_status and getattr(item, "notify_state", None) == "failed":
        item.notify_state = None
        item.notify_error_code = None
        item.notify_error = None

    db.commit()
    db.refresh(item)

    # Nhận/loại một ứng viên là quyết định tuyển dụng cuối cùng -> phải kiểm toán được.
    if old_status != item.candidate_status:
        write_audit_log(
            db, user_id=current_user.id, action="UPDATE_CANDIDATE_STATUS",
            entity_type="shortlist_item", entity_id=item.id,
            old_data={"candidate_status": old_status, "cv_id": str(item.cv_id)},
            new_data={"candidate_status": item.candidate_status, "cv_id": str(item.cv_id)},
        )
    return _item_response(item)


@shortlist_router.delete(
    "/{shortlist_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_item(
    shortlist_id: UUID,
    item_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Gỡ 1 ứng viên khỏi shortlist (không xóa ứng viên khỏi hệ thống)."""
    # Chốt quyền trên shortlist trước: thiếu bước này thì chỉ cần đoán đúng cặp
    # (shortlist_id, item_id) là sửa/xoá được dữ liệu của tài khoản khác.
    shortlist = _get_shortlist_or_404(db, shortlist_id, current_user)
    item = (
        db.query(models.ShortlistItem)
        .filter(
            models.ShortlistItem.id == item_id,
            models.ShortlistItem.shortlist_id == shortlist.id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy ứng viên trong shortlist.")

    db.delete(item)
    db.commit()

@shortlist_router.post(
    "/{shortlist_id}/send-notifications",
    status_code=status.HTTP_200_OK,
    response_model=schemas.ShortlistNotifyResponse,
)
def send_shortlist_notifications(
    shortlist_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Quét danh sách ứng viên trong shortlist, tự động gửi mail kết quả (accepted/rejected)
    trong chế độ nền (background task) và chống gửi lặp lại.

    Ứng viên KHÔNG gửi được (thiếu email, email sai định dạng) được GHI NHẬN lý do lên
    chính item đó rồi báo số lượng trong kết quả trả về — trước đây họ bị loại trong im
    lặng, nên HR tưởng cả shortlist đã được thông báo.
    """
    shortlist = _get_shortlist_or_404(db, shortlist_id, current_user)
    jd_title = shortlist.jd.title if shortlist.jd else "Vị trí tuyển dụng"
    now = datetime.now(timezone.utc)

    valid_items: list[tuple[UUID, str, str, str, str]] = []
    counts = {
        "no_email": 0,
        "invalid_email": 0,
        "already_sent": 0,
        "not_decided": 0,
        "in_flight": 0,
    }

    for item in shortlist.items:
        verdict, code, message = _classify_notify_target(item, now)
        if verdict == "send":
            # Đánh dấu "sending" NGAY: UI hiện "Đang gửi…" thay vì "Chưa gửi" trong lúc
            # tiến trình nền chạy, và lần bấm thứ hai không xếp hàng trùng người này.
            item.notify_state = "sending"
            item.notify_error_code = None
            item.notify_error = None
            item.notify_last_attempt_at = now
            valid_items.append(
                (
                    item.id,
                    item.cv.email,
                    item.cv.name,
                    jd_title,
                    item.candidate_status,
                )
            )
        else:
            counts[verdict] += 1
            if code:
                _mark_notify_failure(item, code, message, attempted=False, now=now)

    db.commit()

    if valid_items:
        # Đẩy tác vụ vào BackgroundTasks để API trả kết quả về UI ngay lập tức
        background_tasks.add_task(
            _background_send_notifications,
            items_to_notify=valid_items,
            hr_user_id=current_user.id,
            hr_email=current_user.email,
            hr_name=current_user.name or "HR Staff",
        )

        # Ghi log kiểm toán cho hành động gửi email hàng loạt
        write_audit_log(
            db,
            user_id=current_user.id,
            action="SEND_SHORTLIST_EMAILS",
            entity_type="shortlist",
            entity_id=shortlist.id,
            old_data=None,
            new_data={"total_queued": len(valid_items), **counts},
        )

    # Nói rõ cả phần KHÔNG gửi được: một câu "đang gửi tới N ứng viên" đứng một mình
    # khiến HR nghĩ mọi người đã chốt đều được thông báo.
    if valid_items:
        parts = [f"Đang gửi email tới {len(valid_items)} ứng viên trong chế độ nền."]
    else:
        parts = ["Không có ứng viên nào cần gửi mail thông báo mới."]
    if counts["no_email"]:
        parts.append(f"{counts['no_email']} ứng viên bị bỏ qua vì CV không có email.")
    if counts["invalid_email"]:
        parts.append(f"{counts['invalid_email']} ứng viên có email sai định dạng.")
    if counts["in_flight"]:
        parts.append(f"{counts['in_flight']} ứng viên đang được gửi ở lô trước.")

    return schemas.ShortlistNotifyResponse(
        message=" ".join(parts),
        total_queued=len(valid_items),
        skipped_no_email=counts["no_email"],
        skipped_invalid_email=counts["invalid_email"],
        skipped_already_sent=counts["already_sent"],
        skipped_not_decided=counts["not_decided"],
        skipped_in_flight=counts["in_flight"],
    )


@shortlist_router.post(
    "/{shortlist_id}/items/{item_id}/resend",
    response_model=schemas.ShortlistItemResponse,
)
def resend_shortlist_notification(
    shortlist_id: UUID,
    item_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Gửi lại mail kết quả cho ĐÚNG MỘT ứng viên, ngay và đồng bộ.

    Khác endpoint gửi cả lô ở hai điểm, đều vì đây là nút "Thử lại" của HR:

    * KHÔNG chạy nền — HR bấm là biết kết quả ngay trong câu trả lời, thay vì phải nạp
      lại trang để đoán. Một mail, timeout SMTP 20s, đủ nhanh cho một request.
    * BỎ QUA điều kiện "đã gửi rồi thì thôi" — HR chủ động bấm thì phải gửi được, kể cả
      để gửi lại cho người đã nhận (mail vào spam, ứng viên báo chưa thấy…).

    Vẫn trả 200 kèm item ĐÃ CẬP NHẬT dù gửi thất bại: thất bại ở đây là KẾT QUẢ của
    thao tác (đã ghi vào DB), không phải request sai — trả 4xx/5xx thì frontend mất
    luôn trạng thái mới và không hiện được lý do lên đúng dòng đó.
    """
    shortlist = _get_shortlist_or_404(db, shortlist_id, current_user)
    item = (
        db.query(models.ShortlistItem)
        .filter(
            models.ShortlistItem.id == item_id,
            models.ShortlistItem.shortlist_id == shortlist.id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy ứng viên trong shortlist.")

    # Chưa chốt quyết định thì không có nội dung mail nào để gửi -> đây là request sai,
    # chặn bằng 400 (khác với "gửi mà thất bại" ở dưới).
    if item.candidate_status not in DECIDED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Hãy chốt “Chọn” hoặc “Từ chối” cho ứng viên này trước khi gửi email.",
        )

    email = ((item.cv.email if item.cv else None) or "").strip()
    if not email:
        _mark_notify_failure(
            item, ERR_NO_EMAIL,
            "CV không trích được địa chỉ email nên không thể gửi thông báo.",
            attempted=False,
        )
        db.commit()
        db.refresh(item)
        return _item_response(item)
    if not is_valid_email(email):
        _mark_notify_failure(
            item, ERR_INVALID_EMAIL,
            f"Địa chỉ email “{email}” không đúng định dạng nên không gửi được. "
            "Hãy sửa email của ứng viên rồi thử lại.",
            attempted=False,
        )
        db.commit()
        db.refresh(item)
        return _item_response(item)

    jd_title = shortlist.jd.title if shortlist.jd else "Vị trí tuyển dụng"
    template_map, attachment_map = _load_hr_templates(db, current_user.id)
    cand_status = item.candidate_status

    result = send_shortlist_email(
        to_email=email,
        hr_email=current_user.email,
        hr_name=current_user.name or "HR Staff",
        candidate_name=item.cv.name or "Ứng viên",
        jd_title=jd_title,
        status=cand_status,
        custom_template=template_map.get(cand_status),
        attachments=attachment_map.get(cand_status),
    )
    _record_send_result(db, item.id, cand_status, result)

    write_audit_log(
        db,
        user_id=current_user.id,
        action="RESEND_SHORTLIST_EMAIL",
        entity_type="shortlist_item",
        entity_id=item.id,
        old_data=None,
        new_data={
            "cv_id": str(item.cv_id),
            "candidate_status": cand_status,
            "ok": result.ok,
            "error_code": result.error_code,
        },
    )

    db.refresh(item)
    return _item_response(item)