from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.dependencies import get_current_user, require_role
from app.core.ownership import get_owned_candidate, get_owned_jd, get_owned_shortlist
from app.database import get_db
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
    )


def _get_shortlist_or_404(
    db: Session, shortlist_id: UUID, user: models.User
) -> models.Shortlist:
    """Bắt buộc truyền `user`: shortlist chỉ thấy được nếu JD chứa nó là của người này."""
    return get_owned_shortlist(db, shortlist_id, user)


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
    items.sort(key=lambda i: (i.candidate.score is None, -(i.candidate.score or 0)))

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
