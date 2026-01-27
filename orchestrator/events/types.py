"""Event type definitions for workflow events.

Provides strongly-typed event structures for the event bridge between
the orchestrator and dashboard.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    """Types of workflow events.

    These events flow from orchestrator -> SurrealDB -> dashboard.
    """

    # Node lifecycle
    NODE_START = "node_start"
    NODE_END = "node_end"

    # Phase lifecycle
    PHASE_START = "phase_start"
    PHASE_END = "phase_end"
    PHASE_CHANGE = "phase_change"

    # Task lifecycle
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"
    TASKS_CREATED = "tasks_created"

    # Agent lifecycle
    AGENT_START = "agent_start"
    AGENT_COMPLETE = "agent_complete"

    # Ralph loop
    RALPH_ITERATION = "ralph_iteration"

    # Errors and escalations
    ERROR_OCCURRED = "error_occurred"
    ESCALATION_REQUIRED = "escalation_required"

    # Workflow lifecycle
    WORKFLOW_START = "workflow_start"
    WORKFLOW_COMPLETE = "workflow_complete"
    WORKFLOW_PAUSED = "workflow_paused"
    WORKFLOW_RESUMED = "workflow_resumed"

    # Metrics
    METRICS_UPDATE = "metrics_update"

    # Path decisions
    PATH_DECISION = "path_decision"


class EventPriority(str, Enum):
    """Event priority levels for filtering."""

    HIGH = "high"  # Errors, escalations, workflow state changes
    MEDIUM = "medium"  # Task/phase events
    LOW = "low"  # Node events, metrics


@dataclass
class WorkflowEvent:
    """A workflow event to be stored in SurrealDB and forwarded to dashboard.

    Attributes:
        event_type: Type of event
        project_name: Project this event belongs to
        data: Event-specific data payload
        timestamp: When the event occurred
        priority: Event priority for filtering
        node_name: Name of the node that generated this event
        task_id: Associated task ID if applicable
        phase: Current workflow phase
        correlation_id: ID for correlating related events
    """

    event_type: EventType
    project_name: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    priority: EventPriority = EventPriority.MEDIUM
    node_name: Optional[str] = None
    task_id: Optional[str] = None
    phase: Optional[int] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        return {
            "event_type": self.event_type.value,
            "project_name": self.project_name,
            "data": self.data,
            "timestamp": self.timestamp,
            "priority": self.priority.value,
            "node_name": self.node_name,
            "task_id": self.task_id,
            "phase": self.phase,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowEvent":
        """Create from dictionary."""
        return cls(
            event_type=EventType(data["event_type"]),
            project_name=data["project_name"],
            data=data.get("data", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            priority=EventPriority(data.get("priority", "medium")),
            node_name=data.get("node_name"),
            task_id=data.get("task_id"),
            phase=data.get("phase"),
            correlation_id=data.get("correlation_id"),
        )


# Event factory functions for common events


def node_start_event(
    project_name: str,
    node_name: str,
    phase: Optional[int] = None,
    state_summary: Optional[dict] = None,
) -> WorkflowEvent:
    """Create a node start event."""
    return WorkflowEvent(
        event_type=EventType.NODE_START,
        project_name=project_name,
        node_name=node_name,
        phase=phase,
        priority=EventPriority.LOW,
        data={"state_summary": state_summary or {}},
    )


def node_end_event(
    project_name: str,
    node_name: str,
    phase: Optional[int] = None,
    success: bool = True,
    duration_seconds: Optional[float] = None,
) -> WorkflowEvent:
    """Create a node end event."""
    return WorkflowEvent(
        event_type=EventType.NODE_END,
        project_name=project_name,
        node_name=node_name,
        phase=phase,
        priority=EventPriority.LOW,
        data={
            "success": success,
            "duration_seconds": duration_seconds,
        },
    )


def phase_change_event(
    project_name: str,
    from_phase: int,
    to_phase: int,
    status: str,
) -> WorkflowEvent:
    """Create a phase change event."""
    return WorkflowEvent(
        event_type=EventType.PHASE_CHANGE,
        project_name=project_name,
        phase=to_phase,
        priority=EventPriority.HIGH,
        data={
            "from_phase": from_phase,
            "to_phase": to_phase,
            "status": status,
        },
    )


def task_start_event(
    project_name: str,
    task_id: str,
    task_title: str,
    phase: Optional[int] = None,
) -> WorkflowEvent:
    """Create a task start event."""
    return WorkflowEvent(
        event_type=EventType.TASK_START,
        project_name=project_name,
        task_id=task_id,
        phase=phase,
        priority=EventPriority.MEDIUM,
        data={"title": task_title},
    )


def task_complete_event(
    project_name: str,
    task_id: str,
    success: bool,
    phase: Optional[int] = None,
    error: Optional[str] = None,
) -> WorkflowEvent:
    """Create a task complete event."""
    event_type = EventType.TASK_COMPLETE if success else EventType.TASK_FAILED
    return WorkflowEvent(
        event_type=event_type,
        project_name=project_name,
        task_id=task_id,
        phase=phase,
        priority=EventPriority.MEDIUM,
        data={
            "success": success,
            "error": error,
        },
    )


def agent_start_event(
    project_name: str,
    agent_name: str,
    node_name: str,
    task_id: Optional[str] = None,
) -> WorkflowEvent:
    """Create an agent start event."""
    return WorkflowEvent(
        event_type=EventType.AGENT_START,
        project_name=project_name,
        node_name=node_name,
        task_id=task_id,
        priority=EventPriority.LOW,
        data={"agent": agent_name},
    )


def agent_complete_event(
    project_name: str,
    agent_name: str,
    node_name: str,
    success: bool,
    duration_seconds: Optional[float] = None,
    task_id: Optional[str] = None,
) -> WorkflowEvent:
    """Create an agent complete event."""
    return WorkflowEvent(
        event_type=EventType.AGENT_COMPLETE,
        project_name=project_name,
        node_name=node_name,
        task_id=task_id,
        priority=EventPriority.LOW,
        data={
            "agent": agent_name,
            "success": success,
            "duration_seconds": duration_seconds,
        },
    )


def error_event(
    project_name: str,
    error_message: str,
    error_type: str,
    node_name: Optional[str] = None,
    task_id: Optional[str] = None,
    recoverable: bool = True,
) -> WorkflowEvent:
    """Create an error event."""
    return WorkflowEvent(
        event_type=EventType.ERROR_OCCURRED,
        project_name=project_name,
        node_name=node_name,
        task_id=task_id,
        priority=EventPriority.HIGH,
        data={
            "error_message": error_message,
            "error_type": error_type,
            "recoverable": recoverable,
        },
    )


def escalation_event(
    project_name: str,
    question: str,
    options: Optional[list[str]] = None,
    context: Optional[dict] = None,
    node_name: Optional[str] = None,
) -> WorkflowEvent:
    """Create an escalation event (requires human input)."""
    return WorkflowEvent(
        event_type=EventType.ESCALATION_REQUIRED,
        project_name=project_name,
        node_name=node_name,
        priority=EventPriority.HIGH,
        data={
            "question": question,
            "options": options or [],
            "context": context or {},
        },
    )


def ralph_iteration_event(
    project_name: str,
    task_id: str,
    iteration: int,
    max_iterations: int,
    tests_passed: int = 0,
    tests_total: int = 0,
) -> WorkflowEvent:
    """Create a Ralph loop iteration event."""
    return WorkflowEvent(
        event_type=EventType.RALPH_ITERATION,
        project_name=project_name,
        task_id=task_id,
        priority=EventPriority.LOW,
        data={
            "iteration": iteration,
            "max_iterations": max_iterations,
            "tests_passed": tests_passed,
            "tests_total": tests_total,
        },
    )


def metrics_update_event(
    project_name: str,
    tokens: int = 0,
    cost: float = 0.0,
    files_created: Optional[int] = None,
    files_modified: Optional[int] = None,
) -> WorkflowEvent:
    """Create a metrics update event."""
    return WorkflowEvent(
        event_type=EventType.METRICS_UPDATE,
        project_name=project_name,
        priority=EventPriority.LOW,
        data={
            "tokens": tokens,
            "cost": cost,
            "files_created": files_created,
            "files_modified": files_modified,
        },
    )


def workflow_start_event(
    project_name: str,
    mode: str = "langgraph",
    start_phase: int = 1,
    autonomous: bool = False,
) -> WorkflowEvent:
    """Create a workflow start event."""
    return WorkflowEvent(
        event_type=EventType.WORKFLOW_START,
        project_name=project_name,
        phase=start_phase,
        priority=EventPriority.HIGH,
        data={
            "mode": mode,
            "start_phase": start_phase,
            "autonomous": autonomous,
        },
    )


def workflow_complete_event(
    project_name: str,
    success: bool,
    final_phase: int,
    summary: Optional[dict] = None,
) -> WorkflowEvent:
    """Create a workflow complete event."""
    return WorkflowEvent(
        event_type=EventType.WORKFLOW_COMPLETE,
        project_name=project_name,
        phase=final_phase,
        priority=EventPriority.HIGH,
        data={
            "success": success,
            "summary": summary or {},
        },
    )


def workflow_paused_event(
    project_name: str,
    phase: int,
    node_name: Optional[str] = None,
    reason: Optional[str] = None,
) -> WorkflowEvent:
    """Create a workflow paused event."""
    return WorkflowEvent(
        event_type=EventType.WORKFLOW_PAUSED,
        project_name=project_name,
        phase=phase,
        node_name=node_name,
        priority=EventPriority.HIGH,
        data={"reason": reason},
    )


def path_decision_event(
    project_name: str,
    router: str,
    decision: str,
    phase: Optional[int] = None,
) -> WorkflowEvent:
    """Create a path decision event."""
    return WorkflowEvent(
        event_type=EventType.PATH_DECISION,
        project_name=project_name,
        phase=phase,
        priority=EventPriority.LOW,
        data={
            "router": router,
            "decision": decision,
        },
    )


def phase_start_event(
    project_name: str,
    phase: int,
    node_name: Optional[str] = None,
) -> WorkflowEvent:
    """Create a phase start event.

    Used to notify dashboard that a workflow phase has started.
    High priority for immediate delivery.

    Args:
        project_name: Project name
        phase: Phase number starting
        node_name: Optional node name that triggered the phase

    Returns:
        WorkflowEvent for phase start
    """
    return WorkflowEvent(
        event_type=EventType.PHASE_START,
        project_name=project_name,
        phase=phase,
        node_name=node_name,
        priority=EventPriority.HIGH,
        data={
            "phase": phase,
            "status": "in_progress",
        },
    )


def phase_end_event(
    project_name: str,
    phase: int,
    success: bool,
    node_name: Optional[str] = None,
    error: Optional[str] = None,
) -> WorkflowEvent:
    """Create a phase end event.

    Used to notify dashboard that a workflow phase has completed.
    High priority for immediate delivery.

    Args:
        project_name: Project name
        phase: Phase number ending
        success: Whether the phase completed successfully
        node_name: Optional node name that completed the phase
        error: Optional error message if phase failed

    Returns:
        WorkflowEvent for phase end
    """
    return WorkflowEvent(
        event_type=EventType.PHASE_END,
        project_name=project_name,
        phase=phase,
        node_name=node_name,
        priority=EventPriority.HIGH,
        data={
            "phase": phase,
            "success": success,
            "status": "completed" if success else "failed",
            "error": error,
        },
    )


def tasks_created_event(
    project_name: str,
    task_count: int,
    milestone_count: int,
    phase: int = 1,
) -> WorkflowEvent:
    """Create a tasks_created event.

    Emitted when task breakdown creates new tasks.
    High priority to trigger immediate frontend refresh.

    Args:
        project_name: Project name
        task_count: Number of tasks created
        milestone_count: Number of milestones created
        phase: Current phase (usually 1 for planning)

    Returns:
        WorkflowEvent for tasks created
    """
    return WorkflowEvent(
        event_type=EventType.TASKS_CREATED,
        project_name=project_name,
        phase=phase,
        priority=EventPriority.HIGH,
        data={
            "task_count": task_count,
            "milestone_count": milestone_count,
        },
    )
