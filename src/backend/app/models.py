import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, ForeignKey, Float, DateTime, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="hr_staff")
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    jd = relationship("JobDescription", back_populates="cvs")
    skills = relationship("CandidateSkill", back_populates="cv", cascade="all, delete-orphan")
    evaluation = relationship("Evaluation", back_populates="cv", uselist=False)
    shortlist_items = relationship("ShortlistItem", back_populates="cv")
    interview = relationship("Interview", back_populates="cv", uselist=False)
    projects = relationship("CandidateProject", back_populates="candidate", cascade="all, delete-orphan")

class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cv_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=True)
    evidence: Mapped[str] = mapped_column(Text, nullable=True)

    cv = relationship("Candidate", back_populates="skills")

class CandidateProject(Base):
    __tablename__ = "candidate_projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    github_url: Mapped[str] = mapped_column(String(500), nullable=True)
    tech_stack: Mapped[dict] = mapped_column(JSONB, nullable=True)
    # Ví dụ: ["Python", "FastAPI", "PostgreSQL"]
    source: Mapped[str] = mapped_column(String(50), default="from_cv")
    # from_cv: trích từ CV | from_github: fetch thêm từ GitHub API
    created_at: Mapped[datetime] = mapped_column( DateTime, default=lambda: datetime.now(timezone.utc))

    candidate = relationship("Candidate", back_populates="projects")
    evaluation = relationship("ProjectEvaluation", back_populates="project", cascade="all, delete-orphan")


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
    project_evaluations = relationship("ProjectEvaluation", back_populates="evaluation_result", cascade="all, delete-orphan")

class ProjectEvaluation(Base):
    __tablename__ = "project_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidate_projects.id"), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evaluations.id"), nullable=True)
    # Điểm từng tiêu chí (0-100)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=True)
    # Mức độ liên quan tới JD
    complexity_score: Mapped[float] = mapped_column(Float, nullable=True)
    # Độ phức tạp kỹ thuật
    overall_score: Mapped[float] = mapped_column(Float, nullable=True)
    # Điểm tổng project này
    analysis: Mapped[str] = mapped_column(Text, nullable=True)
    # Claude giải thích tại sao chấm điểm vậy
    github_stats: Mapped[dict] = mapped_column(JSONB, nullable=True)
    # Dữ liệu thô từ GitHub API:
    # {
    #   "stars": 12,
    #   "forks": 3,
    #   "languages": {"Python": 80, "HTML": 20},
    #   "last_commit": "2024-01-15",
    #   "total_commits": 47,
    #   "has_readme": true,
    #   "repo_description": "..."
    # }
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=True)
    # Bằng chứng cụ thể: đoạn code, commit message...
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("CandidateProject", back_populates="evaluation")
    evaluation_result = relationship("Evaluation", back_populates="project_evaluations")


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

    cv = relationship("Candidate", back_populates="interview")
    questions = relationship("InterviewQuestion", back_populates="interview", cascade="all, delete-orphan")

class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=True)

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