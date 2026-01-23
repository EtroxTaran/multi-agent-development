"""Main node entry points for task implementation.

Provides the LangGraph node functions for implementing tasks.
"""

import asyncio
import concurrent.futures
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...state import (
    WorkflowState,
    Task,
    TaskStatus,
    TaskIndex,
    get_task_by_id,
)
from ....storage import get_budget_storage
from ....utils.worktree import WorktreeManager, WorktreeError
from ....specialists.runner import SpecialistRunner
from ...integrations.board_sync import sync_board
from .modes import (
    TASK_TIMEOUT,
    RALPH_TIMEOUT,
    FALLBACK_MODEL,
    should_use_ralph_loop,
    should_use_unified_loop,
    implement_with_ralph_loop,
    implement_with_unified_loop,
    implement_standard,
)
from .prompts import build_task_prompt
from .output import parse_task_output
from .storage import (
    save_clarification_request,
    save_task_result,
    handle_task_error,
    update_task_trackers,
)

logger = logging.getLogger(__name__)

# Default estimated cost per task implementation (conservative estimate)
ESTIMATED_TASK_COST_USD = 0.50
FALLBACK_COST_RATIO = 0.1  # Haiku is ~10x cheaper than Sonnet
ESTIMATED_FALLBACK_COST_USD = ESTIMATED_TASK_COST_USD * FALLBACK_COST_RATIO


def _check_budget_before_task(
    project_dir: Path,
    task_id: str,
    estimated_cost: float = ESTIMATED_TASK_COST_USD,
) -> Optional[dict[str, Any]]:
    """Check budget before starting task implementation.

    Returns None if budget is OK, or a state update dict if budget
    is exceeded (either escalate or abort). Implements graceful degradation
    by suggesting a fallback (cheaper) model before escalating.

    Args:
        project_dir: Project directory
        task_id: Task being implemented
        estimated_cost: Estimated cost of implementation

    Returns:
        None if OK, or dict with errors/escalation/use_fallback if budget issue
    """
    try:
        budget_manager = get_budget_storage(project_dir)

        # Quick check if budgets are disabled
        if not hasattr(budget_manager, 'config') or not getattr(budget_manager.config, 'enabled', True):
            return None

        # Enforce budget with structured result
        result = budget_manager.enforce_budget(task_id, estimated_cost)

        if result.should_abort:
            # Hard stop - budget completely exhausted
            logger.error(f"Budget exhausted, aborting: {result.message}")
            return {
                "errors": [{
                    "type": "budget_exceeded_error",
                    "message": f"Budget exhausted: {result.message}",
                    "exceeded_type": result.exceeded_type,
                    "limit_usd": result.limit_usd,
                    "current_usd": result.current_usd,
                    "timestamp": datetime.now().isoformat(),
                }],
                "next_decision": "escalate",
                "budget_status": result.to_dict(),
            }

        if not result.allowed:
            # Budget exceeded for primary model - try fallback model
            fallback_cost = estimated_cost * FALLBACK_COST_RATIO
            fallback_result = budget_manager.enforce_budget(task_id, fallback_cost)

            if fallback_result.allowed:
                # Fallback model fits within budget - signal to use it
                logger.info(
                    f"Budget tight for task {task_id}, switching to fallback model "
                    f"({FALLBACK_MODEL}). Primary cost: ${estimated_cost:.2f}, "
                    f"Fallback cost: ${fallback_cost:.2f}, "
                    f"Remaining: ${result.remaining_usd:.2f}"
                )
                return {
                    "use_fallback_model": True,
                    "fallback_model": FALLBACK_MODEL,
                    "fallback_reason": "budget_constraint",
                    "original_cost": estimated_cost,
                    "fallback_cost": fallback_cost,
                    "remaining_budget": result.remaining_usd,
                }
            else:
                # Even fallback doesn't fit - escalate
                logger.warning(
                    f"Budget exceeded for task {task_id}, even fallback model "
                    f"({FALLBACK_MODEL}) doesn't fit. Escalating."
                )
                return {
                    "errors": [{
                        "type": "budget_limit_reached",
                        "message": f"Budget limit reached: {result.message}. Even fallback model exceeds budget.",
                        "exceeded_type": result.exceeded_type,
                        "limit_usd": result.limit_usd,
                        "current_usd": result.current_usd,
                        "remaining_usd": result.remaining_usd,
                        "fallback_attempted": True,
                        "timestamp": datetime.now().isoformat(),
                    }],
                    "next_decision": "escalate",
                    "budget_status": result.to_dict(),
                }

        if result.should_escalate:
            # Approaching limit - log warning but continue
            logger.warning(f"Budget warning: {result.message}")

        return None  # OK to proceed

    except AttributeError as e:
        # Budget manager doesn't have expected interface - continue without budget checks
        logger.debug(f"Budget manager interface mismatch (continuing anyway): {e}")
        return None
    except Exception as e:
        # Don't block on budget check failures - log and continue
        logger.warning(f"Budget check failed (continuing anyway): {e}")
        return None


async def implement_task_node(state: WorkflowState) -> dict[str, Any]:
    """Implement the current task.

    Spawns a worker Claude to implement the single selected task
    with focused scope and TDD practices.

    Supports two modes:
    - Standard: Single worker invocation (default for simple tasks)
    - Ralph Wiggum: Iterative loop until tests pass (for TDD tasks)

    Set USE_RALPH_LOOP env var to control: "auto", "true", "false"

    Args:
        state: Current workflow state

    Returns:
        State updates with task implementation result
    """
    task_id = state.get("current_task_id")
    if not task_id:
        return {
            "errors": [{
                "type": "implement_task_error",
                "message": "No task selected for implementation",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
        }

    task = get_task_by_id(state, task_id)
    if not task:
        return {
            "errors": [{
                "type": "implement_task_error",
                "message": f"Task {task_id} not found",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
        }

    logger.info(f"Implementing task: {task_id} - {task.get('title', 'Unknown')}")

    project_dir = Path(state["project_dir"])

    # Check budget before implementation
    budget_result = _check_budget_before_task(project_dir, task_id)

    # Handle budget check result
    use_fallback_model = False
    fallback_model = None

    if budget_result is not None:
        if budget_result.get("use_fallback_model"):
            # Budget tight but fallback model fits - use it
            use_fallback_model = True
            fallback_model = budget_result.get("fallback_model", FALLBACK_MODEL)
            logger.info(f"Using fallback model '{fallback_model}' due to budget constraints")
        else:
            # Budget exceeded or other error - return the error state
            return budget_result

    # Update task attempt count
    updated_task = dict(task)
    updated_task["attempts"] = updated_task.get("attempts", 0) + 1
    updated_task["status"] = TaskStatus.IN_PROGRESS

    # Update task status in trackers
    update_task_trackers(project_dir, task_id, TaskStatus.IN_PROGRESS)

    # Decide which execution mode to use
    use_unified = should_use_unified_loop(task, project_dir)
    use_ralph = should_use_ralph_loop(task, project_dir)

    if use_unified:
        logger.info(f"Using unified loop for task {task_id}")
        return await implement_with_unified_loop(
            state=state,
            task=task,
            updated_task=updated_task,
            project_dir=project_dir,
            use_fallback_model=use_fallback_model,
            fallback_model=fallback_model,
        )
    elif use_ralph:
        logger.info(f"Using Ralph Wiggum loop for task {task_id}")
        return await implement_with_ralph_loop(
            state=state,
            task=task,
            updated_task=updated_task,
            project_dir=project_dir,
            use_fallback_model=use_fallback_model,
            fallback_model=fallback_model,
        )
    else:
        logger.info(f"Using standard implementation for task {task_id}")
        return await implement_standard(
            state=state,
            task=task,
            updated_task=updated_task,
            project_dir=project_dir,
            use_fallback_model=use_fallback_model,
            fallback_model=fallback_model,
        )


def _run_task_in_worktree(
    worktree_path: Path,
    task: Task,
    state: Optional[WorkflowState],
) -> dict[str, Any]:
    """Run a task implementation inside a worktree.

    Args:
        worktree_path: Path to the worktree
        task: Task to implement
        state: Workflow state

    Returns:
        Result dict with success, output, and error
    """
    runner = SpecialistRunner(worktree_path)
    prompt = build_task_prompt(task, state, worktree_path)
    result = runner.create_agent("A04-implementer").run(prompt)

    return {
        "success": result.success,
        "output": result.output or "",
        "error": result.error,
    }


async def implement_tasks_parallel_node(state: WorkflowState) -> dict[str, Any]:
    """Implement a batch of tasks in parallel using git worktrees.

    Args:
        state: Current workflow state

    Returns:
        State updates with task implementation results
    """
    task_ids = state.get("current_task_ids", [])
    if not task_ids:
        return {
            "errors": [{
                "type": "implement_task_error",
                "message": "No task batch selected for implementation",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
        }

    project_dir = Path(state["project_dir"])

    # Check budget before parallel implementation
    # Estimate cost as number of tasks * per-task cost
    total_estimated_cost = len(task_ids) * ESTIMATED_TASK_COST_USD
    budget_result = _check_budget_before_task(
        project_dir,
        task_ids[0],  # Use first task ID for tracking
        estimated_cost=total_estimated_cost,
    )
    if budget_result is not None:
        return budget_result

    # Use TaskIndex for O(1) lookups when fetching multiple tasks
    task_index = TaskIndex(state)
    tasks = []
    for task_id in task_ids:
        task = task_index.get_by_id(task_id)  # O(1) instead of O(n)
        if not task:
            return {
                "errors": [{
                    "type": "implement_task_error",
                    "message": f"Task {task_id} not found",
                    "timestamp": datetime.now().isoformat(),
                }],
                "next_decision": "escalate",
            }
        tasks.append(task)

    # Update task attempt counts and statuses
    updated_tasks = []
    for task in tasks:
        updated = dict(task)
        updated["attempts"] = updated.get("attempts", 0) + 1
        updated["status"] = TaskStatus.IN_PROGRESS
        updated_tasks.append(updated)
        update_task_trackers(project_dir, updated["id"], TaskStatus.IN_PROGRESS)

    results: list[dict] = []
    errors: list[dict] = []
    failed_task_ids: list[str] = []
    retry_task_ids: list[str] = []
    should_escalate = False

    try:
        with WorktreeManager(project_dir) as wt_manager:
            worktrees = []

            for task in tasks:
                try:
                    worktree = wt_manager.create_worktree(task.get("id", "task"))
                    worktrees.append((worktree, task))
                except WorktreeError as e:
                    logger.error(f"Failed to create worktree for task {task.get('id')}: {e}")
                    errors.append({
                        "type": "worktree_error",
                        "task_id": task.get("id"),
                        "message": str(e),
                        "timestamp": datetime.now().isoformat(),
                    })
                    should_escalate = True

            if should_escalate:
                return {
                    "tasks": updated_tasks,
                    "errors": errors,
                    "next_decision": "escalate",
                    "updated_at": datetime.now().isoformat(),
                }

            # Execute tasks in parallel
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(worktrees)) as executor:
                futures = [
                    loop.run_in_executor(
                        executor,
                        _run_task_in_worktree,
                        worktree,
                        task,
                        state,
                    )
                    for worktree, task in worktrees
                ]

                completed = await asyncio.gather(*futures, return_exceptions=True)

            # Process results and merge sequentially
            for (worktree, task), result in zip(worktrees, completed):
                task_id = task.get("id", "unknown")

                if isinstance(result, Exception):
                    logger.error(f"Task {task_id} failed in worktree: {result}")
                    result = {
                        "success": False,
                        "error": str(result),
                        "output": None,
                    }

                if result.get("success"):
                    try:
                        commit_msg = f"Task: {task.get('title', task_id)}"
                        wt_manager.merge_worktree(worktree, commit_msg)
                    except WorktreeError as e:
                        logger.error(f"Failed to merge worktree for task {task_id}: {e}")
                        result = {
                            "success": False,
                            "error": str(e),
                            "output": result.get("output"),
                        }

                results.append({"task_id": task_id, **result})

    except WorktreeError as e:
        logger.error(f"Parallel implementation failed: {e}")
        return {
            "tasks": updated_tasks,
            "errors": [{
                "type": "worktree_error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    # Apply task-level updates based on results
    updated_tasks_map = {t["id"]: t for t in updated_tasks}
    for result in results:
        task_id = result["task_id"]
        task = updated_tasks_map.get(task_id, {"id": task_id})

        if result.get("success"):
            output = parse_task_output(result.get("output", ""), task_id)

            if output.get("status") == "needs_clarification":
                task["status"] = TaskStatus.BLOCKED
                task["error"] = f"Needs clarification: {output.get('question', 'Unknown')}"
                save_clarification_request(project_dir, task_id, output, state["project_name"])
                errors.append({
                    "type": "task_clarification_needed",
                    "task_id": task_id,
                    "question": output.get("question"),
                    "options": output.get("options", []),
                    "timestamp": datetime.now().isoformat(),
                })
                should_escalate = True
                continue

            save_task_result(project_dir, task_id, output, state["project_name"])
            task["implementation_notes"] = output.get("implementation_notes", "")
        else:
            error_message = result.get("error") or "Task implementation failed"
            task_update = handle_task_error(task, error_message)

            # Capture updates from error handler
            task = task_update["tasks"][0]
            errors.extend(task_update.get("errors", []))
            failed_task_ids.extend(task_update.get("failed_task_ids", []))

            if task_update.get("next_decision") == "retry":
                retry_task_ids.append(task_id)
            else:
                should_escalate = True

        updated_tasks_map[task_id] = task

    # Sync to Kanban board
    try:
        tasks = state.get("tasks", [])
        updated_task_ids = set(updated_tasks_map.keys())
        updated_tasks_list = [t for t in tasks if t["id"] not in updated_task_ids] + list(updated_tasks_map.values())
        sync_state = dict(state)
        sync_state["tasks"] = updated_tasks_list
        sync_board(sync_state)
    except Exception as e:
        logger.warning(f"Failed to sync board in parallel implement: {e}")

    next_decision = "continue"
    current_task_ids = []
    in_flight_task_ids = []
    current_task_id = None

    if should_escalate:
        next_decision = "escalate"
    elif retry_task_ids:
        next_decision = "retry"
        current_task_ids = retry_task_ids
        in_flight_task_ids = retry_task_ids
        current_task_id = retry_task_ids[0]

    return {
        "tasks": list(updated_tasks_map.values()),
        "failed_task_ids": failed_task_ids,
        "errors": errors,
        "current_task_id": current_task_id,
        "current_task_ids": current_task_ids,
        "in_flight_task_ids": in_flight_task_ids,
        "next_decision": next_decision,
        "updated_at": datetime.now().isoformat(),
    }
