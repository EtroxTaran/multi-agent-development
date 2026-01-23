"""Data models for the orchestration workflow.

This module contains data types and enums used throughout the orchestrator.
These are pure data structures without persistence logic - persistence is
handled by the storage adapters and DB repositories.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class PhaseStatus(str, Enum):
    """Status of a workflow phase."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class PhaseState:
    """State of a single phase."""

    name: str
    status: PhaseStatus = PhaseStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    blockers: list[str] = field(default_factory=list)
    approvals: dict[str, bool] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "PhaseState":
        """Create from dictionary."""
        data = dict(data)  # Copy to avoid mutating input
        data["status"] = PhaseStatus(data.get("status", "pending"))
        return cls(**data)


@dataclass
class WorkflowState:
    """Complete workflow state."""

    project_name: str
    current_phase: int = 1
    iteration_count: int = 0
    phases: dict[str, PhaseState] = field(default_factory=dict)
    context: Optional[dict] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    git_commits: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    PHASE_NAMES = ["planning", "validation", "implementation", "verification", "completion"]

    def __post_init__(self):
        """Initialize phases if not provided."""
        if not self.phases:
            self.phases = {name: PhaseState(name=name) for name in self.PHASE_NAMES}

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "project_name": self.project_name,
            "current_phase": self.current_phase,
            "iteration_count": self.iteration_count,
            "phases": {k: v.to_dict() for k, v in self.phases.items()},
            "context": self.context,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "git_commits": self.git_commits,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowState":
        """Create from dictionary."""
        phases = {k: PhaseState.from_dict(v) for k, v in data.get("phases", {}).items()}
        return cls(
            project_name=data["project_name"],
            current_phase=data.get("current_phase", 1),
            iteration_count=data.get("iteration_count", 0),
            phases=phases,
            context=data.get("context"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            git_commits=data.get("git_commits", []),
            metadata=data.get("metadata", {}),
        )

    def get_phase(self, phase_num: int) -> PhaseState:
        """Get phase state by number (1-indexed)."""
        if not 1 <= phase_num <= 5:
            raise ValueError(f"Invalid phase number: {phase_num}")
        phase_name = self.PHASE_NAMES[phase_num - 1]
        return self.phases[phase_name]

    def get_summary(self) -> dict:
        """Get a summary of the workflow state."""
        return {
            "project": self.project_name,
            "current_phase": self.current_phase,
            "iteration_count": self.iteration_count,
            "phase_statuses": {name: phase.status.value for name, phase in self.phases.items()},
            "total_commits": len(self.git_commits),
            "created": self.created_at,
            "updated": self.updated_at,
            "has_context": self.context is not None,
        }
