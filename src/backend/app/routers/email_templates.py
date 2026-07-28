from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.services.email_notification import DEFAULT_EMAIL_TEMPLATES

router = APIRouter(prefix="/email-templates", tags=["Email Templates"])

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
    for t_type in ["accepted", "rejected"]:
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
                    is_active=default_data["is_active"],
                    updated_at=None
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
    if template_type not in ["accepted", "rejected"]:
        raise HTTPException(status_code=400, detail="template_type chỉ được là 'accepted' hoặc 'rejected'.")

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
            is_active=payload.is_active
        )
        db.add(template)
    else:
        # Nếu đã có -> Cập nhật
        template.subject = payload.subject
        template.body_template = payload.body_template
        template.is_active = payload.is_active

    db.commit()
    db.refresh(template)
    return template