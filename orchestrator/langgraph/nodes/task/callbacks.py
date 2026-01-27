"""Callback utilities for task nodes.

Provides helper functions for emitting task progress events to the
ProgressCallback registered in LangGraph config.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_progress_callback() -> Optional[Any]:
    """Get progress callback from LangGraph config.

    The callback is passed via configurable when starting the workflow.

    Returns:
        ProgressCallback if available, None otherwise
    """
    try:
        from langgraph.config import get_config

        config = get_config()
        return config.get("configurable", {}).get("progress_callback")
    except Exception:
        # LangGraph config not available (e.g., running outside workflow)
        return None


def emit_task_start(task_id: str, task_title: str) -> None:
    """Emit task_start event via progress callback.

    Args:
        task_id: Task identifier
        task_title: Task title for display
    """
    callback = get_progress_callback()
    if callback and hasattr(callback, "on_task_start"):
        try:
            callback.on_task_start(task_id, task_title)
        except Exception as e:
            logger.debug(f"Failed to emit task_start event: {e}")


def emit_task_complete(task_id: str, success: bool) -> None:
    """Emit task_complete event via progress callback.

    Args:
        task_id: Task identifier
        success: Whether the task completed successfully
    """
    callback = get_progress_callback()
    if callback and hasattr(callback, "on_task_complete"):
        try:
            callback.on_task_complete(task_id, success)
        except Exception as e:
            logger.debug(f"Failed to emit task_complete event: {e}")


def emit_ralph_iteration(
    task_id: str,
    iteration: int,
    max_iterations: int,
    tests_passed: int = 0,
    tests_total: int = 0,
) -> None:
    """Emit ralph_iteration event via progress callback.

    Used by the Ralph Wiggum loop to report TDD iteration progress.

    Args:
        task_id: Task identifier
        iteration: Current iteration number
        max_iterations: Maximum iterations configured
        tests_passed: Number of tests passing
        tests_total: Total number of tests
    """
    callback = get_progress_callback()
    if callback and hasattr(callback, "on_ralph_iteration"):
        try:
            callback.on_ralph_iteration(
                task_id, iteration, max_iterations, tests_passed, tests_total
            )
        except Exception as e:
            logger.debug(f"Failed to emit ralph_iteration event: {e}")


def emit_tasks_created(task_count: int, milestone_count: int) -> None:
    """Emit tasks_created event via progress callback.

    Used by task breakdown to notify dashboard when tasks are created.

    Args:
        task_count: Number of tasks created
        milestone_count: Number of milestones created
    """
    callback = get_progress_callback()
    if callback and hasattr(callback, "on_tasks_created"):
        try:
            callback.on_tasks_created(task_count, milestone_count)
        except Exception as e:
            logger.debug(f"Failed to emit tasks_created event: {e}")
