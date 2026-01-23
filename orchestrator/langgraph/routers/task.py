"""Task loop routers.

Routers for the incremental task execution loop:
task_breakdown → select_task → implement_task → verify_task → (loop back)
"""

from typing import Literal

from ..state import TaskStatus, WorkflowDecision, WorkflowState, all_tasks_completed, get_task_by_id


def task_breakdown_router(
    state: WorkflowState,
) -> Literal["select_task", "human_escalation", "__end__"]:
    """Route after task breakdown.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "select_task": Tasks created, proceed to select first task
        - "human_escalation": Breakdown failed, need human help
        - "__end__": No tasks to execute
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        tasks = state.get("tasks", [])
        if not tasks:
            return "__end__"  # No tasks created
        return "select_task"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Default: check if tasks exist
    tasks = state.get("tasks", [])
    if tasks:
        return "select_task"

    return "__end__"


def select_task_router(
    state: WorkflowState,
) -> Literal[
    "implement_task", "implement_tasks_parallel", "build_verification", "human_escalation"
]:
    """Route after task selection.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "implement_task": Task selected, proceed to implementation
        - "build_verification": All tasks done, proceed to build verification
        - "human_escalation": No tasks available (deadlock)
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        current_task_ids = state.get("current_task_ids", [])
        if current_task_ids:
            if len(current_task_ids) > 1:
                return "implement_tasks_parallel"
            return "implement_task"

        current_task_id = state.get("current_task_id")
        if current_task_id:
            return "implement_task"

        # No task selected but continue - all done
        if all_tasks_completed(state):
            return "build_verification"

        # Unexpected state
        return "human_escalation"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    # Check for current task batch
    current_task_ids = state.get("current_task_ids", [])
    if current_task_ids:
        if len(current_task_ids) > 1:
            return "implement_tasks_parallel"
        return "implement_task"

    # Check for current task (legacy)
    current_task_id = state.get("current_task_id")
    if current_task_id:
        return "implement_task"

    # Check if all tasks completed
    if all_tasks_completed(state):
        return "build_verification"

    return "human_escalation"


def implement_task_router(
    state: WorkflowState,
) -> Literal["verify_task", "implement_task", "human_escalation"]:
    """Route after task implementation.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "verify_task": Implementation done, verify it
        - "implement_task": Need to retry implementation
        - "human_escalation": Implementation blocked/failed
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "verify_task"

    if decision == WorkflowDecision.RETRY or decision == "retry":
        return "implement_task"  # Retry same task

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    # Default to verification if task exists
    current_task_id = state.get("current_task_id")
    if current_task_id:
        return "verify_task"

    return "human_escalation"


def implement_tasks_parallel_router(
    state: WorkflowState,
) -> Literal["verify_tasks_parallel", "implement_tasks_parallel", "human_escalation"]:
    """Route after parallel task implementation.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "verify_tasks_parallel": Implementation done, verify batch
        - "implement_tasks_parallel": Retry batch implementation
        - "human_escalation": Implementation blocked/failed
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "verify_tasks_parallel"

    if decision == WorkflowDecision.RETRY or decision == "retry":
        return "implement_tasks_parallel"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    # Default to verification if batch exists
    current_task_ids = state.get("current_task_ids", [])
    if current_task_ids:
        return "verify_tasks_parallel"

    return "human_escalation"


def verify_task_router(
    state: WorkflowState,
) -> Literal["select_task", "implement_task", "human_escalation"]:
    """Route after task verification (THE LOOP).

    This is the key router for the task loop:
    - On success: loop back to select_task for next task
    - On failure with retries left: go to implement_task
    - On failure with no retries: escalate

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "select_task": LOOP BACK - task done, get next task
        - "implement_task": Retry - task failed but can retry
        - "human_escalation": Task failed, need human help
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        # Task verified successfully - LOOP BACK to get next task
        # But first check if there are any tasks we can actually select
        return _check_for_available_tasks_or_escalate(state, "select_task")

    if decision == WorkflowDecision.RETRY or decision == "retry":
        # Verification failed but can retry
        current_task_id = state.get("current_task_id")
        if current_task_id:
            task = get_task_by_id(state, current_task_id)
            if task:
                attempts = task.get("attempts", 0)
                max_attempts = task.get("max_attempts", 3)
                if attempts < max_attempts:
                    return "implement_task"

        # No more retries - escalate
        return "human_escalation"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    # Default: check task status
    current_task_id = state.get("current_task_id")
    if not current_task_id:
        # No current task - check if we can select one or need to escalate
        return _check_for_available_tasks_or_escalate(state, "select_task")

    task = get_task_by_id(state, current_task_id)
    if task:
        if task.get("status") == TaskStatus.COMPLETED:
            return _check_for_available_tasks_or_escalate(state, "select_task")
        elif task.get("status") == TaskStatus.FAILED:
            return "human_escalation"

    return _check_for_available_tasks_or_escalate(state, "select_task")


def verify_tasks_parallel_router(
    state: WorkflowState,
) -> Literal["select_task", "implement_tasks_parallel", "human_escalation"]:
    """Route after parallel task verification (batch loop).

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "select_task": Batch verified, select next batch
        - "implement_tasks_parallel": Retry failed tasks in batch
        - "human_escalation": Verification failed, need human help
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return _check_for_available_tasks_or_escalate(state, "select_task")

    if decision == WorkflowDecision.RETRY or decision == "retry":
        current_task_ids = state.get("current_task_ids", [])
        if current_task_ids:
            return "implement_tasks_parallel"
        return "human_escalation"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    # Default: if no batch, loop back to selection
    return _check_for_available_tasks_or_escalate(state, "select_task")


def _check_for_available_tasks_or_escalate(
    state: WorkflowState,
    default_route: Literal["select_task"],
) -> Literal["select_task", "human_escalation"]:
    """Check if there are available tasks to select, or escalate if deadlocked.

    This prevents infinite loops when remaining tasks exist but are all blocked
    by unfulfilled dependencies or other conditions.

    Args:
        state: Current workflow state
        default_route: Route to return if tasks are available

    Returns:
        "select_task" if tasks available, "human_escalation" if deadlocked
    """
    tasks = state.get("tasks", [])
    if not tasks:
        # No tasks at all - escalate (shouldn't happen but handle gracefully)
        return "human_escalation"

    # Check if all tasks are completed
    if all_tasks_completed(state):
        # All done - select_task will route to build_verification
        return default_route

    # Check if any tasks are available (not completed, not blocked by dependencies)
    completed_ids = set(state.get("completed_task_ids", []))

    available_count = 0
    for task in tasks:
        task_id = task.get("id")
        if task_id in completed_ids:
            continue

        status = task.get("status")
        if status == TaskStatus.COMPLETED:
            continue

        # Check if dependencies are met
        dependencies = task.get("dependencies", [])
        deps_met = all(dep in completed_ids for dep in dependencies)
        if deps_met and status != TaskStatus.FAILED:
            available_count += 1

    if available_count > 0:
        return default_route

    # No available tasks but incomplete tasks remain - deadlock
    # This happens when remaining tasks have unmet dependencies or all failed
    return "human_escalation"
