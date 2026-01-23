"""Storage operations for task implementation.

Handles persisting task results, clarification requests, and tracker updates.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...state import Task, TaskStatus
from ...integrations import (
    create_linear_adapter,
    load_issue_mapping,
    create_markdown_tracker,
)

logger = logging.getLogger(__name__)


def save_clarification_request(
    project_dir: Path,
    task_id: str,
    request: dict,
    project_name: str,
) -> None:
    """Save clarification request to database for human review.

    Args:
        project_dir: Project directory
        task_id: Task ID
        request: Clarification request data
        project_name: Project name for DB storage
    """
    from ....db.repositories.logs import get_logs_repository, LogType
    from ....storage.async_utils import run_async

    request_data = {
        **request,
        "task_id": task_id,
        "timestamp": datetime.now().isoformat(),
    }
    repo = get_logs_repository(project_name)
    run_async(repo.create_log(LogType.ERROR, request_data, task_id=task_id))


def save_task_result(
    project_dir: Path,
    task_id: str,
    result: dict,
    project_name: str,
) -> None:
    """Save task implementation result to database.

    Args:
        project_dir: Project directory
        task_id: Task ID
        result: Task result data
        project_name: Project name for DB storage
    """
    from ....db.repositories.phase_outputs import get_phase_output_repository
    from ....storage.async_utils import run_async

    result_data = {
        **result,
        "task_id": task_id,
        "timestamp": datetime.now().isoformat(),
    }
    repo = get_phase_output_repository(project_name)
    run_async(repo.save_task_result(task_id, result_data))


def handle_task_error(task: Task, error_message: str) -> dict[str, Any]:
    """Handle task implementation error.

    Args:
        task: Task that failed
        error_message: Error message

    Returns:
        State update with error
    """
    task_id = task.get("id", "unknown")
    max_attempts = task.get("max_attempts", 3)
    attempts = task.get("attempts", 1)

    task["error"] = error_message

    if attempts >= max_attempts:
        # Max retries exceeded - mark as failed and escalate
        task["status"] = TaskStatus.FAILED
        return {
            "tasks": [task],
            "failed_task_ids": [task_id],
            "errors": [{
                "type": "task_failed",
                "task_id": task_id,
                "message": f"Task failed after {attempts} attempts: {error_message}",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }
    else:
        # Can retry
        task["status"] = TaskStatus.PENDING
        return {
            "tasks": [task],
            "errors": [{
                "type": "task_error",
                "task_id": task_id,
                "message": error_message,
                "attempt": attempts,
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "retry",
            "updated_at": datetime.now().isoformat(),
        }


def update_task_trackers(
    project_dir: Path,
    task_id: str,
    status: TaskStatus,
    notes: Optional[str] = None,
) -> None:
    """Update task status in markdown tracker and Linear.

    Args:
        project_dir: Project directory
        task_id: Task ID
        status: New status
        notes: Optional status notes
    """
    try:
        # Update markdown tracker
        markdown_tracker = create_markdown_tracker(project_dir)
        markdown_tracker.update_task_status(task_id, status, notes)
    except Exception as e:
        logger.warning(f"Failed to update markdown tracker for task {task_id}: {e}")

    try:
        # Update Linear (if configured and issue exists)
        linear_adapter = create_linear_adapter(project_dir)
        if linear_adapter.enabled:
            # Load issue mapping to populate cache
            issue_mapping = load_issue_mapping(project_dir)
            linear_adapter._issue_cache.update(issue_mapping)
            linear_adapter.update_issue_status(task_id, status)
    except Exception as e:
        logger.warning(f"Failed to update Linear for task {task_id}: {e}")
