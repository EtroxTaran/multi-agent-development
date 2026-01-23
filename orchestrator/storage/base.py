"""Storage interface protocols for adapter pattern.

Defines the contracts that storage backends must implement.
These protocols enable transparent switching between file-based and
SurrealDB-based storage.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable

# ============================================================================
# Audit Storage Protocol
# ============================================================================


@dataclass
class AuditEntryData:
    """Audit entry data structure.

    Common representation used by both file and DB backends.
    """

    id: str
    agent: str
    task_id: str
    session_id: Optional[str] = None
    prompt_hash: str = ""
    prompt_length: int = 0
    command_args: list[str] = field(default_factory=list)
    exit_code: int = 0
    status: str = "pending"
    duration_seconds: float = 0.0
    output_length: int = 0
    error_length: int = 0
    parsed_output_type: Optional[str] = None
    cost_usd: Optional[float] = None
    model: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    timestamp: Optional[datetime] = None


@dataclass
class AuditStatisticsData:
    """Audit statistics summary."""

    total: int = 0
    success_count: int = 0
    failed_count: int = 0
    timeout_count: int = 0
    success_rate: float = 0.0
    total_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    avg_duration_seconds: float = 0.0
    by_agent: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)


class AuditRecordContext(Protocol):
    """Context manager protocol for recording audit entries."""

    def set_result(
        self,
        success: bool,
        exit_code: int = 0,
        output_length: int = 0,
        error_length: int = 0,
        cost_usd: Optional[float] = None,
        model: Optional[str] = None,
        parsed_output_type: Optional[str] = None,
    ) -> None:
        """Set the result of the invocation."""
        ...


@runtime_checkable
class AuditStorageProtocol(Protocol):
    """Protocol for audit storage implementations."""

    def record(
        self,
        agent: str,
        task_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        command_args: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> Any:
        """Start recording an audit entry.

        Returns a context manager that tracks the invocation.
        """
        ...

    def get_task_history(self, task_id: str, limit: int = 100) -> list[AuditEntryData]:
        """Get audit history for a task."""
        ...

    def get_statistics(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AuditStatisticsData:
        """Get audit statistics."""
        ...

    def query(
        self,
        agent: Optional[str] = None,
        task_id: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[AuditEntryData]:
        """Query audit entries with filters."""
        ...


# ============================================================================
# Session Storage Protocol
# ============================================================================


@dataclass
class SessionData:
    """Session data structure."""

    id: str
    task_id: str
    agent: str
    status: str = "active"
    invocation_count: int = 0
    total_cost_usd: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


@runtime_checkable
class SessionStorageProtocol(Protocol):
    """Protocol for session storage implementations."""

    def create_session(self, task_id: str, agent: str = "claude") -> SessionData:
        """Create a new session for a task."""
        ...

    def get_session(self, session_id: str) -> Optional[SessionData]:
        """Get session by ID."""
        ...

    def get_active_session(self, task_id: str) -> Optional[SessionData]:
        """Get the active session for a task."""
        ...

    def get_resume_args(self, task_id: str) -> list[str]:
        """Get CLI arguments to resume a session."""
        ...

    def close_session(self, task_id: str) -> None:
        """Close the session for a task."""
        ...

    def record_invocation(self, task_id: str, cost_usd: float = 0.0) -> None:
        """Record an invocation in the current session."""
        ...


# ============================================================================
# Budget Storage Protocol
# ============================================================================


@dataclass
class BudgetRecordData:
    """Budget record data structure."""

    task_id: Optional[str]
    agent: str
    cost_usd: float
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    model: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class BudgetSummaryData:
    """Budget summary data structure."""

    total_cost_usd: float = 0.0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    record_count: int = 0
    by_agent: dict[str, float] = field(default_factory=dict)
    by_task: dict[str, float] = field(default_factory=dict)
    by_model: dict[str, float] = field(default_factory=dict)


@runtime_checkable
class BudgetStorageProtocol(Protocol):
    """Protocol for budget storage implementations."""

    def record_spend(
        self,
        task_id: str,
        agent: str,
        cost_usd: float,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        model: Optional[str] = None,
    ) -> None:
        """Record a spending event."""
        ...

    def get_task_spent(self, task_id: str) -> float:
        """Get total spent for a task."""
        ...

    def get_task_remaining(self, task_id: str, budget_limit: float) -> float:
        """Get remaining budget for a task."""
        ...

    def can_spend(self, task_id: str, amount: float, budget_limit: float) -> bool:
        """Check if spending amount is within budget."""
        ...

    def get_invocation_budget(self, task_id: str, default: float = 1.0) -> float:
        """Get the per-invocation budget for a task."""
        ...

    def get_summary(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> BudgetSummaryData:
        """Get budget summary."""
        ...


# ============================================================================
# Checkpoint Storage Protocol
# ============================================================================


@dataclass
class CheckpointData:
    """Checkpoint data structure."""

    id: str
    name: str
    notes: str = ""
    phase: int = 0
    task_progress: dict = field(default_factory=dict)
    state_snapshot: dict = field(default_factory=dict)
    files_snapshot: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = None

    def summary(self) -> str:
        """Get brief summary for listing."""
        progress = self.task_progress
        created = self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "unknown"
        return (
            f"[{self.id[:8]}] {self.name} - Phase {self.phase} "
            f"({progress.get('completed', 0)}/{progress.get('total', 0)} tasks) "
            f"- {created}"
        )


@runtime_checkable
class CheckpointStorageProtocol(Protocol):
    """Protocol for checkpoint storage implementations."""

    def create_checkpoint(
        self,
        name: str,
        notes: str = "",
        include_files: bool = False,
    ) -> CheckpointData:
        """Create a new checkpoint."""
        ...

    def list_checkpoints(self) -> list[CheckpointData]:
        """List all checkpoints."""
        ...

    def get_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointData]:
        """Get checkpoint by ID."""
        ...

    def rollback_to_checkpoint(self, checkpoint_id: str, confirm: bool = False) -> bool:
        """Rollback to a checkpoint."""
        ...

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        ...


# ============================================================================
# Workflow State Storage Protocol
# ============================================================================


@dataclass
class WorkflowStateData:
    """Workflow state data structure."""

    project_dir: str = ""
    current_phase: int = 1
    phase_status: dict = field(default_factory=dict)
    iteration_count: int = 0
    plan: Optional[dict] = None
    validation_feedback: Optional[dict] = None
    verification_feedback: Optional[dict] = None
    implementation_result: Optional[dict] = None
    next_decision: Optional[str] = None
    execution_mode: str = "afk"
    discussion_complete: bool = False
    research_complete: bool = False
    research_findings: Optional[dict] = None
    token_usage: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@runtime_checkable
class WorkflowStorageProtocol(Protocol):
    """Protocol for workflow state storage implementations."""

    def get_state(self) -> Optional[WorkflowStateData]:
        """Get current workflow state."""
        ...

    def initialize_state(
        self,
        project_dir: str,
        execution_mode: str = "afk",
    ) -> WorkflowStateData:
        """Initialize workflow state."""
        ...

    def update_state(self, **updates: Any) -> Optional[WorkflowStateData]:
        """Update workflow state fields."""
        ...

    def set_phase(self, phase: int, status: str = "in_progress") -> Optional[WorkflowStateData]:
        """Set current phase and status."""
        ...

    def reset_state(self) -> Optional[WorkflowStateData]:
        """Reset workflow state to initial."""
        ...

    def get_summary(self) -> dict[str, Any]:
        """Get workflow state summary."""
        ...
