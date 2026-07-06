from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app import models, schemas
from app.schemas.compare import CompareRequest, CompareResponse
from app.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.services.ai_agent.comparator import compare_candidates_ai

router = APIRouter(
    prefix="/compare",
    tags=["Compare"],
    dependencies=[Depends(require_role("hr_staff"))],
)

@router.post("", response_model=CompareResponse)
def compare_candidates(
    payload: CompareRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1. Truy xuất các ứng viên từ Database
    candidates = db.query(models.Candidate).filter(models.Candidate.id.in_(payload.candidate_ids)).all()
    
    if len(candidates) != len(payload.candidate_ids):
        raise HTTPException(status_code=404, detail="Một hoặc nhiều ứng viên không tồn tại trong hệ thống.")
        
    # 2. Ràng buộc nghiệp vụ: Các ứng viên phải ứng tuyển cùng một JD
    jd_id = candidates[0].jd_id
    if any(c.jd_id != jd_id for c in candidates):
        raise HTTPException(status_code=400, detail="Không thể so sánh chéo. Các ứng viên phải ứng tuyển cùng một vị trí (JD).")
        
    jd = db.query(models.JobDescription).filter(models.JobDescription.id == jd_id).first()
    
    # 3. Trích xuất và rút gọn dữ liệu gửi cho AI (Tránh gửi nguyên raw_text làm tràn Token LLM)
    candidates_info = []
    for c in candidates:
        if c.status != "COMPLETED":
            raise HTTPException(
                status_code=400, 
                detail=f"Ứng viên {c.name or c.id} chưa được xử lý hoàn tất."
            )
            
        candidates_info.append({
            "candidate_id": str(c.id),
            "name": c.name or "Chưa cập nhật tên",
            "full_cv_text": c.raw_text,
            "overall_score": c.evaluation.score if c.evaluation else 0
        })
        
    # 4. Gọi AI Agent để so sánh
    ai_result = compare_candidates_ai(
        jd_requirements=jd.requirements,
        candidates_info=candidates_info,
        aspect=payload.aspect
    )
    
    if "error" in ai_result:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=ai_result["error"])
        
    return CompareResponse(
        recommendation=ai_result.get("recommendation", "Không thể đưa ra đề xuất."),
        detailed_comparison=ai_result.get("detailed_comparison", "Không có dữ liệu so sánh chi tiết.")
    )