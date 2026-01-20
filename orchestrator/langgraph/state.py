"""LangGraph workflow state schema.

Defines the TypedDict state used by the workflow graph, including
reducers for merging parallel execution results.
"""

import operator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Optional, TypedDict


class PhaseStatus(str, Enum):
    """Status of a workflow phase."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"  # Waiting for human clarification


class WorkflowDecision(str, Enum):
    """Decisions that route the workflow."""

    CONTINUE = "continue"
    RETRY = "retry"
    ESCALATE = "escalate"
    ABORT = "abort"


@dataclass
class PhaseState:
    """State for a single phase."""

    status: PhaseStatus = PhaseStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    blockers: list[dict] = field(default_factory=list)
    output: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "blockers": self.blockers,
        }


@dataclass
class AgentFeedback:
    """Feedback from a review agent."""

    agent: str
    approved: bool
    score: float
    assessment: str
    concerns: list[dict] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    summary: str = ""
    raw_output: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "approved": self.approved,
            "score": self.score,
            "assessment": self.assessment,
            "concerns": self.concerns,
            "blocking_issues": self.blocking_issues,
            "summary": self.summary,
        }


def _merge_feedback(
    existing: Optional[dict[str, AgentFeedback]],
    new: dict[str, AgentFeedback],
) -> dict[str, AgentFeedback]:
    """Reducer for merging feedback from parallel agents.

    Args:
        existing: Existing feedback dict
        new: New feedback to merge

    Returns:
        Merged feedback dict
    """
    if existing is None:
        return new
    return {**existing, **new}


def _append_errors(
    existing: Optional[list[dict]],
    new: list[dict],
) -> list[dict]:
    """Reducer for appending errors.

    Args:
        existing: Existing error list
        new: New errors to append

    Returns:
        Combined error list
    """
    if existing is None:
        return new
    return existing + new


def _latest_timestamp(
    existing: Optional[str],
    new: str,
) -> str:
    """Reducer for keeping the latest timestamp.

    Args:
        existing: Existing timestamp
        new: New timestamp

    Returns:
        The later timestamp
    """
    if existing is None:
        return new
    # Compare ISO format timestamps (lexicographically works for ISO format)
    return max(existing, new)


class WorkflowState(TypedDict, total=False):
    """State schema for the LangGraph workflow.

    This TypedDict defines the complete state that flows through the
    workflow graph. Annotated fields use reducers for handling
    parallel execution results.

    Attributes:
        project_dir: Absolute path to the project directory
        project_name: Name of the project
        current_phase: Current phase number (1-5)
        phase_status: Status of each phase
        iteration_count: Total iterations through the workflow
        plan: Implementation plan from Phase 1
        validation_feedback: Feedback from Phase 2 (parallel merge)
        verification_feedback: Feedback from Phase 4 (parallel merge)
        implementation_result: Result from Phase 3
        next_decision: Routing decision for conditional edges
        errors: List of errors (append-only)
        checkpoints: List of checkpoint IDs
        git_commits: List of commit hashes
        created_at: Workflow creation timestamp
        updated_at: Last update timestamp
    """

    # Project identification
    project_dir: str
    project_name: str

    # Phase tracking
    current_phase: int
    phase_status: dict[str, PhaseState]
    iteration_count: int

    # Phase outputs
    plan: Optional[dict]
    validation_feedback: Annotated[Optional[dict[str, AgentFeedback]], _merge_feedback]
    verification_feedback: Annotated[Optional[dict[str, AgentFeedback]], _merge_feedback]
    implementation_result: Optional[dict]

    # Routing
    next_decision: Optional[WorkflowDecision]

    # Errors (append-only)
    errors: Annotated[list[dict], _append_errors]

    # Tracking
    checkpoints: list[str]
    git_commits: list[dict]

    # Timestamps
    created_at: str
    updated_at: Annotated[str, _latest_timestamp]


def create_initial_state(
    project_dir: str,
    project_name: str,
) -> WorkflowState:
    """Create initial workflow state.

    Args:
        project_dir: Project directory path
        project_name: Project name

    Returns:
        Initial WorkflowState
    """
    now = datetime.now().isoformat()

    return WorkflowState(
        project_dir=project_dir,
        project_name=project_name,
        current_phase=1,
        phase_status={
            "1": PhaseState(),
            "2": PhaseState(),
            "3": PhaseState(),
            "4": PhaseState(),
            "5": PhaseState(),
        },
        iteration_count=0,
        plan=None,
        validation_feedback=None,
        verification_feedback=None,
        implementation_result=None,
        next_decision=None,
        errors=[],
        checkpoints=[],
        git_commits=[],
        created_at=now,
        updated_at=now,
    )


def get_phase_state(state: WorkflowState, phase: int) -> PhaseState:
    """Get the state for a specific phase.

    Args:
        state: Current workflow state
        phase: Phase number (1-5)

    Returns:
        PhaseState for the phase
    """
    phase_key = str(phase)
    if phase_key in state.get("phase_status", {}):
        return state["phase_status"][phase_key]
    return PhaseState()


def update_phase_state(
    state: WorkflowState,
    phase: int,
    **updates,
) -> WorkflowState:
    """Update state for a specific phase.

    Args:
        state: Current workflow state
        phase: Phase number (1-5)
        **updates: Fields to update

    Returns:
        Updated WorkflowState
    """
    phase_key = str(phase)
    phase_status = state.get("phase_status", {}).copy()

    if phase_key in phase_status:
        phase_state = phase_status[phase_key]
        for key, value in updates.items():
            if hasattr(phase_state, key):
                setattr(phase_state, key, value)
        phase_status[phase_key] = phase_state

    return {
        **state,
        "phase_status": phase_status,
        "updated_at": datetime.now().isoformat(),
    }


def can_proceed_to_phase(state: WorkflowState, phase: int) -> tuple[bool, str]:
    """Check if workflow can proceed to a phase.

    Args:
        state: Current workflow state
        phase: Target phase number

    Returns:
        Tuple of (can_proceed, reason)
    """
    if phase < 1 or phase > 5:
        return False, f"Invalid phase number: {phase}"

    # Phase 1 can always start
    if phase == 1:
        return True, "Phase 1 can start"

    # Check if previous phase is complete
    prev_phase = get_phase_state(state, phase - 1)
    if prev_phase.status != PhaseStatus.COMPLETED:
        return False, f"Phase {phase - 1} not completed"

    # Check for unresolved blockers
    current = get_phase_state(state, phase)
    unresolved = [b for b in current.blockers if not b.get("resolved")]
    if unresolved:
        return False, f"Phase {phase} has {len(unresolved)} unresolved blockers"

    return True, "Ready to proceed"


def get_workflow_summary(state: WorkflowState) -> dict:
    """Get a summary of the workflow state.

    Args:
        state: Current workflow state

    Returns:
        Summary dictionary
    """
    phase_summaries = {}
    for phase_num in range(1, 6):
        phase_state = get_phase_state(state, phase_num)
        phase_summaries[f"phase_{phase_num}"] = {
            "status": phase_state.status.value,
            "attempts": phase_state.attempts,
            "has_blockers": len([b for b in phase_state.blockers if not b.get("resolved")]) > 0,
        }

    return {
        "project": state.get("project_name"),
        "current_phase": state.get("current_phase"),
        "iteration_count": state.get("iteration_count", 0),
        "phases": phase_summaries,
        "has_plan": state.get("plan") is not None,
        "has_validation": state.get("validation_feedback") is not None,
        "has_implementation": state.get("implementation_result") is not None,
        "has_verification": state.get("verification_feedback") is not None,
        "total_errors": len(state.get("errors", [])),
        "total_commits": len(state.get("git_commits", [])),
    }
