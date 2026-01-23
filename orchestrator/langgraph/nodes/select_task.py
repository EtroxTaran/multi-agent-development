"""Select next task node.

Selects the next task to implement based on:
- Task status (pending only)
- Dependency satisfaction
- Priority ordering
- Milestone grouping
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ...config import load_project_config
from ..integrations.board_sync import sync_board
from ..state import Task, TaskIndex, TaskStatus, WorkflowState, all_tasks_completed

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
    in_flight_ids = set(state.get("in_flight_task_ids", []))

    # Use TaskIndex for O(1) lookups and cached availability checks
    task_index = TaskIndex(state)

    # Check if all tasks are done
    if all_tasks_completed(state):
        logger.info("All tasks completed")
        return {
            "current_task_id": None,
            "current_task_ids": [],
            "in_flight_task_ids": [],
            "next_decision": "continue",  # Move to build_verification
            "updated_at": datetime.now().isoformat(),
        }

    # Get tasks that are ready to execute using O(1) indexed lookup
    # TaskIndex.get_available() is cached after first call
    available = [task for task in task_index.get_available() if task.get("id") not in in_flight_ids]

    if not available:
        # Check for dependency deadlock
        pending_tasks = [
            t for t in tasks if t.get("id") not in completed_ids and t.get("id") not in failed_ids
        ]

        if pending_tasks:
            # There are pending tasks but none available - deadlock
            logger.error("Dependency deadlock detected - no tasks available but work remains")
            return {
                "current_task_id": None,
                "current_task_ids": [],
                "in_flight_task_ids": [],
                "errors": [
                    {
                        "type": "dependency_deadlock",
                        "message": f"Dependency deadlock: {len(pending_tasks)} tasks pending but none available",
                        "pending_tasks": [t.get("id") for t in pending_tasks],
                        "timestamp": datetime.now().isoformat(),
                    }
                ],
                "next_decision": "escalate",
                "updated_at": datetime.now().isoformat(),
            }
        else:
            # All tasks either completed or failed
            logger.info("All tasks processed (some may have failed)")
            return {
                "current_task_id": None,
                "current_task_ids": [],
                "in_flight_task_ids": [],
                "next_decision": "continue",
                "updated_at": datetime.now().isoformat(),
            }

    # Sort available tasks by priority, milestone, and ID
    sorted_tasks = _sort_tasks_by_priority(available, state.get("milestones", []))

    # Determine batch size
    project_dir = Path(state["project_dir"])
    max_workers = _get_parallel_workers(project_dir)
    batch_limit = max(1, min(max_workers, len(sorted_tasks)))

    # Select a batch of independent tasks
    selected_tasks = _select_independent_tasks(sorted_tasks, batch_limit)
    if not selected_tasks:
        # Fallback to single task if independence filter excluded all
        selected_tasks = sorted_tasks[:1]

    task_ids = [task["id"] for task in selected_tasks]
    logger.info(f"Selected task batch: {task_ids}")

    # Update task statuses to in_progress
    updated_tasks = []
    for task in selected_tasks:
        updated = dict(task)
        updated["status"] = TaskStatus.IN_PROGRESS
        updated_tasks.append(updated)

    # Sync to Kanban board
    try:
        # Create updated task list for sync
        updated_task_ids = {t["id"] for t in updated_tasks}
        updated_tasks_list = [t for t in tasks if t["id"] not in updated_task_ids] + updated_tasks
        sync_state = dict(state)
        sync_state["tasks"] = updated_tasks_list
        sync_board(sync_state)
    except Exception as e:
        logger.warning(f"Failed to sync board in select task: {e}")

    return {
        "current_task_id": task_ids[0] if task_ids else None,
        "current_task_ids": task_ids,
        "in_flight_task_ids": task_ids,
        "tasks": updated_tasks,  # Will be merged by reducer
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


def _get_parallel_workers(project_dir: Path) -> int:
    """Determine parallel worker count from config or environment."""
    env_value = os.environ.get("PARALLEL_WORKERS")
    if env_value and env_value.isdigit():
        return max(1, int(env_value))

    config = load_project_config(project_dir)
    parallel_workers = getattr(config.workflow, "parallel_workers", 1)
    try:
        return max(1, int(parallel_workers))
    except (TypeError, ValueError):
        return 1


def _task_file_set(task: Task) -> set[str]:
    """Get the set of files associated with a task."""
    files = (task.get("files_to_create") or []) + (task.get("files_to_modify") or [])
    return {f for f in files if f}


def _select_independent_tasks(tasks: list[Task], limit: int) -> list[Task]:
    """Select tasks that do not share files_to_create/files_to_modify."""
    selected: list[Task] = []
    used_files: set[str] = set()

    for task in tasks:
        if len(selected) >= limit:
            break

        task_files = _task_file_set(task)

        # If task has no file metadata, keep it single to be safe
        if not task_files and selected:
            continue

        if task_files and task_files & used_files:
            continue

        selected.append(task)
        used_files.update(task_files)

    return selected


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
