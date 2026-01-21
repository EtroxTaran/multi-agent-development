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


class TaskStatus(str, Enum):
    """Status of an individual task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class Task(TypedDict, total=False):
    """A single implementation task.

    Attributes:
        id: Unique task identifier (e.g., "T1", "T2")
        title: Short task title
        user_story: User story in "As a... I want... So that..." format
        acceptance_criteria: List of acceptance criteria to satisfy
        dependencies: Task IDs this task depends on
        status: Current task status
        priority: Task priority (critical, high, medium, low)
        milestone_id: ID of milestone this task belongs to
        estimated_complexity: Task complexity (low, medium, high)
        files_to_create: List of files to create
        files_to_modify: List of files to modify
        test_files: List of test files for this task
        attempts: Number of implementation attempts
        max_attempts: Maximum allowed attempts (default 3)
        linear_issue_id: Optional Linear issue ID if integration enabled
        implementation_notes: Notes from implementation
        error: Error message if task failed
    """

    id: str
    title: str
    user_story: str
    acceptance_criteria: list[str]
    dependencies: list[str]
    status: TaskStatus
    priority: str
    milestone_id: Optional[str]
    estimated_complexity: str
    files_to_create: list[str]
    files_to_modify: list[str]
    test_files: list[str]
    attempts: int
    max_attempts: int
    linear_issue_id: Optional[str]
    implementation_notes: str
    error: Optional[str]


class Milestone(TypedDict, total=False):
    """A group of related tasks.

    Attributes:
        id: Unique milestone identifier (e.g., "M1")
        name: Milestone name
        description: Milestone description
        task_ids: List of task IDs in this milestone
        status: Current milestone status
    """

    id: str
    name: str
    description: str
    task_ids: list[str]
    status: TaskStatus


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
    _archived_path: Optional[str] = None  # Path where raw_output was archived

    def to_dict(self) -> dict:
        """Convert to dict for serialization (excludes raw_output)."""
        return {
            "agent": self.agent,
            "approved": self.approved,
            "score": self.score,
            "assessment": self.assessment,
            "concerns": self.concerns,
            "blocking_issues": self.blocking_issues,
            "summary": self.summary,
        }

    def archive_raw_output(self, workflow_dir: str) -> Optional[str]:
        """Archive raw_output to disk and clear from memory.

        Args:
            workflow_dir: Path to .workflow directory

        Returns:
            Path to archived file or None if no raw_output
        """
        import json
        from pathlib import Path

        if self.raw_output is None:
            return None

        feedback_dir = Path(workflow_dir) / "feedback"
        feedback_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.agent}_{timestamp}.json"
        archive_path = feedback_dir / filename

        archive_path.write_text(json.dumps(self.raw_output, indent=2))

        # Clear raw_output from memory
        self._archived_path = str(archive_path)
        self.raw_output = None

        return str(archive_path)

    def get_archived_output(self) -> Optional[dict]:
        """Load archived raw_output from disk if available."""
        import json
        from pathlib import Path

        if self._archived_path is None:
            return self.raw_output

        archive_path = Path(self._archived_path)
        if archive_path.exists():
            return json.loads(archive_path.read_text())
        return None


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


# Maximum errors to keep in state
MAX_ERRORS = 100


def _append_errors(
    existing: Optional[list[dict]],
    new: list[dict],
) -> list[dict]:
    """Reducer for appending errors with size limit.

    Keeps most recent MAX_ERRORS to prevent unbounded state growth.

    Args:
        existing: Existing error list
        new: New errors to append

    Returns:
        Combined error list (limited to MAX_ERRORS)
    """
    if existing is None:
        result = new
    else:
        result = existing + new

    # Keep only most recent errors if over limit
    if len(result) > MAX_ERRORS:
        result = result[-MAX_ERRORS:]

    return result


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


# Maximum unique IDs to track in state
MAX_UNIQUE_IDS = 1000


def _append_unique(
    existing: Optional[list[str]],
    new: list[str],
) -> list[str]:
    """Reducer for appending unique items with size limit.

    Keeps most recent MAX_UNIQUE_IDS to prevent unbounded state growth.

    Args:
        existing: Existing list
        new: New items to append

    Returns:
        Combined list with unique items (limited to MAX_UNIQUE_IDS)
    """
    if existing is None:
        result = list(new)
    else:
        result = list(existing)
        for item in new:
            if item not in result:
                result.append(item)

    # Keep only most recent IDs if over limit
    if len(result) > MAX_UNIQUE_IDS:
        result = result[-MAX_UNIQUE_IDS:]

    return result


def _merge_tasks(
    existing: Optional[list[Task]],
    new: list[Task],
) -> list[Task]:
    """Reducer for merging task lists.

    Updates existing tasks by ID or appends new ones.

    Args:
        existing: Existing task list
        new: New or updated tasks

    Returns:
        Merged task list
    """
    if existing is None:
        return list(new)

    # Build a map of existing tasks by ID
    task_map = {t["id"]: t for t in existing if "id" in t}

    # Update or add new tasks
    for task in new:
        if "id" in task:
            task_map[task["id"]] = task

    return list(task_map.values())


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
        tasks: List of implementation tasks (incremental execution)
        milestones: List of task milestones
        current_task_id: ID of currently executing task
        completed_task_ids: IDs of completed tasks (append-only unique)
        failed_task_ids: IDs of failed tasks (append-only unique)
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

    # Task-based execution (incremental implementation)
    tasks: Annotated[list[Task], _merge_tasks]
    milestones: list[Milestone]
    current_task_id: Optional[str]
    completed_task_ids: Annotated[list[str], _append_unique]
    failed_task_ids: Annotated[list[str], _append_unique]


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
        # Task-based execution fields
        tasks=[],
        milestones=[],
        current_task_id=None,
        completed_task_ids=[],
        failed_task_ids=[],
    )


def create_task(
    task_id: str,
    title: str,
    user_story: str = "",
    acceptance_criteria: Optional[list[str]] = None,
    dependencies: Optional[list[str]] = None,
    priority: str = "medium",
    milestone_id: Optional[str] = None,
    estimated_complexity: str = "medium",
    files_to_create: Optional[list[str]] = None,
    files_to_modify: Optional[list[str]] = None,
    test_files: Optional[list[str]] = None,
    max_attempts: int = 3,
) -> Task:
    """Create a new task with defaults.

    Args:
        task_id: Unique task ID (e.g., "T1")
        title: Short task title
        user_story: User story description
        acceptance_criteria: List of acceptance criteria
        dependencies: Task IDs this depends on
        priority: Task priority
        milestone_id: Milestone this belongs to
        estimated_complexity: Task complexity
        files_to_create: Files to create
        files_to_modify: Files to modify
        test_files: Test files for this task
        max_attempts: Maximum implementation attempts

    Returns:
        New Task instance
    """
    return Task(
        id=task_id,
        title=title,
        user_story=user_story,
        acceptance_criteria=acceptance_criteria or [],
        dependencies=dependencies or [],
        status=TaskStatus.PENDING,
        priority=priority,
        milestone_id=milestone_id,
        estimated_complexity=estimated_complexity,
        files_to_create=files_to_create or [],
        files_to_modify=files_to_modify or [],
        test_files=test_files or [],
        attempts=0,
        max_attempts=max_attempts,
        linear_issue_id=None,
        implementation_notes="",
        error=None,
    )


def get_task_by_id(state: WorkflowState, task_id: str) -> Optional[Task]:
    """Get a task by its ID.

    Args:
        state: Current workflow state
        task_id: Task ID to find

    Returns:
        Task if found, None otherwise
    """
    for task in state.get("tasks", []):
        if task.get("id") == task_id:
            return task
    return None


def get_pending_tasks(state: WorkflowState) -> list[Task]:
    """Get all pending tasks.

    Args:
        state: Current workflow state

    Returns:
        List of pending tasks
    """
    return [
        task for task in state.get("tasks", [])
        if task.get("status") == TaskStatus.PENDING
    ]


def get_available_tasks(state: WorkflowState) -> list[Task]:
    """Get tasks that are ready to execute (pending with satisfied dependencies).

    Args:
        state: Current workflow state

    Returns:
        List of tasks ready to execute
    """
    completed = set(state.get("completed_task_ids", []))
    failed = set(state.get("failed_task_ids", []))
    available = []

    for task in state.get("tasks", []):
        task_id = task.get("id")

        # Skip already completed or failed tasks
        if task_id in completed or task_id in failed:
            continue

        if task.get("status") != TaskStatus.PENDING:
            continue

        # Check if all dependencies are satisfied
        deps = task.get("dependencies", [])
        if all(dep in completed for dep in deps):
            available.append(task)

    return available


def all_tasks_completed(state: WorkflowState) -> bool:
    """Check if all tasks are completed.

    Args:
        state: Current workflow state

    Returns:
        True if all tasks are completed
    """
    tasks = state.get("tasks", [])
    if not tasks:
        return True

    completed = set(state.get("completed_task_ids", []))
    return all(task.get("id") in completed for task in tasks)


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

    # Task summary
    tasks = state.get("tasks", [])
    completed_ids = set(state.get("completed_task_ids", []))
    failed_ids = set(state.get("failed_task_ids", []))
    task_summary = {
        "total": len(tasks),
        "completed": len(completed_ids),
        "failed": len(failed_ids),
        "pending": len([t for t in tasks if t.get("id") not in completed_ids and t.get("id") not in failed_ids]),
        "current_task_id": state.get("current_task_id"),
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
        "tasks": task_summary,
    }
