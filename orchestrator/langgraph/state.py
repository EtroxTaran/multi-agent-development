"""LangGraph workflow state schema.

Defines the TypedDict state used by the workflow graph, including
reducers for merging parallel execution results.
"""

import operator
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Optional, TypedDict


# ============== ERROR CONTEXT ==============
# Rich error context for the Bugfixer agent


class ErrorContext(TypedDict, total=False):
    """Rich error context for comprehensive debugging.

    Provides full diagnostic information for the Bugfixer agent to
    analyze and potentially auto-fix errors.

    Attributes:
        error_id: Unique error identifier for tracking
        source_node: Which node failed
        error_type: Exception class name
        error_message: Human-readable error message
        stack_trace: Full Python traceback
        stderr: CLI stderr if error came from subprocess
        state_snapshot: Relevant state at time of error (sanitized)
        last_agent_execution: Agent execution context if error was from agent call
        recoverable: Hint for fixer - is this likely auto-fixable?
        suggested_actions: Potential fix strategies to try
        timestamp: When the error occurred
        retry_count: How many times this error has been retried
        related_errors: IDs of related/similar errors
    """

    error_id: str
    source_node: str
    error_type: str
    error_message: str
    stack_trace: str
    stderr: Optional[str]
    state_snapshot: dict[str, Any]
    last_agent_execution: Optional[dict]
    recoverable: bool
    suggested_actions: list[str]
    timestamp: str
    retry_count: int
    related_errors: list[str]


def create_error_context(
    source_node: str,
    exception: Exception,
    state: Optional[dict] = None,
    last_execution: Optional[dict] = None,
    stderr: Optional[str] = None,
    recoverable: bool = True,
    suggested_actions: Optional[list[str]] = None,
) -> ErrorContext:
    """Create a rich ErrorContext from an exception.

    Args:
        source_node: Name of the node where error occurred
        exception: The caught exception
        state: Current workflow state (will be sanitized)
        last_execution: Agent execution context if applicable
        stderr: CLI stderr output if applicable
        recoverable: Whether this error might be auto-fixable
        suggested_actions: List of potential fix strategies

    Returns:
        ErrorContext with full diagnostic info
    """
    # Sanitize state - remove large/sensitive fields
    sanitized_state = {}
    if state:
        # Keep only relevant fields for debugging
        safe_fields = [
            "current_phase", "current_task_id", "project_name",
            "next_decision", "fixer_attempts", "iteration_count",
        ]
        sanitized_state = {
            k: state.get(k)
            for k in safe_fields
            if k in state and state.get(k) is not None
        }
        # Include error summary if exists
        if state.get("errors"):
            sanitized_state["error_count"] = len(state["errors"])

    # Classify error type for recovery hints
    error_type = type(exception).__name__
    auto_recoverable_types = {
        "TimeoutError": True,
        "ConnectionError": True,
        "FileNotFoundError": True,
        "ImportError": True,
        "SyntaxError": True,
        "JSONDecodeError": True,
        "AssertionError": True,  # Test failures
    }
    is_recoverable = recoverable and auto_recoverable_types.get(error_type, False)

    # Generate suggested actions based on error type
    if suggested_actions is None:
        suggested_actions = _suggest_recovery_actions(error_type, str(exception))

    return ErrorContext(
        error_id=str(uuid.uuid4())[:8],
        source_node=source_node,
        error_type=error_type,
        error_message=str(exception),
        stack_trace=traceback.format_exc(),
        stderr=stderr,
        state_snapshot=sanitized_state,
        last_agent_execution=last_execution,
        recoverable=is_recoverable,
        suggested_actions=suggested_actions,
        timestamp=datetime.now().isoformat(),
        retry_count=0,
        related_errors=[],
    )


def _suggest_recovery_actions(error_type: str, message: str) -> list[str]:
    """Generate suggested recovery actions based on error type.

    Args:
        error_type: Exception class name
        message: Error message

    Returns:
        List of suggested fix strategies
    """
    suggestions = {
        "TimeoutError": ["retry_with_longer_timeout", "reduce_task_scope", "check_network"],
        "ConnectionError": ["retry_after_delay", "check_network", "verify_endpoint"],
        "FileNotFoundError": ["check_file_path", "create_missing_file", "verify_cwd"],
        "ImportError": ["add_missing_import", "install_dependency", "check_module_path"],
        "SyntaxError": ["regenerate_code", "fix_syntax", "validate_output"],
        "JSONDecodeError": ["retry_with_structured_output", "validate_json", "fix_escaping"],
        "AssertionError": ["iterate_with_ralph_loop", "fix_implementation", "update_test"],
        "PermissionError": ["check_file_permissions", "use_sudo", "change_directory"],
        "KeyError": ["check_state_fields", "add_default_value", "verify_input"],
        "TypeError": ["check_argument_types", "add_type_conversion", "validate_input"],
    }

    base_actions = suggestions.get(error_type, ["analyze_error", "retry_operation"])

    # Add context-specific suggestions
    message_lower = message.lower()
    if "rate limit" in message_lower:
        base_actions.insert(0, "wait_and_retry")
    if "authentication" in message_lower or "auth" in message_lower:
        base_actions.insert(0, "check_credentials")
    if "memory" in message_lower:
        base_actions.insert(0, "reduce_batch_size")

    return base_actions


# ============== AGENT EXECUTION ==============
# Tracks all agent calls for evaluation and optimization


class AgentExecution(TypedDict, total=False):
    """Tracks a single agent execution for evaluation.

    Captures all information needed to evaluate agent quality
    and potentially optimize prompts.

    Attributes:
        execution_id: Unique identifier for this execution
        agent: Which agent ran (claude, cursor, gemini)
        node: Which workflow node triggered the execution
        template_name: Which prompt template was used
        prompt: The actual prompt sent to the agent
        output: The agent's response (may be truncated for storage)
        success: Whether the execution succeeded
        exit_code: CLI exit code if applicable
        duration_seconds: How long the execution took
        cost_usd: Estimated cost of this execution
        model: Which model was used (e.g., sonnet, opus, gemini-2.0-flash)
        task_id: Associated task ID if in task loop
        input_tokens: Number of input tokens (if available)
        output_tokens: Number of output tokens (if available)
        timestamp: When execution started
        retries: Number of retries before success/failure
        error_context: ErrorContext if execution failed
    """

    execution_id: str
    agent: str
    node: str
    template_name: str
    prompt: str
    output: str
    success: bool
    exit_code: int
    duration_seconds: float
    cost_usd: float
    model: str
    task_id: Optional[str]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    timestamp: str
    retries: int
    error_context: Optional[ErrorContext]


def create_agent_execution(
    agent: str,
    node: str,
    template_name: str,
    prompt: str,
    output: str = "",
    success: bool = False,
    exit_code: int = 0,
    duration_seconds: float = 0.0,
    cost_usd: float = 0.0,
    model: str = "",
    task_id: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    retries: int = 0,
    error_context: Optional[ErrorContext] = None,
) -> AgentExecution:
    """Create an AgentExecution record.

    Args:
        agent: Agent name (claude, cursor, gemini)
        node: Workflow node name
        template_name: Prompt template name
        prompt: Prompt sent to agent (will be truncated if too long)
        output: Agent response (will be truncated if too long)
        success: Whether execution succeeded
        exit_code: CLI exit code
        duration_seconds: Execution duration
        cost_usd: Estimated cost
        model: Model used
        task_id: Associated task ID
        input_tokens: Input token count
        output_tokens: Output token count
        retries: Number of retries
        error_context: Error context if failed

    Returns:
        AgentExecution record
    """
    # Truncate large strings to prevent state bloat
    MAX_PROMPT_LENGTH = 10000
    MAX_OUTPUT_LENGTH = 20000

    truncated_prompt = prompt[:MAX_PROMPT_LENGTH] if len(prompt) > MAX_PROMPT_LENGTH else prompt
    truncated_output = output[:MAX_OUTPUT_LENGTH] if len(output) > MAX_OUTPUT_LENGTH else output

    return AgentExecution(
        execution_id=str(uuid.uuid4())[:8],
        agent=agent,
        node=node,
        template_name=template_name,
        prompt=truncated_prompt,
        output=truncated_output,
        success=success,
        exit_code=exit_code,
        duration_seconds=duration_seconds,
        cost_usd=cost_usd,
        model=model,
        task_id=task_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        timestamp=datetime.now().isoformat(),
        retries=retries,
        error_context=error_context,
    )


# Maximum executions to keep in history
MAX_EXECUTION_HISTORY = 50


def _append_executions(
    existing: Optional[list[AgentExecution]],
    new: list[AgentExecution],
) -> list[AgentExecution]:
    """Reducer for appending agent executions with size limit.

    Keeps most recent MAX_EXECUTION_HISTORY executions.

    Args:
        existing: Existing execution list
        new: New executions to append

    Returns:
        Combined list (limited to MAX_EXECUTION_HISTORY)
    """
    if existing is None:
        result = list(new)
    else:
        result = list(existing) + list(new)

    # Keep only most recent executions if over limit
    if len(result) > MAX_EXECUTION_HISTORY:
        result = result[-MAX_EXECUTION_HISTORY:]

    return result


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
    new: Optional[dict[str, AgentFeedback]],
) -> dict[str, AgentFeedback]:
    """Reducer for merging feedback from parallel agents.

    Args:
        existing: Existing feedback dict
        new: New feedback to merge

    Returns:
        Merged feedback dict
    """
    if new is None:
        return existing or {}
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


def _replace_unique(
    existing: Optional[list[str]],
    new: Optional[list[str]],
) -> list[str]:
    """Reducer for replacing lists with unique values.

    Args:
        existing: Existing list
        new: New list (replaces existing)

    Returns:
        New list with unique items (order preserved)
    """
    if new is None:
        return existing or []

    result: list[str] = []
    for item in new:
        if item not in result:
            result.append(item)
    return result


def _merge_tasks(
    existing: Optional[list[Task]],
    new: list[Task],
) -> list[Task]:
    """Reducer for merging task lists with conflict detection.

    Updates existing tasks by ID or appends new ones.
    Logs conflicts when concurrent updates modify the same task differently.

    Args:
        existing: Existing task list
        new: New or updated tasks

    Returns:
        Merged task list
    """
    import logging
    logger = logging.getLogger(__name__)

    if existing is None:
        return list(new)

    # Build a map of existing tasks by ID
    task_map = {t["id"]: t for t in existing if "id" in t}

    # Update or add new tasks with conflict detection
    for task in new:
        if "id" not in task:
            continue

        task_id = task["id"]
        if task_id in task_map:
            existing_task = task_map[task_id]
            # Check for conflicting updates (different status, attempts, etc.)
            if _detect_task_conflict(existing_task, task):
                logger.warning(
                    f"Task merge conflict detected for {task_id}: "
                    f"existing status={existing_task.get('status')}, "
                    f"new status={task.get('status')}. Using newer update."
                )
                # Merge fields instead of full overwrite to preserve data
                merged_task = _merge_task_fields(existing_task, task)
                task_map[task_id] = merged_task
            else:
                task_map[task_id] = task
        else:
            task_map[task_id] = task

    return list(task_map.values())


def _detect_task_conflict(existing: Task, new: Task) -> bool:
    """Detect if two task updates conflict.

    Args:
        existing: Existing task state
        new: New task state

    Returns:
        True if there's a conflict that needs resolution
    """
    # Conflict if both have been modified and have different statuses
    existing_status = existing.get("status")
    new_status = new.get("status")

    # If statuses are different and neither is the original, it's a conflict
    if existing_status != new_status:
        if existing_status not in (None, "pending") and new_status not in (None, "pending"):
            return True

    # Conflict if attempts differ significantly
    existing_attempts = existing.get("attempts", 0)
    new_attempts = new.get("attempts", 0)
    if abs(existing_attempts - new_attempts) > 1:
        return True

    return False


def _merge_task_fields(existing: Task, new: Task) -> Task:
    """Merge task fields, preferring newer values but preserving history.

    Args:
        existing: Existing task state
        new: New task state

    Returns:
        Merged task
    """
    merged = dict(existing)

    # Update with new values
    for key, value in new.items():
        if value is not None:
            # For lists, merge instead of overwrite
            if isinstance(value, list) and isinstance(merged.get(key), list):
                existing_list = merged[key]
                for item in value:
                    if item not in existing_list:
                        existing_list.append(item)
            else:
                merged[key] = value

    # Take the higher attempt count
    merged["attempts"] = max(
        existing.get("attempts", 0),
        new.get("attempts", 0)
    )

    return merged


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
        review_skipped: Whether reviews were skipped
        review_changed_files: Files considered for review gating
        review_skipped_reason: Reason reviews were skipped
        next_decision: Routing decision for conditional edges
        errors: List of errors (append-only)
        checkpoints: List of checkpoint IDs
        git_commits: List of commit hashes
        created_at: Workflow creation timestamp
        updated_at: Last update timestamp
        tasks: List of implementation tasks (incremental execution)
        milestones: List of task milestones
        current_task_id: ID of currently executing task
        current_task_ids: IDs of currently executing task batch
        in_flight_task_ids: IDs of tasks in progress (batch)
        completed_task_ids: IDs of completed tasks (append-only unique)
        failed_task_ids: IDs of failed tasks (append-only unique)

        # Discussion phase (GSD pattern)
        discussion_complete: Whether discussion phase completed
        context_file: Path to generated CONTEXT.md
        developer_preferences: Captured developer preferences
        needs_clarification: Whether human input is needed

        # Research phase (GSD pattern)
        research_complete: Whether research phase completed
        research_findings: Findings from research agents
        research_errors: Errors from research agents (non-blocking)

        # Execution mode (Ralph Wiggum pattern)
        execution_mode: Current execution mode (hitl or afk)

        # Token/cost tracking
        token_usage: Token and cost tracking metrics

        # Session management
        last_handoff: Path to last handoff brief

        # Fixer agent state
        fixer_enabled: Whether fixer is enabled (default True)
        fixer_attempts: Number of fix attempts this session
        fixer_circuit_breaker_open: Whether circuit breaker is open
        current_fix_attempt: Current fix attempt details
        fix_history: History of fix attempts (append-only)
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
    review_skipped: Optional[bool]
    review_changed_files: list[str]
    review_skipped_reason: Optional[str]

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
    current_task_ids: Annotated[list[str], _replace_unique]
    in_flight_task_ids: Annotated[list[str], _replace_unique]
    completed_task_ids: Annotated[list[str], _append_unique]
    failed_task_ids: Annotated[list[str], _append_unique]

    # Discussion phase (GSD pattern)
    discussion_complete: bool
    context_file: Optional[str]
    developer_preferences: Optional[dict]
    needs_clarification: bool

    # Research phase (GSD pattern)
    research_complete: bool
    research_findings: Optional[dict]
    research_errors: Optional[list[dict]]

    # Execution mode (Ralph Wiggum pattern)
    execution_mode: str  # "hitl" (human-in-the-loop) or "afk" (autonomous)

    # Token/cost tracking
    token_usage: Optional[dict]

    # Session management
    last_handoff: Optional[str]

    # Fixer agent state
    fixer_enabled: bool
    fixer_attempts: int
    fixer_circuit_breaker_open: bool
    current_fix_attempt: Optional[dict]
    fix_history: Annotated[list[dict], operator.add]

    # Auto-improvement state
    last_agent_execution: Optional[AgentExecution]  # Most recent agent execution for evaluation
    last_evaluation: Optional[dict]  # Most recent evaluation result
    last_analysis: Optional[dict]  # Most recent output analysis
    optimization_queue: list[dict]  # Templates queued for optimization
    optimization_results: list[dict]  # Results from optimization attempts
    active_experiments: dict[str, str]  # A/B testing: template -> version_id

    # Global error context (for Bugfixer agent)
    error_context: Optional[ErrorContext]  # Rich error context for current error
    execution_history: Annotated[list[AgentExecution], _append_executions]  # All agent executions


def create_initial_state(
    project_dir: str,
    project_name: str,
    execution_mode: str = "hitl",
) -> WorkflowState:
    """Create initial workflow state.

    Args:
        project_dir: Project directory path
        project_name: Project name
        execution_mode: Execution mode - "hitl" (human-in-the-loop, default) or "afk" (autonomous)

    Returns:
        Initial WorkflowState
    """
    now = datetime.now().isoformat()

    # Validate execution_mode
    if execution_mode not in ("hitl", "afk"):
        execution_mode = "hitl"  # Default to interactive mode

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
        review_skipped=False,
        review_changed_files=[],
        review_skipped_reason=None,
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
        current_task_ids=[],
        in_flight_task_ids=[],
        completed_task_ids=[],
        failed_task_ids=[],
        # Discussion phase fields (GSD pattern)
        discussion_complete=False,
        context_file=None,
        developer_preferences=None,
        needs_clarification=False,
        # Research phase fields (GSD pattern)
        research_complete=False,
        research_findings=None,
        research_errors=None,
        # Execution mode (Ralph Wiggum pattern)
        # "hitl" = human-in-the-loop (pauses for human input)
        # "afk" = away-from-keyboard (fully autonomous, no pauses)
        execution_mode=execution_mode,
        # Token/cost tracking
        token_usage=None,
        # Session management
        last_handoff=None,
        # Fixer agent state
        fixer_enabled=True,  # Fixer is ON by default
        fixer_attempts=0,
        fixer_circuit_breaker_open=False,
        current_fix_attempt=None,
        fix_history=[],
        # Auto-improvement state
        last_agent_execution=None,
        last_evaluation=None,
        last_analysis=None,
        optimization_queue=[],
        optimization_results=[],
        active_experiments={},
        # Global error context (for Bugfixer agent)
        error_context=None,
        execution_history=[],
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


class TaskIndex:
    """Indexed access to tasks for O(1) lookups.

    Provides fast access to tasks by ID and status, and caches
    dependency satisfaction checks to avoid O(n²) behavior when
    repeatedly selecting tasks.

    Usage:
        index = TaskIndex(state)
        task = index.get_by_id("T1")  # O(1)
        available = index.get_available()  # O(pending_count) first call, cached after
    """

    def __init__(self, state: WorkflowState):
        """Build task index from workflow state.

        Args:
            state: Current workflow state
        """
        self._tasks_by_id: dict[str, Task] = {}
        self._tasks_by_status: dict[str, list[Task]] = {
            TaskStatus.PENDING: [],
            TaskStatus.IN_PROGRESS: [],
            TaskStatus.COMPLETED: [],
            TaskStatus.FAILED: [],
        }
        self._completed_ids: set[str] = set(state.get("completed_task_ids", []))
        self._failed_ids: set[str] = set(state.get("failed_task_ids", []))
        self._available_cache: Optional[list[Task]] = None

        # Build indexes
        for task in state.get("tasks", []):
            task_id = task.get("id")
            if task_id:
                self._tasks_by_id[task_id] = task
                status = task.get("status", TaskStatus.PENDING)
                if status in self._tasks_by_status:
                    self._tasks_by_status[status].append(task)

    def get_by_id(self, task_id: str) -> Optional[Task]:
        """Get task by ID in O(1).

        Args:
            task_id: Task ID to find

        Returns:
            Task if found, None otherwise
        """
        return self._tasks_by_id.get(task_id)

    def get_by_status(self, status: TaskStatus) -> list[Task]:
        """Get all tasks with a given status in O(1).

        Args:
            status: Task status to filter by

        Returns:
            List of tasks with that status
        """
        return self._tasks_by_status.get(status, [])

    def get_available(self) -> list[Task]:
        """Get tasks ready to execute (pending with satisfied dependencies).

        Results are cached for repeated calls with same state.

        Returns:
            List of available tasks
        """
        if self._available_cache is not None:
            return self._available_cache

        available = []
        for task in self._tasks_by_status.get(TaskStatus.PENDING, []):
            task_id = task.get("id")

            # Skip already completed or failed
            if task_id in self._completed_ids or task_id in self._failed_ids:
                continue

            # Check dependencies
            deps = task.get("dependencies", [])
            if all(dep in self._completed_ids for dep in deps):
                available.append(task)

        self._available_cache = available
        return available

    def is_dependency_satisfied(self, task_id: str) -> bool:
        """Check if a task's dependencies are all completed.

        Args:
            task_id: Task ID to check

        Returns:
            True if all dependencies are satisfied
        """
        task = self._tasks_by_id.get(task_id)
        if not task:
            return False

        deps = task.get("dependencies", [])
        return all(dep in self._completed_ids for dep in deps)

    @property
    def total_count(self) -> int:
        """Total number of tasks."""
        return len(self._tasks_by_id)

    @property
    def completed_count(self) -> int:
        """Number of completed tasks."""
        return len(self._completed_ids)

    @property
    def pending_count(self) -> int:
        """Number of pending tasks."""
        return len(self._tasks_by_status.get(TaskStatus.PENDING, []))


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


def get_task_by_id_indexed(index: TaskIndex, task_id: str) -> Optional[Task]:
    """Get a task by ID using index (O(1)).

    Args:
        index: TaskIndex instance
        task_id: Task ID to find

    Returns:
        Task if found, None otherwise
    """
    return index.get_by_id(task_id)


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


def get_available_tasks_indexed(index: TaskIndex) -> list[Task]:
    """Get available tasks using pre-built index (O(pending_count), cached).

    Use this instead of get_available_tasks when making repeated calls,
    such as in a loop selecting tasks one by one.

    Args:
        index: Pre-built TaskIndex instance

    Returns:
        List of tasks ready to execute
    """
    return index.get_available()


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
        "current_task_ids": state.get("current_task_ids", []),
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
