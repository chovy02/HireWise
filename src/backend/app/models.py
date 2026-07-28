import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, ForeignKey, Float, DateTime, Boolean, Column
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # is_active: tài khoản đã XÁC MINH email hay chưa (kích hoạt qua verify-email).
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    # is_banned: admin CHỦ ĐỘNG khóa tài khoản (tách khỏi is_active để không nhầm
    # với trạng thái xác minh email). True = bị khóa, không thể đăng nhập.
    is_banned: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    role: Mapped[str] = mapped_column(String(50), default="hr_staff")
    # Mã OTP 6 chữ số gửi qua email + hạn dùng. Cột hạn dùng phải timezone-aware:
    # code so sánh với datetime.now(timezone.utc), lưu naive sẽ ném TypeError khi so sánh.
    verification_code: Mapped[str] = mapped_column(String(6), nullable=True)
    verification_code_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    jds = relationship("JobDescription", back_populates="creator")
    evaluation_overrides = relationship("EvaluationOverride", back_populates="user")
    shortlists = relationship("Shortlist", back_populates="creator")
    chat_sessions = relationship("ChatSession", back_populates="user")
    agent_logs = relationship("AgentToolLog", back_populates="user")

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False)
    sender_role: Mapped[str] = mapped_column(String(50), nullable=False) # hr_staff, ai_agent, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)      
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)   
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("ChatSession", back_populates="messages")


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    jd_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    creator = relationship("User", back_populates="jds")
    cvs = relationship("Candidate", back_populates="jd")
    evaluations = relationship("Evaluation", back_populates="jd")
    shortlists = relationship("Shortlist", back_populates="jd")

class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jd_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_descriptions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    file_hash: Mapped[str] = mapped_column(String(255), nullable=True) # Check trùng lặp CV
    source: Mapped[str] = mapped_column(String(100), nullable=True)    # email, web_upload
    status: Mapped[str] = mapped_column(String(50), default="cho_xu_ly")
    # Lý do khi status=FAILED. Không có cột này thì HR chỉ thấy chữ "Lỗi" mà không
    # biết vì sao, và không phân biệt được lỗi tạm thời (AI quá tải -> thử lại được)
    # với lỗi vĩnh viễn (CV là ảnh scan -> thử lại vô ích).
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    jd = relationship("JobDescription", back_populates="cvs")
    skills = relationship("CandidateSkill", back_populates="cv", cascade="all, delete-orphan")
    projects = relationship("CandidateProject", back_populates="candidate", cascade="all, delete-orphan")
    evaluation = relationship("Evaluation", back_populates="cv", uselist=False)
    shortlist_items = relationship("ShortlistItem", back_populates="cv")
    interview = relationship("Interview", back_populates="cv", uselist=False)

class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cv_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=True)
    evidence: Mapped[str] = mapped_column(Text, nullable=True)

    cv = relationship("Candidate", back_populates="skills")


class CandidateProject(Base):
    """Dự án trích từ CV ứng viên.

    Bảng candidate_projects đã tồn tại trong DB và pipeline vẫn ghi vào nó, nhưng
    class ORM này từng bị xóa khỏi models.py — khiến MỌI CV mà parser trích được
    mục projects đều chết với AttributeError rồi bị đánh dấu FAILED (CV không có
    projects thì vẫn chạy, nên lỗi trông như ngẫu nhiên).
    """
    __tablename__ = "candidate_projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    github_url: Mapped[str] = mapped_column(String(500), nullable=True)
    tech_stack: Mapped[dict] = mapped_column(JSONB, nullable=True)
    # 'from_cv' (parser trích) hoặc nguồn khác nếu sau này HR tự thêm.
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="from_cv")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    candidate = relationship("Candidate", back_populates="projects")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cv_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), unique=True, nullable=False)
    jd_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_descriptions.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)
    external_tool_logs: Mapped[dict] = mapped_column(JSONB, nullable=True)
    is_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    cv = relationship("Candidate", back_populates="evaluation")
    jd = relationship("JobDescription", back_populates="evaluations")
    overrides = relationship("EvaluationOverride", back_populates="evaluation")
    agent_logs = relationship("AgentToolLog", back_populates="evaluation") # Nối log tool vào evaluation


class EvaluationOverride(Base):
    __tablename__ = "evaluation_overrides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evaluations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    old_score: Mapped[float] = mapped_column(Float, nullable=False)
    new_score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    evaluation = relationship("Evaluation", back_populates="overrides")
    user = relationship("User", back_populates="evaluation_overrides")

class Shortlist(Base):
    __tablename__ = "shortlists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jd_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_descriptions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    jd = relationship("JobDescription", back_populates="shortlists")
    creator = relationship("User", back_populates="shortlists")
    items = relationship("ShortlistItem", back_populates="shortlist", cascade="all, delete-orphan")

class ShortlistItem(Base):
    __tablename__ = "shortlist_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shortlist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shortlists.id"), nullable=False)
    cv_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    candidate_status: Mapped[str] = mapped_column(String(50), default="pending") # pending, accepted, rejected
    added_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    shortlist = relationship("Shortlist", back_populates="items")
    cv = relationship("Candidate", back_populates="shortlist_items")

class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cv_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), unique=True, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=True)
    feedback_summary: Mapped[str] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")    #(pending, in_progress, completed) 

    cv = relationship("Candidate", back_populates="interview")
    questions = relationship("InterviewQuestion", back_populates="interview", cascade="all, delete-orphan", order_by="InterviewQuestion.order_index")

class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    
    expected_answer: Mapped[str] = mapped_column(Text, nullable=True)
    answer_text: Mapped[str] = mapped_column(Text, nullable=True)
    ai_evaluation: Mapped[str] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=True)
    is_ai_generated: Mapped[bool] = mapped_column(default=True)
    order_index: Mapped[int] = mapped_column(default=0)

    interview = relationship("Interview", back_populates="questions")

class AgentToolLog(Base):
    __tablename__ = "agent_tool_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Tinh chỉnh: Cho phép NULL nếu tool do hệ thống gọi tự động không qua người dùng
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # Tinh chỉnh: Bổ sung liên kết với evaluation để biết AI đang dùng tool chấm CV nào
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evaluations.id"), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_params: Mapped[dict] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False) # success, error, timeout
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="agent_logs")
    evaluation = relationship("Evaluation", back_populates="agent_logs")

class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level: Mapped[str] = mapped_column(String(20), default="INFO") # INFO, WARNING, ERROR, CRITICAL
    module: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class AILog(Base):
    __tablename__ = "ai_logs"

    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String, index=True)  # Ví dụ: cv_extractor, interviewer, comparator
    prompt = Column(Text, nullable=True)     # Nội dung prompt gửi cho Gemini
    completion = Column(Text, nullable=True) # Kết quả JSON/Text Gemini trả về
    total_tokens = Column(Integer, default=0)# Số token tiêu thụ
    latency_ms = Column(Float, default=0.0)  # Thời gian phản hồi (tính bằng ms)
    is_error = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False) # VD: UPDATE_ROLE, DELETE_JD
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False) # VD: user, job_description
    entity_id: Mapped[str] = mapped_column(String(255), nullable=True)
    old_data: Mapped[dict] = mapped_column(JSONB, nullable=True) # Dữ liệu trước khi sửa
    new_data: Mapped[dict] = mapped_column(JSONB, nullable=True) # Dữ liệu sau khi sửa
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # Loại thông báo: 'info' (xanh dương), 'warning' (vàng), 'alert' (đỏ)
    type: Mapped[str] = mapped_column(String(50), default="info") 
    is_active: Mapped[bool] = mapped_column(Boolean, default=True) # Bật/Tắt hiển thị
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    creator = relationship("User")