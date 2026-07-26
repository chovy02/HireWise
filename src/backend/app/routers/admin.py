import uuid
from datetime import datetime
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
import csv
import io
from fastapi.responses import StreamingResponse

from app import models, schemas
from app.core.dependencies import require_role
from app.core.dependencies import get_current_user # Dùng để lấy ID của admin đang tạo thông báo
from app.database import get_db

# ==========================================
# SCHEMAS (Định nghĩa dữ liệu trả về)
# ==========================================

# 1. Schemas cho AI Monitoring
class AILogResponse(BaseModel):
    id: int
    agent_name: str
    prompt: Optional[str] = None
    completion: Optional[str] = None
    total_tokens: int
    latency_ms: float
    is_error: bool
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class AIStatsResponse(BaseModel):
    total_requests: int
    error_rate: float
    avg_latency_ms: float
    total_tokens: int


# 5. Schemas cho Thông báo (Notifications)
class NotificationCreate(BaseModel):
    title: str
    message: str
    type: str = "info"
    is_active: bool = True

class NotificationResponse(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    type: str
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True

# 3. Schemas cho Nhật ký kiểm toán (Audit Logs)
class AuditLogResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    old_data: Optional[dict] = None
    new_data: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


# 4. Schemas cho Báo cáo doanh nghiệp (Business Analytics)
class BusinessMetricsResponse(BaseModel):
    total_jds: int
    active_jds: int
    total_candidates: int
    total_interviews: int
    avg_candidate_score: float


# ==========================================
# ROUTER CONFIG
# ==========================================
# Khu vực giám sát chỉ dành cho Admin (RBAC)

router = APIRouter(
    prefix="/admin",
    tags=["Admin Monitoring & Management"],
    dependencies=[Depends(require_role("admin"))],
)


# ==========================================
# I. ROUTES: LOG HỆ THỐNG CƠ BẢN
# ==========================================

@router.get("/system-logs", response_model=List[schemas.SystemLogResponse])
def list_system_logs(
    limit: int = 200,
    db: Session = Depends(get_db),
):
    """NFR-8: Xem log hoạt động đăng nhập + hành động quản trị (mới nhất trước)."""
    return (
        db.query(models.SystemLog)
        .order_by(models.SystemLog.created_at.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )


# ==========================================
# II. ROUTES: GIÁM SÁT AI (AI MONITORING)
# ==========================================

@router.get("/ai-metrics", response_model=AIStatsResponse)
def get_ai_metrics(db: Session = Depends(get_db)):
    """Tính toán thống kê AI: Tổng request, Tỷ lệ lỗi, Trễ TB, Tổng Token."""
    total = db.query(models.AILog).count()
    
    if total == 0:
        return AIStatsResponse(
            total_requests=0, 
            error_rate=0.0, 
            avg_latency_ms=0.0, 
            total_tokens=0
        )

    errors = db.query(models.AILog).filter(models.AILog.is_error == True).count()
    avg_lat = db.query(func.avg(models.AILog.latency_ms)).scalar() or 0.0
    tot_tokens = db.query(func.sum(models.AILog.total_tokens)).scalar() or 0

    return AIStatsResponse(
        total_requests=total,
        error_rate=round((errors / total) * 100, 2),
        avg_latency_ms=round(avg_lat, 2),
        total_tokens=tot_tokens
    )

@router.get("/ai-logs", response_model=List[AILogResponse])
def list_ai_logs(
    limit: int = 100, 
    db: Session = Depends(get_db)
):
    """Lấy danh sách lịch sử Prompt/Completion của AI."""
    return (
        db.query(models.AILog)
        .order_by(models.AILog.created_at.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )


# ==========================================
# IV. ROUTES: KIỂM TOÁN (AUDIT LOGS)
# ==========================================

@router.get("/audit-logs", response_model=List[AuditLogResponse])
def list_audit_logs(
    limit: int = 100, 
    entity_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Xem nhật ký kiểm toán (Ai đã sửa gì, Before/After). Có thể lọc theo entity_type (vd: user, jd)."""
    query = db.query(models.AuditLog)
    
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
        
    return (
        query.order_by(models.AuditLog.created_at.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )


# ==========================================
# V. ROUTES: BÁO CÁO DOANH NGHIỆP (BUSINESS ANALYTICS)
# ==========================================

@router.get("/business-metrics", response_model=BusinessMetricsResponse)
def get_business_metrics(db: Session = Depends(get_db)):
    """Lấy số liệu tổng quan về hoạt động tuyển dụng cho Dashboard."""
    total_jds = db.query(models.JobDescription).count()
    active_jds = db.query(models.JobDescription).filter(models.JobDescription.status == "active").count()
    total_candidates = db.query(models.Candidate).count()
    total_interviews = db.query(models.Interview).count()
    
    # Tính điểm trung bình của tất cả ứng viên đã được AI chấm
    avg_score = db.query(func.avg(models.Evaluation.score)).scalar() or 0.0

    return BusinessMetricsResponse(
        total_jds=total_jds,
        active_jds=active_jds,
        total_candidates=total_candidates,
        total_interviews=total_interviews,
        avg_candidate_score=round(avg_score, 2)
    )

# ==========================================
# VI. ROUTES: TRUNG TÂM THÔNG BÁO (NOTIFICATIONS)
# ==========================================

@router.get("/notifications", response_model=List[NotificationResponse])
def get_all_notifications(db: Session = Depends(get_db)):
    """Admin xem danh sách toàn bộ thông báo (cả bật và tắt)."""
    return db.query(models.Notification).order_by(models.Notification.created_at.desc()).all()

@router.post("/notifications", response_model=NotificationResponse)
def create_notification(
    noti_in: NotificationCreate, 
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_user)
):
    """Admin tạo một thông báo mới để bắn lên giao diện."""
    new_noti = models.Notification(
        title=noti_in.title,
        message=noti_in.message,
        type=noti_in.type,
        is_active=noti_in.is_active,
        created_by=current_admin.id
    )
    db.add(new_noti)
    db.commit()
    db.refresh(new_noti)
    return new_noti

@router.put("/notifications/{noti_id}/toggle", response_model=NotificationResponse)
def toggle_notification(noti_id: uuid.UUID, db: Session = Depends(get_db)):
    """Admin bật/tắt (ẩn/hiện) một thông báo."""
    noti = db.query(models.Notification).filter(models.Notification.id == noti_id).first()
    if not noti:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
    
    noti.is_active = not noti.is_active
    db.commit()
    db.refresh(noti)
    return noti

# ==========================================
# VII. ROUTES: TRUNG TÂM TRÍCH XUẤT (EXPORT CENTER)
# ==========================================

@router.get("/export/system-logs")
def export_system_logs_csv(db: Session = Depends(get_db)):
    """Xuất lịch sử hệ thống ra file CSV."""
    logs = db.query(models.SystemLog).order_by(models.SystemLog.created_at.desc()).all()
    
    output = io.StringIO()
    output.write('\ufeff') # Ghi Byte Order Mark (BOM) để Excel đọc đúng tiếng Việt UTF-8
    
    writer = csv.writer(output)
    writer.writerow(["ID", "Level", "Module", "Message", "Created At"]) # Tiêu đề cột
    
    for log in logs:
        writer.writerow([
            log.id, 
            log.level, 
            log.module, 
            log.message, 
            log.created_at.strftime("%Y-%m-%d %H:%M:%S")
        ])
        
    output.seek(0)
    return StreamingResponse(
        output, 
        media_type="text/csv", 
        headers={"Content-Disposition": "attachment; filename=system_logs.csv"}
    )

@router.get("/export/ai-logs")
def export_ai_logs_csv(db: Session = Depends(get_db)):
    """Xuất lịch sử giám sát AI ra file CSV."""
    logs = db.query(models.AILog).order_by(models.AILog.created_at.desc()).all()
    
    output = io.StringIO()
    output.write('\ufeff')
    
    writer = csv.writer(output)
    writer.writerow(["ID", "Agent Name", "Prompt", "Completion", "Tokens", "Latency (ms)", "Is Error", "Created At"])
    
    for log in logs:
        writer.writerow([
            log.id, 
            log.agent_name, 
            log.prompt, 
            log.completion, 
            log.total_tokens, 
            log.latency_ms,
            "Lỗi" if log.is_error else "Thành công",
            log.created_at.strftime("%Y-%m-%d %H:%M:%S")
        ])
        
    output.seek(0)
    return StreamingResponse(
        output, 
        media_type="text/csv", 
        headers={"Content-Disposition": "attachment; filename=ai_logs.csv"}
    )

@router.get("/export/audit-logs")
def export_audit_logs_csv(db: Session = Depends(get_db)):
    """Xuất nhật ký kiểm toán (Ai đã sửa gì) ra file CSV."""
    logs = db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).all()
    
    output = io.StringIO()
    output.write('\ufeff')
    
    writer = csv.writer(output)
    writer.writerow(["ID", "User ID", "Action", "Entity Type", "Entity ID", "Created At"])
    
    for log in logs:
        writer.writerow([
            str(log.id), 
            str(log.user_id) if log.user_id else "System", 
            log.action, 
            log.entity_type, 
            log.entity_id, 
            log.created_at.strftime("%Y-%m-%d %H:%M:%S")
        ])
        
    output.seek(0)
    return StreamingResponse(
        output, 
        media_type="text/csv", 
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"}
    )