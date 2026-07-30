import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.services.email_attachment_storage import (
    ALLOWED_INLINE_TYPES,
    MAX_ATTACHMENT_BYTES,
    delete_attachment,
    read_attachment,
    save_attachment,
)
from app.services.email_notification import DEFAULT_EMAIL_TEMPLATES

router = APIRouter(prefix="/email-templates", tags=["Email Templates"])

TEMPLATE_TYPES = ("accepted", "rejected")


def _require_valid_type(template_type: str) -> None:
    if template_type not in TEMPLATE_TYPES:
        raise HTTPException(
            status_code=400, detail="template_type chỉ được là 'accepted' hoặc 'rejected'."
        )


def _get_or_create_template(
    db: Session, user: models.User, template_type: str
) -> models.EmailTemplate:
    """Lấy mẫu của HR, tạo từ bản mặc định nếu chưa từng lưu.

    Cần thiết cho việc gắn file: file phải trỏ tới một hàng email_templates có thật,
    mà HR hoàn toàn có thể bấm "chèn ảnh" trước khi bấm "Lưu mẫu" lần nào.
    """
    template = db.query(models.EmailTemplate).filter(
        models.EmailTemplate.user_id == user.id,
        models.EmailTemplate.template_type == template_type,
    ).first()
    if template:
        return template

    default_data = DEFAULT_EMAIL_TEMPLATES[template_type]
    template = models.EmailTemplate(
        user_id=user.id,
        template_type=template_type,
        subject=default_data["subject"],
        body_template=default_data["body_template"],
        body_format="text",
        is_active=default_data["is_active"],
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def _get_owned_attachment(
    db: Session, user: models.User, template_type: str, attachment_id: uuid.UUID
) -> models.EmailTemplateAttachment:
    """Tìm file theo id NHƯNG chỉ trong mẫu của chính người đang đăng nhập.

    Join sang email_templates để lọc theo user_id: thiếu bước này thì bất kỳ HR nào
    biết id cũng tải/xoá được file của đồng nghiệp.
    """
    _require_valid_type(template_type)
    attachment = (
        db.query(models.EmailTemplateAttachment)
        .join(models.EmailTemplate)
        .filter(
            models.EmailTemplateAttachment.id == attachment_id,
            models.EmailTemplate.user_id == user.id,
            models.EmailTemplate.template_type == template_type,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Không tìm thấy file trong mẫu mail này.")
    return attachment


@router.get("", response_model=list[schemas.EmailTemplateResponse])
def get_my_templates(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr_staff"))
):
    """
    Lấy danh sách mẫu mail. Luôn trả về đủ 2 object (accepted và rejected).
    Nếu HR chưa tự chỉnh sửa dưới DB thì trả về nguyên bản format mặc định của hệ thống.
    """
    # 1. Truy vấn các template HR đã tự lưu trong DB
    db_templates = db.query(models.EmailTemplate).filter(
        models.EmailTemplate.user_id == current_user.id
    ).all()

    # Gom thành Dict theo type để dễ đối chiếu: {"accepted": obj, ...}
    saved_map = {t.template_type: t for t in db_templates}

    results = []
    for t_type in TEMPLATE_TYPES:
        if t_type in saved_map:
            # Nếu DB có -> Dùng bản của HR đã lưu
            results.append(saved_map[t_type])
        else:
            # Nếu DB chưa có -> Tạo Object tạm từ hằng số mặc định trả về cho UI
            default_data = DEFAULT_EMAIL_TEMPLATES[t_type]
            results.append(
                schemas.EmailTemplateResponse(
                    id=None, # Chưa có ID dưới DB
                    user_id=current_user.id,
                    template_type=t_type,
                    subject=default_data["subject"],
                    body_template=default_data["body_template"],
                    body_format="text",
                    is_active=default_data["is_active"],
                    updated_at=None,
                    attachments=[],
                )
            )

    return results

@router.put("/{template_type}", response_model=schemas.EmailTemplateResponse)
def upsert_template(
    template_type: str,
    payload: schemas.EmailTemplateUpsert,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr_staff"))
):
    """
    Tạo mới hoặc chỉnh sửa mẫu mail theo format riêng của HR.
    template_type chỉ nhận 'accepted' hoặc 'rejected'.
    """
    _require_valid_type(template_type)

    template = db.query(models.EmailTemplate).filter(
        models.EmailTemplate.user_id == current_user.id,
        models.EmailTemplate.template_type == template_type
    ).first()

    if not template:
        # Nếu chưa có -> Tạo mới
        template = models.EmailTemplate(
            user_id=current_user.id,
            template_type=template_type,
            subject=payload.subject,
            body_template=payload.body_template,
            body_format=payload.body_format,
            is_active=payload.is_active
        )
        db.add(template)
    else:
        # Nếu đã có -> Cập nhật
        template.subject = payload.subject
        template.body_template = payload.body_template
        template.body_format = payload.body_format
        template.is_active = payload.is_active

    db.commit()
    db.refresh(template)
    return template


# ────────────────────────────────────────────────────────────
# File/ảnh gắn vào mẫu mail
# ────────────────────────────────────────────────────────────


@router.post(
    "/{template_type}/attachments",
    response_model=schemas.EmailAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    template_type: str,
    file: UploadFile = File(...),
    is_inline: bool = Form(False, description="True = ảnh chèn giữa nội dung mail"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr_staff")),
):
    """Tải một file lên và gắn vào mẫu mail.

    is_inline=True dành cho ảnh chèn giữa bài: trả về content_id để nội dung HTML
    trỏ tới bằng <img src="cid:{content_id}">.
    """
    _require_valid_type(template_type)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File rỗng.")
    if len(content) > MAX_ATTACHMENT_BYTES:
        limit_mb = MAX_ATTACHMENT_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File vượt quá {limit_mb}MB. Hãy nén lại hoặc dùng liên kết tải về.",
        )

    if is_inline and file.content_type not in ALLOWED_INLINE_TYPES:
        allowed = ", ".join(sorted(ALLOWED_INLINE_TYPES))
        raise HTTPException(
            status_code=400,
            detail=f"Ảnh chèn giữa bài chỉ nhận: {allowed}.",
        )

    template = _get_or_create_template(db, current_user, template_type)

    attachment_id = uuid.uuid4()
    path = save_attachment(attachment_id, file.filename, content)

    attachment = models.EmailTemplateAttachment(
        id=attachment_id,
        template_id=template.id,
        filename=file.filename or f"file-{attachment_id}",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        file_path=path,
        is_inline=is_inline,
        # content_id phải hợp lệ trong header Content-ID và ổn định: dùng luôn id.
        content_id=f"att-{attachment_id}" if is_inline else None,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


@router.get("/{template_type}/attachments/{attachment_id}/content")
def download_attachment(
    template_type: str,
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr_staff")),
):
    """Trả bytes của file.

    Trình soạn thảo cần endpoint này để HIỆN LẠI ảnh đã chèn: nội dung lưu trong DB
    chỉ có "cid:att-..." (thứ mà mail cần), không phải URL trình duyệt tải được.
    """
    attachment = _get_owned_attachment(db, current_user, template_type, attachment_id)
    data = read_attachment(attachment.file_path)
    if data is None:
        raise HTTPException(status_code=410, detail="File không còn trên đĩa.")
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={"Content-Disposition": f'inline; filename="{attachment.filename}"'},
    )


@router.delete(
    "/{template_type}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_attachment(
    template_type: str,
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr_staff")),
):
    """Xoá file khỏi mẫu (và khỏi đĩa).

    KHÔNG tự sửa nội dung HTML để bỏ thẻ <img> đang trỏ tới ảnh vừa xoá: nội dung là
    của HR, sửa ngầm dễ làm mất chỗ khác. Frontend chịu trách nhiệm bỏ thẻ ảnh khi HR
    xoá ảnh, còn lúc gửi thì thiếu file chỉ bị bỏ qua kèm cảnh báo (xem _build_message).
    """
    attachment = _get_owned_attachment(db, current_user, template_type, attachment_id)
    path = attachment.file_path
    db.delete(attachment)
    db.commit()
    delete_attachment(path)
