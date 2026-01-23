"""State adapter for UI display components."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TaskUIInfo:
    """UI-friendly task information."""

    id: str
    title: str
    status: str  # pending, in_progress, completed, failed
    iteration: int = 0
    max_iterations: int = 10
    tests_passed: int = 0
    tests_total: int = 0
    error: Optional[str] = None


@dataclass
class EventLogEntry:
    """Single event log entry."""

    timestamp: datetime
    message: str
    level: str  # info, warning, error, success


@dataclass
class UIStateSnapshot:
    """Immutable snapshot of UI state."""

    project_name: str
    elapsed_seconds: float
    current_phase: int
    total_phases: int
    phase_progress: float
    phase_name: str
    tasks: list[TaskUIInfo]
    tasks_completed: int
    tasks_total: int
    current_task_id: Optional[str]
    tokens: int
    cost: float
    files_created: int
    files_modified: int
    recent_events: list[EventLogEntry]
    status: str  # running, paused, completed, failed
