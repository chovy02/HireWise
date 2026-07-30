from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.dependencies import get_current_user, require_role
from app.core.ownership import get_owned_candidate, get_owned_jd, get_owned_shortlist
from app.database import SessionLocal, get_db
from app.services.email_notification import send_shortlist_email
from app.services.logging import write_audit_log


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
    )


def _item_response(item: models.ShortlistItem) -> schemas.ShortlistItemResponse:
    return schemas.ShortlistItemResponse(
        id=item.id,
        candidate_status=item.candidate_status,
        added_at=item.added_at,
        candidate=_candidate_summary(item.cv),
        # getattr thay vì item.notified_at: hai cột này mới thêm ở migration
        # 9e35c9fe2f0f, DB chưa nâng cấp thì đọc thẳng sẽ nổ 500 trên MỌI lần mở
        # shortlist — không chỉ riêng tính năng gửi mail.
        notified_at=getattr(item, "notified_at", None),
        notified_status=getattr(item, "notified_status", None),
    )


def _get_shortlist_or_404(
    db: Session, shortlist_id: UUID, user: models.User
) -> models.Shortlist:
    """Bắt buộc truyền `user`: shortlist chỉ thấy được nếu JD chứa nó là của người này."""
    return get_owned_shortlist(db, shortlist_id, user)

def _background_send_notifications(
    items_to_notify: list[tuple[UUID, str, str, str, str]],
    hr_user_id: UUID,  # [MỚI] Truyền thêm ID của HR để query template
    hr_email: str,
    hr_name: str,
):
    db = SessionLocal()
    try:
        # [MỚI] Lấy các template tùy chỉnh của HR từ DB lên (nếu có)
        templates = db.query(models.EmailTemplate).filter(
            models.EmailTemplate.user_id == hr_user_id,
            models.EmailTemplate.is_active == True
        ).all()
        
        # Gom vào Dict để tra cứu nhanh theo type: {"accepted": obj, "rejected": obj}
        template_map = {t.template_type: t for t in templates}

        # Đọc danh sách file/ảnh MỘT LẦN cho mỗi mẫu, ngay ở đây.
        #
        # Không để send_shortlist_email tự truy vấn: nó chạy một lần cho MỖI ứng viên,
        # nên một lô 200 người sẽ thành 200 lượt query cho cùng hai bộ file. Quan hệ
        # `attachments` là lazy-load, đọc trong vòng lặp cũng cho ra đúng chuyện đó.
        attachment_map = {
            t_type: list(tpl.attachments) for t_type, tpl in template_map.items()
        }

        for item_id, cand_email, cand_name, jd_title, cand_status in items_to_notify:
            # Lấy template tương ứng với status ("accepted" / "rejected")
            custom_tpl = template_map.get(cand_status)

            success = send_shortlist_email(
                to_email=cand_email,
                hr_email=hr_email,
                hr_name=hr_name,
                candidate_name=cand_name or "Ứng viên",
                jd_title=jd_title,
                status=cand_status,
                custom_template=custom_tpl, # [MỚI] Truyền template vào đây
                attachments=attachment_map.get(cand_status),
            )
            if success:
                item = db.query(models.ShortlistItem).filter(models.ShortlistItem.id == item_id).first()
                if item:
                    item.notified_at = datetime.now(timezone.utc)
                    item.notified_status = cand_status
        db.commit()
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
    """Tạo một shortlist mới cho vị trí tuyển dụng."""
    jd = get_owned_jd(db, jd_id, current_user)

    shortlist = models.Shortlist(
        jd_id=jd.id,
        name=payload.name.strip(),
        created_by=current_user.id,
    )
    db.add(shortlist)
    db.commit()
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
    # added_at + id là chốt phá hoà: hai ứng viên cùng điểm phải luôn ra cùng một
    # thứ tự giữa các lần gọi, nếu không bảng sẽ nhảy hàng sau mỗi lần cập nhật.
    items.sort(
        key=lambda i: (
            i.candidate.score is None,
            -(i.candidate.score or 0),
            i.added_at,
            str(i.id),
        )
    )

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
    """
    shortlist = _get_shortlist_or_404(db, shortlist_id, current_user)
    jd_title = shortlist.jd.title if shortlist.jd else "Vị trí tuyển dụng"

    # Lọc các ứng viên đã chốt (accepted/rejected) và CHƯA được gửi mail lần nào
    # (hoặc trạng thái vừa thay đổi so với lần gửi trước).
    valid_items = []
    for item in shortlist.items:
        if item.candidate_status in ["accepted", "rejected"]:
            # Kiểm tra xem có cột notified_at chưa (nếu đã migrate model)
            notified_at = getattr(item, "notified_at", None)
            notified_status = getattr(item, "notified_status", None)

            if not notified_at or notified_status != item.candidate_status:
                if item.cv and item.cv.email:
                    valid_items.append(
                        (
                            item.id,
                            item.cv.email,
                            item.cv.name,
                            jd_title,
                            item.candidate_status,
                        )
                    )

    if not valid_items:
        return {
            "message": "Không có ứng viên nào cần gửi mail thông báo mới.",
            "total_queued": 0,
        }

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
        new_data={"total_queued": len(valid_items)},
    )

    return {
        "message": f"Đang tiến hành gửi email tới {len(valid_items)} ứng viên trong chế độ nền.",
        "total_queued": len(valid_items),
    }