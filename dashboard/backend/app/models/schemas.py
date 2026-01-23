"""Pydantic models for API request/response schemas."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# Enums
class WorkflowStatus(str, Enum):
    """Workflow status values."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class PhaseStatus(str, Enum):
    """Phase status values."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskStatus(str, Enum):
    """Task status values."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class AgentType(str, Enum):
    """Agent types."""

    CLAUDE = "claude"
    CURSOR = "cursor"
    GEMINI = "gemini"


# Project models
class ProjectSummary(BaseModel):
    """Summary of a project."""

    name: str
    path: str
    created_at: Optional[str] = None
    current_phase: int = 0
    has_documents: bool = False
    has_product_spec: bool = False
    has_claude_md: bool = False
    has_gemini_md: bool = False
    has_cursor_rules: bool = False


class GitInfo(BaseModel):
    """Git information for a project."""

    branch: str
    commit: str
    repo_url: Optional[str] = None
    is_dirty: bool = False
    last_commit_msg: Optional[str] = None


class ProjectStatus(BaseModel):
    """Detailed project status."""

    name: str
    path: str
    config: Optional[dict] = None
    state: Optional[dict] = None
    files: dict[str, bool] = Field(default_factory=dict)
    phases: dict[str, dict] = Field(default_factory=dict)
    git_info: Optional[GitInfo] = None


class ProjectInitRequest(BaseModel):
    """Request to initialize a new project."""

    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class ProjectInitResponse(BaseModel):
    """Response from project initialization."""

    success: bool
    project_dir: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


class FolderInfo(BaseModel):
    """Information about a workspace folder."""

    name: str
    path: str
    is_project: bool = False
    has_workflow: bool = False
    has_product_md: bool = False


# Workflow models
class WorkflowStatusResponse(BaseModel):
    """Workflow status response."""

    mode: str = "langgraph"
    status: WorkflowStatus
    project: Optional[str] = None
    current_phase: Optional[int] = None
    phase_status: dict[str, str] = Field(default_factory=dict)
    pending_interrupt: Optional[dict] = None
    message: Optional[str] = None


class WorkflowHealthResponse(BaseModel):
    """Workflow health check response."""

    status: str  # healthy, degraded, unhealthy
    project: Optional[str] = None
    current_phase: Optional[int] = None
    phase_status: Optional[str] = None
    iteration_count: int = 0
    last_updated: Optional[str] = None
    agents: dict[str, bool] = Field(default_factory=dict)
    langgraph_enabled: bool = False
    has_context: bool = False
    total_commits: int = 0


class WorkflowStartRequest(BaseModel):
    """Request to start a workflow."""

    start_phase: int = Field(default=1, ge=1, le=5)
    end_phase: int = Field(default=5, ge=1, le=5)
    skip_validation: bool = False
    autonomous: bool = False


class WorkflowStartResponse(BaseModel):
    """Response from starting a workflow."""

    success: bool
    mode: str = "langgraph"
    paused: bool = False
    message: Optional[str] = None
    error: Optional[str] = None
    results: Optional[dict] = None


class ResumeRequest(BaseModel):
    """Request to resume a paused workflow."""

    autonomous: bool = False
    human_response: Optional[dict] = None


class WorkflowRollbackRequest(BaseModel):
    """Request to rollback workflow."""

    phase: int = Field(..., ge=1, le=5)


class WorkflowRollbackResponse(BaseModel):
    """Response from workflow rollback."""

    success: bool
    rolled_back_to: Optional[str] = None
    current_phase: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None


# Task models
class TaskInfo(BaseModel):
    """Task information."""

    id: str
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    dependencies: list[str] = Field(default_factory=list)
    files_to_create: list[str] = Field(default_factory=list)
    files_to_modify: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    complexity_score: Optional[float] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class TaskListResponse(BaseModel):
    """Response with list of tasks."""

    tasks: list[TaskInfo] = Field(default_factory=list)
    total: int = 0
    completed: int = 0
    in_progress: int = 0
    pending: int = 0
    failed: int = 0


# Agent models
class AgentStatus(BaseModel):
    """Agent status."""

    agent: AgentType
    available: bool
    last_invocation: Optional[str] = None
    total_invocations: int = 0
    success_rate: float = 0.0
    avg_duration_seconds: float = 0.0
    total_cost_usd: float = 0.0


class AgentStatusResponse(BaseModel):
    """Response with agent statuses."""

    agents: list[AgentStatus] = Field(default_factory=list)


# Audit models
class AuditEntry(BaseModel):
    """Audit entry."""

    id: str
    agent: str
    task_id: str
    session_id: Optional[str] = None
    prompt_hash: Optional[str] = None
    prompt_length: Optional[int] = None
    command_args: list[str] = Field(default_factory=list)
    exit_code: Optional[int] = None
    status: str = "pending"
    duration_seconds: Optional[float] = None
    output_length: Optional[int] = None
    error_length: Optional[int] = None
    parsed_output_type: Optional[str] = None
    cost_usd: Optional[float] = None
    model: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    timestamp: Optional[datetime] = None


class AuditQueryRequest(BaseModel):
    """Request to query audit entries."""

    agent: Optional[str] = None
    task_id: Optional[str] = None
    status: Optional[str] = None
    since: Optional[datetime] = None
    limit: int = Field(default=100, le=1000)


class AuditResponse(BaseModel):
    """Response with audit entries."""

    entries: list[AuditEntry] = Field(default_factory=list)
    total: int = 0


class AuditStatistics(BaseModel):
    """Audit statistics."""

    total: int = 0
    success_count: int = 0
    failed_count: int = 0
    timeout_count: int = 0
    success_rate: float = 0.0
    total_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    avg_duration_seconds: float = 0.0
    by_agent: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)


# Session models
class SessionInfo(BaseModel):
    """Session information."""

    session_id: str
    task_id: str
    agent: str
    created_at: str
    last_active: Optional[str] = None
    iteration: int = 0
    active: bool = True


class SessionListResponse(BaseModel):
    """Response with list of sessions."""

    sessions: list[SessionInfo] = Field(default_factory=list)


# Budget models
class BudgetStatus(BaseModel):
    """Budget status."""

    total_spent_usd: float = 0.0
    project_budget_usd: Optional[float] = None
    project_remaining_usd: Optional[float] = None
    project_used_percent: Optional[float] = None
    task_count: int = 0
    record_count: int = 0
    task_spent: dict[str, float] = Field(default_factory=dict)
    updated_at: Optional[str] = None
    enabled: bool = True


class TaskSpending(BaseModel):
    """Task spending information."""

    task_id: str
    spent_usd: float = 0.0
    budget_usd: Optional[float] = None
    remaining_usd: Optional[float] = None
    used_percent: Optional[float] = None


class BudgetReportResponse(BaseModel):
    """Response with budget report."""

    status: BudgetStatus
    task_spending: list[TaskSpending] = Field(default_factory=list)


# Feedback models
class FeedbackResponse(BaseModel):
    """Feedback from validation or verification."""

    phase: int
    agent: AgentType
    status: str  # approved, needs_changes, error
    score: Optional[float] = None
    issues: list[dict] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    timestamp: Optional[str] = None


class EscalationQuestion(BaseModel):
    """Escalation question requiring human input."""

    id: str
    question: str
    options: list[str] = Field(default_factory=list)
    context: Optional[str] = None
    created_at: str


class EscalationResponse(BaseModel):
    """Response to an escalation question."""

    question_id: str
    answer: str
    additional_context: Optional[str] = None


# Chat models
class ChatMessage(BaseModel):
    """Chat message."""

    role: str  # user, assistant, system
    content: str
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    """Chat request."""

    message: str
    project_name: Optional[str] = None
    context: Optional[dict] = None


class ChatResponse(BaseModel):
    """Chat response."""

    message: str
    streaming: bool = False


class CommandRequest(BaseModel):
    """Command execution request."""

    command: str
    args: list[str] = Field(default_factory=list)
    project_name: Optional[str] = None


class CommandResponse(BaseModel):
    """Command execution response."""

    success: bool
    output: Optional[str] = None
    error: Optional[str] = None


# WebSocket event models
class WebSocketEvent(BaseModel):
    """WebSocket event."""

    type: str  # action, state_change, escalation, chat
    data: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


# Error models
class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: Optional[str] = None
    status_code: int = 400
