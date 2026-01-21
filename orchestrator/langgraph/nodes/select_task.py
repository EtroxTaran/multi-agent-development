"""Select next task node.

Selects the next task to implement based on:
- Task status (pending only)
- Dependency satisfaction
- Priority ordering
- Milestone grouping
"""

import logging
from datetime import datetime
from typing import Any, Optional

from ..state import (
    WorkflowState,
    Task,
    TaskStatus,
    get_available_tasks,
    get_task_by_id,
    all_tasks_completed,
)

logger = logging.getLogger(__name__)

# Priority ordering (highest first)
PRIORITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


async def select_next_task_node(state: WorkflowState) -> dict[str, Any]:
    """Select the next task to implement.

    Selection algorithm:
    1. Filter tasks with status == "pending"
    2. Filter tasks with all dependencies in completed_task_ids
    3. Sort by: priority (high first) → milestone order → task ID
    4. Select first available task
    5. If none available but tasks remain → dependency deadlock → escalate

    Args:
        state: Current workflow state

    Returns:
        State updates with current_task_id or next_decision
    """
    logger.info(f"Selecting next task for: {state['project_name']}")

    tasks = state.get("tasks", [])
    completed_ids = set(state.get("completed_task_ids", []))
    failed_ids = set(state.get("failed_task_ids", []))

    # Check if all tasks are done
    if all_tasks_completed(state):
        logger.info("All tasks completed")
        return {
            "current_task_id": None,
            "next_decision": "continue",  # Move to build_verification
            "updated_at": datetime.now().isoformat(),
        }

    # Get tasks that are ready to execute
    available = get_available_tasks(state)

    if not available:
        # Check for dependency deadlock
        pending_tasks = [t for t in tasks if t.get("id") not in completed_ids and t.get("id") not in failed_ids]

        if pending_tasks:
            # There are pending tasks but none available - deadlock
            logger.error("Dependency deadlock detected - no tasks available but work remains")
            return {
                "current_task_id": None,
                "errors": [{
                    "type": "dependency_deadlock",
                    "message": f"Dependency deadlock: {len(pending_tasks)} tasks pending but none available",
                    "pending_tasks": [t.get("id") for t in pending_tasks],
                    "timestamp": datetime.now().isoformat(),
                }],
                "next_decision": "escalate",
                "updated_at": datetime.now().isoformat(),
            }
        else:
            # All tasks either completed or failed
            logger.info("All tasks processed (some may have failed)")
            return {
                "current_task_id": None,
                "next_decision": "continue",
                "updated_at": datetime.now().isoformat(),
            }

    # Sort available tasks by priority, milestone, and ID
    sorted_tasks = _sort_tasks_by_priority(available, state.get("milestones", []))

    # Select the first task
    selected = sorted_tasks[0]
    task_id = selected["id"]

    # Update task status to in_progress
    updated_task = dict(selected)
    updated_task["status"] = TaskStatus.IN_PROGRESS

    logger.info(f"Selected task: {task_id} - {selected.get('title', 'Unknown')}")

    return {
        "current_task_id": task_id,
        "tasks": [updated_task],  # Will be merged by reducer
        "next_decision": "continue",
        "updated_at": datetime.now().isoformat(),
    }


def _sort_tasks_by_priority(
    tasks: list[Task],
    milestones: list[dict],
) -> list[Task]:
    """Sort tasks by priority, milestone order, and task ID.

    Args:
        tasks: List of available tasks
        milestones: List of milestones for ordering

    Returns:
        Sorted task list
    """
    # Build milestone order map
    milestone_order = {m.get("id"): i for i, m in enumerate(milestones)}

    def sort_key(task: Task) -> tuple:
        priority = PRIORITY_ORDER.get(task.get("priority", "medium"), 2)
        milestone_id = task.get("milestone_id", "")
        milestone_pos = milestone_order.get(milestone_id, 999)

        # Extract numeric part of task ID for stable ordering
        task_id = task.get("id", "T999")
        try:
            task_num = int(task_id.lstrip("T"))
        except ValueError:
            task_num = 999

        return (priority, milestone_pos, task_num)

    return sorted(tasks, key=sort_key)


def get_task_summary(state: WorkflowState) -> dict:
    """Get a summary of task progress.

    Args:
        state: Current workflow state

    Returns:
        Summary dictionary
    """
    tasks = state.get("tasks", [])
    completed_ids = set(state.get("completed_task_ids", []))
    failed_ids = set(state.get("failed_task_ids", []))

    pending = []
    in_progress = []
    completed = []
    failed = []

    for task in tasks:
        task_id = task.get("id")
        if task_id in completed_ids:
            completed.append(task_id)
        elif task_id in failed_ids:
            failed.append(task_id)
        elif task.get("status") == TaskStatus.IN_PROGRESS:
            in_progress.append(task_id)
        else:
            pending.append(task_id)

    return {
        "total": len(tasks),
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "failed": failed,
        "current_task_id": state.get("current_task_id"),
        "progress_percent": (len(completed) / len(tasks) * 100) if tasks else 100,
    }
