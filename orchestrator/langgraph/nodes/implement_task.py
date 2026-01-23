"""Implement task node.

Implements a single task using worker Claude with focused scope.
Only implements the current task's acceptance criteria.

Supports two execution modes:
1. Standard: Single worker invocation with TDD prompt
2. Ralph Wiggum: Iterative loop until tests pass (fresh context each iteration)

Ralph Wiggum mode is recommended when tests already exist (TDD workflow).
"""

import asyncio
import concurrent.futures
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..state import (
    WorkflowState,
    Task,
    TaskStatus,
    TaskIndex,
    get_task_by_id,
)
from ..integrations.ralph_loop import (
    RalphLoopConfig,
    run_ralph_loop,
    detect_test_framework,
)
from ..integrations.unified_loop import (
    UnifiedLoopRunner,
    UnifiedLoopConfig,
    LoopContext,
    should_use_unified_loop,
)
from ..integrations import (
    create_linear_adapter,
    load_issue_mapping,
    create_markdown_tracker,
)
from ..integrations.board_sync import sync_board
from ...specialists.runner import SpecialistRunner
from ...cleanup import CleanupManager
from ...utils.worktree import WorktreeManager, WorktreeError
from ...agents import BudgetExceeded
from ...storage import get_budget_storage

logger = logging.getLogger(__name__)

# Configuration
TASK_TIMEOUT = 600  # 10 minutes per task (standard mode)
RALPH_TIMEOUT = 1800  # 30 minutes total for Ralph loop
MAX_CONCURRENT_OPERATIONS = 1  # Single writer

# Environment variable to enable Ralph Wiggum mode
USE_RALPH_LOOP = os.environ.get("USE_RALPH_LOOP", "auto")  # "auto", "true", "false"

# Environment variable to enable Unified Loop (Ralph Wiggum for all agents)
USE_UNIFIED_LOOP_ENV = os.environ.get("USE_UNIFIED_LOOP", "false").lower() == "true"

# Environment variables for agent/model selection in unified loop
LOOP_AGENT = os.environ.get("LOOP_AGENT", "claude")  # claude, cursor, gemini
LOOP_MODEL = os.environ.get("LOOP_MODEL")  # codex-5.2, composer, gemini-2.0-flash, etc.

# Scoped prompt for minimal context workers - focuses only on task-relevant files
SCOPED_TASK_PROMPT = """## Task
{description}

## Acceptance Criteria
{acceptance_criteria}

## Files to Create
{files_to_create}

## Files to Modify
{files_to_modify}

## Test Files
{test_files}

## Instructions
1. Read only the files listed above
2. Implement using TDD (write/update tests first)
3. Do NOT read orchestration files (.workflow/, plan.json)
4. Follow existing code patterns in the project
5. Signal completion with: <promise>DONE</promise>

## Output
When complete, output a JSON object:
{{
    "task_id": "{task_id}",
    "status": "completed",
    "files_created": [],
    "files_modified": [],
    "tests_written": [],
    "tests_passed": true,
    "implementation_notes": "Brief notes"
}}
"""

# Default estimated cost per task implementation (conservative estimate)
ESTIMATED_TASK_COST_USD = 0.50


def _check_budget_before_task(
    project_dir: Path,
    task_id: str,
    estimated_cost: float = ESTIMATED_TASK_COST_USD,
) -> Optional[dict[str, Any]]:
    """Check budget before starting task implementation.

    Returns None if budget is OK, or a state update dict if budget
    is exceeded (either escalate or abort).

    Args:
        project_dir: Project directory
        task_id: Task being implemented
        estimated_cost: Estimated cost of implementation

    Returns:
        None if OK, or dict with errors/escalation if budget exceeded
    """
    try:
        budget_manager = get_budget_storage(project_dir)

        # Quick check if budgets are disabled
        if not budget_manager.config.enabled:
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
            # Budget exceeded but not completely exhausted - escalate
            logger.warning(f"Budget exceeded, escalating: {result.message}")
            return {
                "errors": [{
                    "type": "budget_limit_reached",
                    "message": f"Budget limit reached: {result.message}",
                    "exceeded_type": result.exceeded_type,
                    "limit_usd": result.limit_usd,
                    "current_usd": result.current_usd,
                    "remaining_usd": result.remaining_usd,
                    "timestamp": datetime.now().isoformat(),
                }],
                "next_decision": "escalate",
                "budget_status": result.to_dict(),
            }

        if result.should_escalate:
            # Approaching limit - log warning but continue
            logger.warning(f"Budget warning: {result.message}")

        return None  # OK to proceed

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
    if budget_result is not None:
        return budget_result

    # Update task attempt count
    updated_task = dict(task)
    updated_task["attempts"] = updated_task.get("attempts", 0) + 1
    updated_task["status"] = TaskStatus.IN_PROGRESS

    # Update task status in trackers
    _update_task_trackers(project_dir, task_id, TaskStatus.IN_PROGRESS)

    # Decide which execution mode to use
    use_unified = _should_use_unified_loop(task, project_dir)
    use_ralph = _should_use_ralph_loop(task, project_dir)

    if use_unified:
        logger.info(f"Using unified loop for task {task_id} (agent: {LOOP_AGENT})")
        return await _implement_with_unified_loop(
            state=state,
            task=task,
            updated_task=updated_task,
            project_dir=project_dir,
        )
    elif use_ralph:
        logger.info(f"Using Ralph Wiggum loop for task {task_id}")
        return await _implement_with_ralph_loop(
            state=state,
            task=task,
            updated_task=updated_task,
            project_dir=project_dir,
        )
    else:
        logger.info(f"Using standard implementation for task {task_id}")
        return await _implement_standard(
            state=state,
            task=task,
            updated_task=updated_task,
            project_dir=project_dir,
        )


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
        _update_task_trackers(project_dir, updated["id"], TaskStatus.IN_PROGRESS)

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
            output = _parse_task_output(result.get("output", ""), task_id)

            if output.get("status") == "needs_clarification":
                task["status"] = TaskStatus.BLOCKED
                task["error"] = f"Needs clarification: {output.get('question', 'Unknown')}"
                _save_clarification_request(project_dir, task_id, output, state["project_name"])
                errors.append({
                    "type": "task_clarification_needed",
                    "task_id": task_id,
                    "question": output.get("question"),
                    "options": output.get("options", []),
                    "timestamp": datetime.now().isoformat(),
                })
                should_escalate = True
                continue

            _save_task_result(project_dir, task_id, output, state["project_name"])
            task["implementation_notes"] = output.get("implementation_notes", "")
        else:
            error_message = result.get("error") or "Task implementation failed"
            task_update = _handle_task_error(task, error_message)

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


def _should_use_ralph_loop(task: Task, project_dir: Path) -> bool:
    """Determine whether to use Ralph Wiggum loop for this task.

    Uses Ralph loop when:
    - USE_RALPH_LOOP=true (always use)
    - USE_RALPH_LOOP=auto AND task has test_files defined

    Args:
        task: Task to implement
        project_dir: Project directory

    Returns:
        True if Ralph loop should be used
    """
    ralph_setting = USE_RALPH_LOOP.lower()

    if ralph_setting == "false":
        return False

    if ralph_setting == "true":
        return True

    # Auto mode: use Ralph if tests are specified
    if ralph_setting == "auto":
        test_files = task.get("test_files", [])
        return len(test_files) > 0

    return False


def _should_use_unified_loop(task: Task, project_dir: Path) -> bool:
    """Determine whether to use unified loop for this task.

    Uses unified loop when:
    - USE_UNIFIED_LOOP=true (environment variable)
    - Or task specifies a non-Claude agent

    The unified loop works with any agent (Claude, Cursor, Gemini).

    Args:
        task: Task to implement
        project_dir: Project directory

    Returns:
        True if unified loop should be used
    """
    # Check environment variable
    if USE_UNIFIED_LOOP_ENV:
        return True

    # Check if task specifies a non-Claude agent
    agent_type = task.get("agent_type") or task.get("primary_cli")
    if agent_type and agent_type.lower() in ("cursor", "gemini"):
        return True

    # Check LOOP_AGENT environment variable
    if LOOP_AGENT.lower() in ("cursor", "gemini"):
        return True

    return False


def _get_unified_loop_config(task: Task, project_dir: Path) -> UnifiedLoopConfig:
    """Get unified loop configuration for a task.

    Args:
        task: Task to implement
        project_dir: Project directory

    Returns:
        Configured UnifiedLoopConfig
    """
    # Determine agent type
    agent_type = LOOP_AGENT
    if task.get("agent_type"):
        agent_type = task.get("agent_type")
    elif task.get("primary_cli"):
        agent_type = task.get("primary_cli")

    # Determine model
    model = LOOP_MODEL
    if task.get("model"):
        model = task.get("model")

    # Determine verification type
    verification = "tests"
    if task.get("test_files"):
        verification = "tests"
    elif task.get("verification"):
        verification = task.get("verification")

    return UnifiedLoopConfig(
        agent_type=agent_type,
        model=model,
        max_iterations=10,
        iteration_timeout=300,
        verification=verification,
        enable_session=(agent_type.lower() == "claude"),
        enable_error_context=True,
        enable_budget=True,
        budget_per_iteration=0.50,
        max_budget=5.00,
        save_iteration_logs=True,
    )


async def _implement_with_ralph_loop(
    state: WorkflowState,
    task: Task,
    updated_task: dict,
    project_dir: Path,
) -> dict[str, Any]:
    """Implement task using Ralph Wiggum iterative loop.

    Runs Claude in a loop until all tests pass, with fresh context
    each iteration to avoid degradation.

    Args:
        state: Workflow state
        task: Task definition
        updated_task: Task with updated attempt count
        project_dir: Project directory

    Returns:
        State updates
    """
    task_id = task["id"]

    # Configure Ralph loop
    test_command = detect_test_framework(project_dir)
    config = RalphLoopConfig(
        max_iterations=10,
        iteration_timeout=300,  # 5 min per iteration
        test_command=test_command,
        save_iteration_logs=True,
    )

    try:
        result = await asyncio.wait_for(
            run_ralph_loop(
                project_dir=project_dir,
                task_id=task_id,
                title=task.get("title", ""),
                user_story=task.get("user_story", ""),
                acceptance_criteria=task.get("acceptance_criteria", []),
                files_to_create=task.get("files_to_create", []),
                files_to_modify=task.get("files_to_modify", []),
                test_files=task.get("test_files", []),
                config=config,
            ),
            timeout=RALPH_TIMEOUT,
        )

        if result.success:
            # Task completed successfully
            _save_task_result(project_dir, task_id, {
                "status": "completed",
                "implementation_mode": "ralph_wiggum",
                "iterations": result.iterations,
                "total_time_seconds": result.total_time_seconds,
                "completion_reason": result.completion_reason,
                **(result.final_output or {}),
            }, state["project_name"])

            updated_task["implementation_notes"] = (
                f"Completed via Ralph loop in {result.iterations} iteration(s). "
                f"Reason: {result.completion_reason}"
            )

            logger.info(
                f"Task {task_id} completed via Ralph loop "
                f"in {result.iterations} iterations"
            )

            # Cleanup transient/session artifacts for this task
            try:
                cleanup_manager = CleanupManager(project_dir)
                cleanup_result = cleanup_manager.on_task_done(task_id)
                logger.debug(
                    f"Cleanup for task {task_id}: {cleanup_result.total_deleted} items, "
                    f"{cleanup_result.bytes_freed} bytes freed"
                )
            except Exception as e:
                logger.warning(f"Cleanup failed for task {task_id}: {e}")

            return {
                "tasks": [updated_task],
                "next_decision": "continue",  # Go to verify_task
                "updated_at": datetime.now().isoformat(),
            }
        else:
            # Ralph loop failed
            logger.warning(
                f"Ralph loop failed for task {task_id}: {result.error}"
            )
            return _handle_task_error(
                updated_task,
                f"Ralph loop failed after {result.iterations} iterations: {result.error}",
            )

    except asyncio.TimeoutError:
        logger.error(f"Ralph loop for task {task_id} timed out")
        return _handle_task_error(
            updated_task,
            f"Ralph loop timed out after {RALPH_TIMEOUT // 60} minutes",
        )
    except Exception as e:
        logger.error(f"Ralph loop for task {task_id} failed: {e}")
        return _handle_task_error(updated_task, str(e))


async def _implement_with_unified_loop(
    state: WorkflowState,
    task: Task,
    updated_task: dict,
    project_dir: Path,
) -> dict[str, Any]:
    """Implement task using unified loop pattern (works with any agent).

    This is the universal version of Ralph Wiggum that works with
    Claude, Cursor, and Gemini agents. Uses the adapter layer to
    abstract CLI differences.

    Args:
        state: Workflow state
        task: Task definition
        updated_task: Task with updated attempt count
        project_dir: Project directory

    Returns:
        State updates
    """
    task_id = task["id"]

    # Get unified loop configuration
    config = _get_unified_loop_config(task, project_dir)

    # Build loop context
    context = LoopContext(
        task_id=task_id,
        title=task.get("title", ""),
        user_story=task.get("user_story", ""),
        acceptance_criteria=task.get("acceptance_criteria", []),
        files_to_create=task.get("files_to_create", []),
        files_to_modify=task.get("files_to_modify", []),
        test_files=task.get("test_files", []),
    )

    try:
        # Create and run unified loop
        runner = UnifiedLoopRunner(project_dir, config)
        result = await asyncio.wait_for(
            runner.run(task_id, context=context),
            timeout=RALPH_TIMEOUT,
        )

        if result.success:
            # Task completed successfully
            _save_task_result(project_dir, task_id, {
                "status": "completed",
                "implementation_mode": "unified_loop",
                "agent_type": result.agent_type,
                "model": result.model,
                "iterations": result.iterations,
                "total_time_seconds": result.total_time_seconds,
                "total_cost_usd": result.total_cost_usd,
                "completion_reason": result.completion_reason,
                **(result.final_output or {}),
            }, state["project_name"])

            updated_task["implementation_notes"] = (
                f"Completed via unified loop ({result.agent_type}) "
                f"in {result.iterations} iteration(s). "
                f"Reason: {result.completion_reason}. "
                f"Cost: ${result.total_cost_usd:.4f}"
            )

            logger.info(
                f"Task {task_id} completed via unified loop "
                f"({result.agent_type}) in {result.iterations} iterations"
            )

            # Cleanup transient artifacts
            try:
                cleanup_manager = CleanupManager(project_dir)
                cleanup_result = cleanup_manager.on_task_done(task_id)
                logger.debug(
                    f"Cleanup for task {task_id}: {cleanup_result.total_deleted} items, "
                    f"{cleanup_result.bytes_freed} bytes freed"
                )
            except Exception as e:
                logger.warning(f"Cleanup failed for task {task_id}: {e}")

            return {
                "tasks": [updated_task],
                "next_decision": "continue",
                "updated_at": datetime.now().isoformat(),
            }
        else:
            # Unified loop failed
            logger.warning(
                f"Unified loop failed for task {task_id}: {result.error}"
            )
            return _handle_task_error(
                updated_task,
                f"Unified loop failed after {result.iterations} iterations "
                f"({result.agent_type}): {result.error}",
            )

    except asyncio.TimeoutError:
        logger.error(f"Unified loop for task {task_id} timed out")
        return _handle_task_error(
            updated_task,
            f"Unified loop timed out after {RALPH_TIMEOUT // 60} minutes",
        )
    except Exception as e:
        logger.error(f"Unified loop for task {task_id} failed: {e}")
        return _handle_task_error(updated_task, str(e))


async def _implement_standard(
    state: WorkflowState,
    task: Task,
    updated_task: dict,
    project_dir: Path,
) -> dict[str, Any]:
    """Implement task using standard single-invocation approach via Specialist Runner.

    Args:
        state: Workflow state
        task: Task definition
        updated_task: Task with updated attempt count
        project_dir: Project directory

    Returns:
        State updates
    """
    task_id = task["id"]

    # Build prompt using scoped or full context
    prompt = build_task_prompt(task, state, project_dir)

    try:
        # Use SpecialistRunner to execute A04-implementer
        # Running in thread to avoid blocking event loop
        runner = SpecialistRunner(project_dir)
        
        result = await asyncio.to_thread(
            runner.create_agent("A04-implementer").run,
            prompt
        )

        if not result.success:
            raise Exception(result.error or "Task implementation failed")

        # Parse the raw output string into JSON
        output = _parse_task_output(result.output, task_id)

        # Check if worker needs clarification
        if output.get("status") == "needs_clarification":
            logger.info(f"Task {task_id} needs clarification")
            updated_task["status"] = TaskStatus.BLOCKED
            updated_task["error"] = f"Needs clarification: {output.get('question', 'Unknown')}"

            # Save clarification request
            _save_clarification_request(project_dir, task_id, output, state["project_name"])

            return {
                "tasks": [updated_task],
                "errors": [{
                    "type": "task_clarification_needed",
                    "task_id": task_id,
                    "question": output.get("question"),
                    "options": output.get("options", []),
                    "timestamp": datetime.now().isoformat(),
                }],
                "next_decision": "escalate",
                "updated_at": datetime.now().isoformat(),
            }

        # Task implemented - save result
        _save_task_result(project_dir, task_id, output, state["project_name"])

        # Update task with implementation notes
        updated_task["implementation_notes"] = output.get("implementation_notes", "")

        logger.info(f"Task {task_id} implementation completed")

        # Cleanup transient/session artifacts for this task
        try:
            cleanup_manager = CleanupManager(project_dir)
            cleanup_result = cleanup_manager.on_task_done(task_id)
            logger.debug(
                f"Cleanup for task {task_id}: {cleanup_result.total_deleted} items, "
                f"{cleanup_result.bytes_freed} bytes freed"
            )
        except Exception as e:
            logger.warning(f"Cleanup failed for task {task_id}: {e}")

        # Sync to Kanban board
        try:
            tasks = state.get("tasks", [])
            updated_tasks_list = [t for t in tasks if t["id"] != task_id] + [updated_task]
            sync_state = dict(state)
            sync_state["tasks"] = updated_tasks_list
            sync_board(sync_state)
        except Exception as e:
            logger.warning(f"Failed to sync board in implement task: {e}")

        return {
            "tasks": [updated_task],
            "next_decision": "continue",  # Will go to verify_task
            "updated_at": datetime.now().isoformat(),
        }

    except asyncio.TimeoutError:
        logger.error(f"Task {task_id} timed out after {TASK_TIMEOUT}s")
        return _handle_task_error(
            updated_task,
            f"Task timed out after {TASK_TIMEOUT // 60} minutes",
        )

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        return _handle_task_error(updated_task, str(e))


def _format_criteria(criteria: list[str]) -> str:
    """Format acceptance criteria as numbered list."""
    if not criteria:
        return "- No specific criteria defined"
    return "\n".join(f"- [ ] {c}" for c in criteria)


def _format_files(files: list[str]) -> str:
    """Format file list."""
    if not files:
        return "- None specified"
    return "\n".join(f"- {f}" for f in files)


def build_scoped_prompt(task: Task) -> str:
    """Build a scoped prompt with only task-relevant context.

    This creates a minimal prompt that focuses the worker on:
    - The specific task description
    - Only the files needed for this task
    - Clear instructions to avoid reading orchestration files

    Args:
        task: Task to implement

    Returns:
        Scoped prompt string
    """
    return SCOPED_TASK_PROMPT.format(
        task_id=task.get("id", "unknown"),
        description=task.get("description", task.get("title", "Unknown task")),
        acceptance_criteria="\n".join(
            f"- {c}" for c in task.get("acceptance_criteria", [])
        ) or "- No specific criteria defined",
        files_to_create="\n".join(
            f"- {f}" for f in task.get("files_to_create", [])
        ) or "- None",
        files_to_modify="\n".join(
            f"- {f}" for f in task.get("files_to_modify", [])
        ) or "- None",
        test_files="\n".join(
            f"- {f}" for f in task.get("test_files", [])
        ) or "- None",
    )


def build_full_prompt(task: Task, state: Optional[WorkflowState] = None) -> str:
    """Build a full prompt when file lists are not specified."""
    completed_context = _build_completed_context(state) if state else ""
    description = task.get("description", task.get("title", "Unknown task"))
    user_story = task.get("user_story", "No user story provided")
    dependencies = task.get("dependencies", [])

    prompt = f"""## Task
{description}

## User Story
{user_story}

## Acceptance Criteria
{_format_criteria(task.get("acceptance_criteria", []))}

## Dependencies
{_format_files(dependencies)}

## Files to Create
{_format_files(task.get("files_to_create", []))}

## Files to Modify
{_format_files(task.get("files_to_modify", []))}

## Test Files
{_format_files(task.get("test_files", []))}
"""

    if completed_context:
        prompt += f"\n{completed_context}\n"

    prompt += f"""
## Instructions
1. Implement using TDD (write/update tests first)
2. Follow existing code patterns in the project
3. Do NOT read orchestration files (.workflow/, plan.json)
4. Signal completion with: <promise>DONE</promise>

## Output
When complete, output a JSON object:
{{
    "task_id": "{task.get("id", "unknown")}",
    "status": "completed",
    "files_created": [],
    "files_modified": [],
    "tests_written": [],
    "tests_passed": true,
    "implementation_notes": "Brief notes"
}}
"""

    return prompt.strip()


def build_task_prompt(
    task: Task,
    state: Optional[WorkflowState],
    project_dir: Path,
) -> str:
    """Build a task prompt, preferring scoped context when files are listed.

    Includes CONTEXT.md preferences when available to guide implementation.
    """
    has_file_scope = bool(
        task.get("files_to_create") or task.get("files_to_modify") or task.get("test_files")
    )

    prompt = build_scoped_prompt(task) if has_file_scope else build_full_prompt(task, state)

    # Include CONTEXT.md preferences (GSD pattern)
    context_preferences = _load_context_preferences(project_dir)
    if context_preferences:
        prompt += f"\n\n## Project Context (from CONTEXT.md)\n{context_preferences}"

    # Include research findings if available
    research_findings = _load_research_findings(project_dir)
    if research_findings:
        prompt += f"\n\n## Research Findings\n{research_findings}"

    diff_context = _build_diff_context(project_dir, task)
    if diff_context:
        prompt += f"\n\n## Diff Context\n```diff\n{diff_context}\n```"

    clarification_answers = _load_task_clarification_answers(project_dir, task.get("id", "unknown"))
    if clarification_answers:
        prompt += f"\n\nCLARIFICATION ANSWERS:\n{json.dumps(clarification_answers, indent=2)}"

    return prompt


def _load_context_preferences(project_dir: Path) -> str:
    """Load developer preferences from CONTEXT.md.

    Args:
        project_dir: Project directory

    Returns:
        Formatted preferences string or empty string
    """
    context_file = project_dir / "CONTEXT.md"
    if not context_file.exists():
        return ""

    try:
        content = context_file.read_text()

        # Extract key sections
        sections_to_include = [
            "## Library Preferences",
            "## Architectural Decisions",
            "## Testing Philosophy",
            "## Code Style",
            "## Error Handling",
        ]

        extracted = []
        for section in sections_to_include:
            if section in content:
                section_start = content.find(section)
                next_section = content.find("##", section_start + len(section))
                if next_section == -1:
                    section_content = content[section_start:]
                else:
                    section_content = content[section_start:next_section]

                # Clean up section content
                section_content = section_content.strip()
                if section_content and "[TBD]" not in section_content:
                    extracted.append(section_content)

        if extracted:
            return "\n\n".join(extracted)

    except Exception as e:
        logger.warning(f"Failed to load CONTEXT.md: {e}")

    return ""


def _load_research_findings(project_dir: Path) -> str:
    """Load research findings from the research phase.

    Args:
        project_dir: Project directory

    Returns:
        Formatted research summary or empty string
    """
    findings_file = project_dir / ".workflow" / "phases" / "research" / "findings.json"
    if not findings_file.exists():
        return ""

    try:
        findings = json.loads(findings_file.read_text())

        parts = []

        # Tech stack
        tech_stack = findings.get("tech_stack")
        if tech_stack:
            languages = tech_stack.get("languages", [])
            frameworks = tech_stack.get("frameworks", [])
            if languages:
                parts.append(f"**Languages**: {', '.join(languages)}")
            if frameworks:
                fw_names = [f.get("name", str(f)) if isinstance(f, dict) else str(f) for f in frameworks]
                parts.append(f"**Frameworks**: {', '.join(fw_names)}")

        # Patterns
        patterns = findings.get("existing_patterns")
        if patterns:
            arch = patterns.get("architecture")
            if arch and arch != "unknown":
                parts.append(f"**Architecture**: {arch}")

            testing = patterns.get("testing", {})
            if testing:
                test_info = testing.get("framework") or testing.get("types")
                if test_info:
                    if isinstance(test_info, list):
                        parts.append(f"**Testing**: {', '.join(test_info)}")
                    else:
                        parts.append(f"**Testing**: {test_info}")

        if parts:
            return "\n".join(parts)

    except Exception as e:
        logger.warning(f"Failed to load research findings: {e}")

    return ""


def _build_completed_context(state: Optional[WorkflowState]) -> str:
    """Build context from completed tasks to help with continuity."""
    if not state:
        return ""

    completed_ids = set(state.get("completed_task_ids", []))
    if not completed_ids:
        return ""

    lines = ["## PREVIOUSLY COMPLETED TASKS"]
    for task in state.get("tasks", []):
        task_id = task.get("id")
        if task_id in completed_ids:
            notes = task.get("implementation_notes", "").strip()
            note_line = f" - {notes}" if notes else ""
            lines.append(f"- {task_id}: {task.get('title', 'Untitled')}{note_line}")

    return "\n".join(lines)


def _build_diff_context(project_dir: Path, task: Task, max_chars: int = 4000) -> str:
    """Build git diff context for task-relevant files."""
    import subprocess

    files = []
    for key in ("files_to_create", "files_to_modify", "test_files"):
        files.extend(task.get(key, []) or [])

    files = [f for f in files if f]
    if not files:
        return ""

    try:
        result = subprocess.run(
            ["git", "diff", "--"] + files,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return ""

        diff = result.stdout.strip()
        if not diff:
            return ""

        return diff[:max_chars]
    except Exception:
        return ""


def _run_task_in_worktree(
    worktree_path: Path,
    task: Task,
    state: Optional[WorkflowState],
) -> dict[str, Any]:
    """Run a task implementation inside a worktree."""
    runner = SpecialistRunner(worktree_path)
    prompt = build_task_prompt(task, state, worktree_path)
    result = runner.create_agent("A04-implementer").run(prompt)

    return {
        "success": result.success,
        "output": result.output or "",
        "error": result.error,
    }


def _load_task_clarification_answers(project_dir: Path, task_id: str) -> dict:
    """Load clarification answers for a specific task."""
    answers_file = project_dir / ".workflow" / "task_clarifications" / f"{task_id}_answers.json"
    if answers_file.exists():
        try:
            return json.loads(answers_file.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_clarification_request(project_dir: Path, task_id: str, request: dict, project_name: str) -> None:
    """Save clarification request to database for human review."""
    from ...db.repositories.logs import get_logs_repository, LogType
    from ...storage.async_utils import run_async

    request_data = {
        **request,
        "task_id": task_id,
        "timestamp": datetime.now().isoformat(),
    }
    repo = get_logs_repository(project_name)
    run_async(repo.save(LogType.ERROR, request_data, task_id=task_id))


def _save_task_result(project_dir: Path, task_id: str, result: dict, project_name: str) -> None:
    """Save task implementation result to database."""
    from ...db.repositories.phase_outputs import get_phase_output_repository, OutputType
    from ...storage.async_utils import run_async

    result_data = {
        **result,
        "task_id": task_id,
        "timestamp": datetime.now().isoformat(),
    }
    repo = get_phase_output_repository(project_name)
    run_async(repo.save_task_result(task_id, result_data))


def _handle_task_error(task: Task, error_message: str) -> dict[str, Any]:
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


def _parse_task_output(stdout: str, task_id: str) -> dict:
    """Parse worker output, extracting task result JSON."""
    if not stdout:
        return {"task_id": task_id, "status": "unknown", "raw_output": ""}

    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, dict):
            parsed["task_id"] = task_id
            # Validate the parsed output
            validation_result = _validate_implementer_output(parsed)
            parsed["_validation"] = validation_result
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in output
    import re
    json_pattern = rf'\{{\s*"task_id"\s*:\s*"{task_id}"[^}}]*\}}'
    match = re.search(json_pattern, stdout, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            validation_result = _validate_implementer_output(parsed)
            parsed["_validation"] = validation_result
            return parsed
        except json.JSONDecodeError:
            pass

    # Generic JSON extraction
    json_match = re.search(r"\{[\s\S]*\}", stdout)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                parsed["task_id"] = task_id
                validation_result = _validate_implementer_output(parsed)
                parsed["_validation"] = validation_result
                return parsed
        except json.JSONDecodeError:
            pass

    return {"task_id": task_id, "status": "unknown", "raw_output": stdout}


def _validate_implementer_output(output: dict) -> dict:
    """Validate implementer output against expected schema.

    Performs basic structural validation of task implementation output.
    Returns validation result with is_valid flag and any warnings/errors.

    Args:
        output: Parsed JSON output from implementer

    Returns:
        Validation result dict with keys: is_valid, warnings, errors
    """
    warnings: list[str] = []
    errors: list[str] = []

    # Required fields for a valid task completion
    required_fields = ["task_id", "status"]
    for field in required_fields:
        if field not in output:
            errors.append(f"Missing required field: {field}")

    # Status validation
    valid_statuses = ["completed", "needs_clarification", "blocked", "failed", "unknown"]
    status = output.get("status")
    if status and status not in valid_statuses:
        warnings.append(f"Unexpected status value: {status}")

    # Validate completion fields when status is 'completed'
    if status == "completed":
        completion_fields = ["files_created", "files_modified", "tests_written", "tests_passed"]
        for field in completion_fields:
            if field not in output:
                warnings.append(f"Completion field missing: {field}")

        # Check tests_passed is boolean
        tests_passed = output.get("tests_passed")
        if tests_passed is not None and not isinstance(tests_passed, bool):
            warnings.append(f"tests_passed should be boolean, got {type(tests_passed).__name__}")

        # Check file lists are arrays
        for field in ["files_created", "files_modified", "tests_written"]:
            value = output.get(field)
            if value is not None and not isinstance(value, list):
                warnings.append(f"{field} should be a list, got {type(value).__name__}")

    # Validate clarification fields when status is 'needs_clarification'
    if status == "needs_clarification":
        if "question" not in output:
            errors.append("needs_clarification status requires 'question' field")
        if "options" in output and not isinstance(output.get("options"), list):
            warnings.append("'options' should be a list")

    # Try jsonschema validation if available
    try:
        import jsonschema

        schema = _get_task_output_schema()
        if schema:
            try:
                jsonschema.validate(instance=output, schema=schema)
            except jsonschema.ValidationError as e:
                warnings.append(f"Schema validation: {e.message}")
    except ImportError:
        pass  # jsonschema not available, skip

    is_valid = len(errors) == 0

    return {
        "is_valid": is_valid,
        "warnings": warnings,
        "errors": errors,
    }


def _get_task_output_schema() -> Optional[dict]:
    """Load the task output JSON schema if available.

    Searches for task-output-schema.json in standard locations.

    Returns:
        Schema dict or None if not found
    """
    search_paths = [
        Path(__file__).parent.parent.parent / "schemas" / "task-output-schema.json",
        Path.home() / ".config" / "conductor" / "schemas" / "task-output-schema.json",
    ]

    for path in search_paths:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load schema from {path}: {e}")
                return None

    return None


def _update_task_trackers(
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
