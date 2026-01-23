"""
Review cycle LangGraph node.

Integrates the 4-eyes review protocol into the LangGraph workflow.
This node manages the iterative review-optimize-review cycle for each task.

Usage:
    from orchestrator.langgraph.nodes.review_cycle import review_cycle_node

    # Add to workflow graph
    workflow.add_node("review_cycle", review_cycle_node)
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from langgraph.types import interrupt

from orchestrator.cleanup import CleanupManager
from orchestrator.dispatch import AgentDispatcher, Task
from orchestrator.recovery import ErrorCategory, ErrorContext, RecoveryHandler
from orchestrator.review import ReviewCycle, ReviewCycleResult

logger = logging.getLogger(__name__)


async def review_cycle_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node for running the review cycle.

    This node:
    1. Dispatches work to the assigned agent
    2. Runs parallel 4-eyes review
    3. Iterates until approval or max iterations
    4. Handles escalations with interrupt()
    5. Cleans up artifacts after completion

    Args:
        state: Current workflow state

    Returns:
        Updated state with review results
    """
    project_dir = Path(state.get("project_dir", "."))
    current_task = state.get("current_task")
    max_iterations = state.get("max_review_iterations", 3)

    if not current_task:
        logger.warning("No current task to review")
        return state

    # Initialize components
    dispatcher = AgentDispatcher(project_dir)
    cleanup_manager = CleanupManager(project_dir)
    recovery_handler = RecoveryHandler(project_dir)

    # Get assigned agent for the task
    agent_id = current_task.get("assigned_agent", "A04")
    task_id = current_task.get("id", "unknown")

    logger.info(f"Starting review cycle for task {task_id} with agent {agent_id}")

    # Create task object
    task = Task(
        id=task_id,
        title=current_task.get("title", ""),
        description=current_task.get("description", ""),
        acceptance_criteria=current_task.get("acceptance_criteria", []),
        input_files=current_task.get("input_files", []),
        expected_output_files=current_task.get("files_to_create", []),
        test_files=current_task.get("test_files", []),
    )

    # Run review cycle
    cycle = ReviewCycle(dispatcher, project_dir)

    try:
        result = await cycle.run(
            working_agent_id=agent_id,
            task=task,
            max_iterations=max_iterations,
        )

        # Handle different outcomes
        if result.final_status == "approved":
            # Success! Update state
            return _update_state_approved(state, task_id, result, cleanup_manager)

        elif result.final_status == "escalated":
            # Need human intervention
            return await _handle_escalation(state, task_id, result, recovery_handler)

        else:
            # Failed
            return _update_state_failed(state, task_id, result)

    except Exception as e:
        logger.error(f"Review cycle failed with exception: {e}")

        # Try recovery
        error_context = ErrorContext(
            category=ErrorCategory.AGENT_FAILURE,
            message=str(e),
            task_id=task_id,
            agent_id=agent_id,
        )

        recovery_result = await recovery_handler.handle_error(e, error_context)

        if recovery_result.escalation_required:
            return await _handle_escalation_from_error(state, task_id, e, recovery_handler)

        return _update_state_failed(state, task_id, None, str(e))


def _update_state_approved(
    state: dict[str, Any],
    task_id: str,
    result: ReviewCycleResult,
    cleanup_manager: CleanupManager,
) -> dict[str, Any]:
    """Update state after task approval.

    Args:
        state: Current state
        task_id: Task ID
        result: Review cycle result
        cleanup_manager: Cleanup manager

    Returns:
        Updated state
    """
    # Clean up task artifacts
    cleanup_manager.on_task_done(task_id)

    # Update task status
    tasks = state.get("tasks", [])
    for task in tasks:
        if task.get("id") == task_id:
            task["status"] = "done"
            task["review_result"] = {
                "approved": True,
                "iterations": result.iteration_count,
                "final_score": _get_average_score(result),
                "completed_at": datetime.utcnow().isoformat(),
            }
            break

    # Move to completed
    completed = state.get("completed_tasks", [])
    completed.append(task_id)

    return {
        **state,
        "tasks": tasks,
        "completed_tasks": completed,
        "current_task": None,
        "last_review_result": result.to_dict(),
    }


def _update_state_failed(
    state: dict[str, Any],
    task_id: str,
    result: Optional[ReviewCycleResult],
    error_message: Optional[str] = None,
) -> dict[str, Any]:
    """Update state after task failure.

    Args:
        state: Current state
        task_id: Task ID
        result: Review cycle result (if available)
        error_message: Error message (if exception occurred)

    Returns:
        Updated state
    """
    # Update task status
    tasks = state.get("tasks", [])
    for task in tasks:
        if task.get("id") == task_id:
            task["status"] = "failed"
            task["review_result"] = {
                "approved": False,
                "iterations": result.iteration_count if result else 0,
                "error": error_message or result.escalation_reason if result else "Unknown error",
                "failed_at": datetime.utcnow().isoformat(),
            }
            break

    # Add to blocked tasks
    blocked = state.get("blocked_tasks", [])
    blocked.append(task_id)

    return {
        **state,
        "tasks": tasks,
        "blocked_tasks": blocked,
        "current_task": None,
        "last_error": error_message or (result.escalation_reason if result else None),
    }


async def _handle_escalation(
    state: dict[str, Any],
    task_id: str,
    result: ReviewCycleResult,
    recovery_handler: RecoveryHandler,
) -> dict[str, Any]:
    """Handle escalation requiring human intervention.

    Uses LangGraph interrupt() to pause workflow for human input.

    Args:
        state: Current state
        task_id: Task ID
        result: Review cycle result
        recovery_handler: Recovery handler

    Returns:
        Updated state (after human input)
    """
    logger.info(f"Escalating task {task_id}: {result.escalation_reason}")

    # Prepare escalation context
    escalation_context = {
        "task_id": task_id,
        "reason": result.escalation_reason,
        "iterations_attempted": result.iteration_count,
        "reviews": [
            {
                "iteration": i.iteration_number,
                "reviews": [
                    {
                        "reviewer": r.reviewer_id,
                        "approved": r.approved,
                        "score": r.score,
                        "blocking_issues": r.blocking_issues,
                    }
                    for r in i.reviews
                ],
            }
            for i in result.iterations
        ],
        "options": [
            "retry_with_feedback",
            "skip_task",
            "abort_workflow",
            "manual_override_approve",
            "manual_override_reject",
        ],
    }

    # Use LangGraph interrupt to pause for human input
    human_decision = interrupt(
        {
            "type": "escalation",
            "task_id": task_id,
            "reason": result.escalation_reason,
            "context": escalation_context,
            "message": f"Task {task_id} requires human decision after {result.iteration_count} failed iterations.",
        }
    )

    # Process human decision
    if human_decision:
        action = human_decision.get("action", "skip_task")

        if action == "retry_with_feedback":
            # Human provided feedback, retry the task
            return {
                **state,
                "human_feedback": human_decision.get("feedback", ""),
                "retry_requested": True,
            }

        elif action == "manual_override_approve":
            # Human approved despite review failures
            return _update_state_approved(
                state, task_id, result, CleanupManager(Path(state.get("project_dir", ".")))
            )

        elif action == "manual_override_reject":
            # Human rejected
            return _update_state_failed(state, task_id, result, "Manually rejected by human")

        elif action == "skip_task":
            # Skip this task
            return _update_state_failed(state, task_id, result, "Skipped by human decision")

        elif action == "abort_workflow":
            # Abort entire workflow
            return {
                **state,
                "workflow_aborted": True,
                "abort_reason": "Aborted by human decision",
            }

    # Default: skip task
    return _update_state_failed(state, task_id, result, "Escalation timeout - task skipped")


async def _handle_escalation_from_error(
    state: dict[str, Any],
    task_id: str,
    error: Exception,
    recovery_handler: RecoveryHandler,
) -> dict[str, Any]:
    """Handle escalation from an exception.

    Args:
        state: Current state
        task_id: Task ID
        error: The exception
        recovery_handler: Recovery handler

    Returns:
        Updated state
    """
    # Use LangGraph interrupt
    human_decision = interrupt(
        {
            "type": "error_escalation",
            "task_id": task_id,
            "error": str(error),
            "message": f"Task {task_id} failed with error: {error}",
            "options": ["retry", "skip", "abort"],
        }
    )

    if human_decision:
        action = human_decision.get("action", "skip")

        if action == "retry":
            return {**state, "retry_requested": True}
        elif action == "abort":
            return {**state, "workflow_aborted": True, "abort_reason": str(error)}

    return _update_state_failed(state, task_id, None, str(error))


def _get_average_score(result: ReviewCycleResult) -> float:
    """Calculate average score across all reviews.

    Args:
        result: Review cycle result

    Returns:
        Average score
    """
    scores = []
    for iteration in result.iterations:
        for review in iteration.reviews:
            if review.score > 0:
                scores.append(review.score)

    return sum(scores) / len(scores) if scores else 0.0


# Sync wrapper for LangGraph
def review_cycle_node_sync(state: dict[str, Any]) -> dict[str, Any]:
    """Synchronous wrapper for review_cycle_node.

    Args:
        state: Current workflow state

    Returns:
        Updated state
    """
    return asyncio.run(review_cycle_node(state))
