import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, cast, Integer
from sqlalchemy.orm import Session
import csv
import io
import json
from fastapi.responses import StreamingResponse

from app import models, schemas
from app.core.dependencies import require_role
from app.core.dependencies import get_current_user # Dùng để lấy ID của admin đang tạo thông báo
from app.database import get_db
from app.services.logging import write_audit_log

# ==========================================
# HELPERS
# ==========================================

def _clamp(limit: int, lo: int = 1, hi: int = 500) -> int:
    return min(max(limit, lo), hi)


def _since_aware(hours: Optional[int]) -> Optional[datetime]:
    """Mốc thời gian bắt đầu cửa sổ lọc, dạng CÓ timezone.

    Dùng cho ai_logs.created_at (kiểu timestamptz). hours=None/0 = không giới hạn.
    """
    if not hours:
        return None
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _since_naive(hours: Optional[int]) -> Optional[datetime]:
    """Như `_since_aware` nhưng BỎ timezone.

    audit_logs / agent_tool_logs / system_logs dùng cột `timestamp without time
    zone` lưu giờ UTC; so sánh với datetime có tz sẽ bị Postgres từ chối.
    """
    if not hours:
        return None
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)


# ==========================================
# SCHEMAS (Định nghĩa dữ liệu trả về)
# ==========================================

# 1. Schemas cho AI Monitoring
class AILogResponse(BaseModel):
    id: int
    agent_name: Optional[str] = None
    prompt: Optional[str] = None
    completion: Optional[str] = None
    total_tokens: int
    latency_ms: float
    is_error: bool
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class AIAgentStat(BaseModel):
    """Thống kê tách theo từng agent — để biết agent NÀO đang đắt/chậm/hay lỗi."""
    agent_name: str
    requests: int
    errors: int
    error_rate: float
    avg_latency_ms: float
    total_tokens: int

class AIStatsResponse(BaseModel):
    total_requests: int
    error_rate: float
    avg_latency_ms: float
    total_tokens: int
    # Độ trễ chậm nhất — 1 request 30s bị chôn vùi trong số trung bình.
    max_latency_ms: float = 0.0
    # Lượt AI Agent gọi tool (bảng agent_tool_logs), tách khỏi lượt gọi LLM.
    tool_calls: int = 0
    tool_errors: int = 0
    by_agent: List[AIAgentStat] = []

class AgentToolLogResponse(BaseModel):
    """1 lần AI Agent gọi tool nghiệp vụ (search_candidates, create_jd…)."""
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    user_email: Optional[str] = None
    tool_name: str
    input_params: Optional[Any] = None
    result: Optional[Any] = None
    status: str
    created_at: datetime


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
    # Email người thực hiện, join sẵn từ bảng users: UUID rỗng nghĩa với admin.
    user_email: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    old_data: Optional[Any] = None
    new_data: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True

class AuditFiltersResponse(BaseModel):
    """Giá trị có thật trong bảng, để dropdown lọc không hiện lựa chọn rỗng."""
    actions: List[str] = []
    entity_types: List[str] = []


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
def get_ai_metrics(
    hours: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Thống kê AI trong cửa sổ `hours` giờ gần nhất (bỏ trống = toàn bộ lịch sử).

    Trả cả số tổng lẫn breakdown theo agent: chi phí token và độ trễ chỉ có ý nghĩa
    hành động được khi biết agent nào gây ra.
    """
    since = _since_aware(hours)

    q = db.query(models.AILog)
    if since is not None:
        q = q.filter(models.AILog.created_at >= since)

    total = q.count()

    # Lượt gọi tool của Agent nằm ở bảng khác (cột thời gian KHÔNG có timezone).
    tool_q = db.query(models.AgentToolLog)
    since_naive = _since_naive(hours)
    if since_naive is not None:
        tool_q = tool_q.filter(models.AgentToolLog.created_at >= since_naive)
    tool_calls = tool_q.count()
    tool_errors = tool_q.filter(models.AgentToolLog.status != "success").count()

    if total == 0:
        return AIStatsResponse(
            total_requests=0,
            error_rate=0.0,
            avg_latency_ms=0.0,
            total_tokens=0,
            max_latency_ms=0.0,
            tool_calls=tool_calls,
            tool_errors=tool_errors,
            by_agent=[],
        )

    errors = q.filter(models.AILog.is_error == True).count()  # noqa: E712
    agg = q.with_entities(
        func.avg(models.AILog.latency_ms),
        func.max(models.AILog.latency_ms),
        func.sum(models.AILog.total_tokens),
    ).one()
    avg_lat, max_lat, tot_tokens = agg

    # Breakdown theo agent trong CÙNG cửa sổ thời gian.
    rows_q = db.query(
        models.AILog.agent_name,
        func.count(models.AILog.id),
        func.sum(cast(models.AILog.is_error, Integer)),
        func.avg(models.AILog.latency_ms),
        func.sum(models.AILog.total_tokens),
    )
    if since is not None:
        rows_q = rows_q.filter(models.AILog.created_at >= since)
    rows = rows_q.group_by(models.AILog.agent_name).all()

    by_agent = []
    for name, count, err_count, a_lat, a_tokens in rows:
        count = count or 0
        err_count = int(err_count or 0)
        by_agent.append(AIAgentStat(
            agent_name=name or "(không rõ)",
            requests=count,
            errors=err_count,
            error_rate=round((err_count / count) * 100, 2) if count else 0.0,
            avg_latency_ms=round(float(a_lat or 0.0), 2),
            total_tokens=int(a_tokens or 0),
        ))
    by_agent.sort(key=lambda a: a.requests, reverse=True)

    return AIStatsResponse(
        total_requests=total,
        error_rate=round((errors / total) * 100, 2),
        avg_latency_ms=round(float(avg_lat or 0.0), 2),
        total_tokens=int(tot_tokens or 0),
        max_latency_ms=round(float(max_lat or 0.0), 2),
        tool_calls=tool_calls,
        tool_errors=tool_errors,
        by_agent=by_agent,
    )

@router.get("/ai-logs", response_model=List[AILogResponse])
def list_ai_logs(
    limit: int = 100,
    agent_name: Optional[str] = None,
    status: Optional[str] = None,   # success | error
    hours: Optional[int] = None,
    q: Optional[str] = None,        # tìm trong prompt/completion/error_message
    db: Session = Depends(get_db),
):
    """Lịch sử Prompt/Completion của AI, lọc theo agent, trạng thái, thời gian, từ khóa."""
    query = db.query(models.AILog)

    since = _since_aware(hours)
    if since is not None:
        query = query.filter(models.AILog.created_at >= since)
    if agent_name:
        query = query.filter(models.AILog.agent_name == agent_name)
    if status == "error":
        query = query.filter(models.AILog.is_error == True)  # noqa: E712
    elif status == "success":
        query = query.filter(models.AILog.is_error == False)  # noqa: E712
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            models.AILog.prompt.ilike(like),
            models.AILog.completion.ilike(like),
            models.AILog.error_message.ilike(like),
        ))

    return (
        query.order_by(models.AILog.created_at.desc())
        .limit(_clamp(limit))
        .all()
    )


@router.get("/agent-tool-logs", response_model=List[AgentToolLogResponse])
def list_agent_tool_logs(
    limit: int = 100,
    tool_name: Optional[str] = None,
    status: Optional[str] = None,   # success | error
    hours: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Lịch sử AI Agent gọi tool nghiệp vụ — tầng hành động, khác với tầng sinh chữ.

    ai_logs cho biết model nói gì; bảng này cho biết model đã LÀM gì (tra ứng viên,
    tạo JD…) với tham số nào và kết quả ra sao.
    """
    query = (
        db.query(models.AgentToolLog, models.User.email)
        .outerjoin(models.User, models.AgentToolLog.user_id == models.User.id)
    )

    since = _since_naive(hours)
    if since is not None:
        query = query.filter(models.AgentToolLog.created_at >= since)
    if tool_name:
        query = query.filter(models.AgentToolLog.tool_name == tool_name)
    if status == "error":
        query = query.filter(models.AgentToolLog.status != "success")
    elif status == "success":
        query = query.filter(models.AgentToolLog.status == "success")

    rows = (
        query.order_by(models.AgentToolLog.created_at.desc())
        .limit(_clamp(limit))
        .all()
    )
    return [
        AgentToolLogResponse(
            id=log.id,
            user_id=log.user_id,
            user_email=email,
            tool_name=log.tool_name,
            input_params=log.input_params,
            result=log.result,
            status=log.status,
            created_at=log.created_at,
        )
        for log, email in rows
    ]


# ==========================================
# IV. ROUTES: KIỂM TOÁN (AUDIT LOGS)
# ==========================================

@router.get("/audit-logs", response_model=List[AuditLogResponse])
def list_audit_logs(
    limit: int = 100,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    hours: Optional[int] = None,
    q: Optional[str] = None,   # tìm theo email người thực hiện hoặc entity_id
    db: Session = Depends(get_db),
):
    """Nhật ký kiểm toán: ai đã sửa gì, giá trị trước/sau.

    Join sẵn email người thực hiện — audit chỉ hữu ích khi đọc ra được TÊN người,
    không phải một UUID phải tra thủ công.
    """
    query = (
        db.query(models.AuditLog, models.User.email)
        .outerjoin(models.User, models.AuditLog.user_id == models.User.id)
    )

    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    if action:
        query = query.filter(models.AuditLog.action == action)
    since = _since_naive(hours)
    if since is not None:
        query = query.filter(models.AuditLog.created_at >= since)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            models.User.email.ilike(like),
            models.AuditLog.entity_id.ilike(like),
            models.AuditLog.action.ilike(like),
        ))

    rows = (
        query.order_by(models.AuditLog.created_at.desc())
        .limit(_clamp(limit))
        .all()
    )
    return [
        AuditLogResponse(
            id=log.id,
            user_id=log.user_id,
            user_email=email,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            old_data=log.old_data,
            new_data=log.new_data,
            created_at=log.created_at,
        )
        for log, email in rows
    ]


@router.get("/audit-filters", response_model=AuditFiltersResponse)
def get_audit_filters(db: Session = Depends(get_db)):
    """Danh sách action/entity_type CÓ THẬT trong bảng, cho dropdown lọc.

    Không suy ra từ trang kết quả hiện tại: khi đã lọc, tập giá trị sẽ co lại còn
    đúng lựa chọn đang chọn và admin không thoát ra được.
    """
    actions = [a for (a,) in db.query(models.AuditLog.action).distinct().all() if a]
    entities = [e for (e,) in db.query(models.AuditLog.entity_type).distinct().all() if e]
    return AuditFiltersResponse(actions=sorted(actions), entity_types=sorted(entities))


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

    write_audit_log(
        db, user_id=current_admin.id, action="CREATE_NOTIFICATION",
        entity_type="notification", entity_id=new_noti.id,
        old_data=None,
        new_data={"title": new_noti.title, "type": new_noti.type, "is_active": new_noti.is_active},
    )
    return new_noti

@router.delete("/notifications/{noti_id}", status_code=204)
def delete_notification(
    noti_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_user),
):
    """Admin xóa hẳn một thông báo khỏi hệ thống.

    Thay cho cơ chế ẩn/hiện cũ: thông báo đã phát thì luôn hiển thị với người dùng,
    admin chỉ có thể gỡ bỏ hoàn toàn (vd phát nhầm) chứ không giấu đi.
    """
    noti = db.query(models.Notification).filter(models.Notification.id == noti_id).first()
    if not noti:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")

    removed = {"title": noti.title, "message": noti.message, "type": noti.type}
    db.delete(noti)
    db.commit()

    write_audit_log(
        db, user_id=current_admin.id, action="DELETE_NOTIFICATION",
        entity_type="notification", entity_id=noti_id,
        old_data=removed,
        new_data=None,  # đã xóa -> không có trạng thái "sau"
    )

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
    """Xuất nhật ký kiểm toán ra CSV, KÈM email người thực hiện và giá trị trước/sau.

    Bản xuất thiếu before/after thì không đối chiếu được — mà đối chiếu chính là lý
    do tồn tại của nhật ký kiểm toán.
    """
    rows = (
        db.query(models.AuditLog, models.User.email)
        .outerjoin(models.User, models.AuditLog.user_id == models.User.id)
        .order_by(models.AuditLog.created_at.desc())
        .all()
    )
    
    output = io.StringIO()
    output.write('\ufeff')
    
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Người thực hiện", "Action", "Entity Type", "Entity ID",
        "Trước (JSON)", "Sau (JSON)", "Created At",
    ])

    for log, email in rows:
        writer.writerow([
            str(log.id),
            email or "Hệ thống",
            log.action,
            log.entity_type,
            log.entity_id,
            json.dumps(log.old_data, ensure_ascii=False) if log.old_data else "",
            json.dumps(log.new_data, ensure_ascii=False) if log.new_data else "",
            log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        ])
        
    output.seek(0)
    return StreamingResponse(
        output, 
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"}
    )


@router.get("/export/agent-tool-logs")
def export_agent_tool_logs_csv(db: Session = Depends(get_db)):
    """Xuất lịch sử AI Agent gọi tool nghiệp vụ ra CSV."""
    rows = (
        db.query(models.AgentToolLog, models.User.email)
        .outerjoin(models.User, models.AgentToolLog.user_id == models.User.id)
        .order_by(models.AgentToolLog.created_at.desc())
        .all()
    )

    output = io.StringIO()
    output.write('\ufeff')

    writer = csv.writer(output)
    writer.writerow([
        "ID", "Người dùng", "Tool", "Tham số (JSON)", "Kết quả (JSON)",
        "Trạng thái", "Created At",
    ])

    for log, email in rows:
        writer.writerow([
            str(log.id),
            email or "Hệ thống",
            log.tool_name,
            json.dumps(log.input_params, ensure_ascii=False) if log.input_params else "",
            json.dumps(log.result, ensure_ascii=False) if log.result else "",
            log.status,
            log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        ])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=agent_tool_logs.csv"}
    )