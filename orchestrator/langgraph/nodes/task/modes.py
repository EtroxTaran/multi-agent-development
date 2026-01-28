"""Execution modes for task implementation.

Provides different strategies for implementing tasks:
- Standard: Single worker invocation
- Ralph Wiggum: Iterative loop until tests pass
- Unified: Universal loop that works with any agent
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ....cleanup import CleanupManager
from ....specialists.runner import SpecialistRunner
from ...integrations.board_sync import sync_board
from ...integrations.ralph_loop import RalphLoopConfig, detect_test_framework, run_ralph_loop
from ...integrations.unified_loop import LoopContext, UnifiedLoopConfig, UnifiedLoopRunner
from ...state import Task, TaskStatus, WorkflowState, create_agent_execution, create_error_context
from .output import parse_task_output
from .prompts import build_task_prompt
from .storage import handle_task_error, save_clarification_request, save_task_result

logger = logging.getLogger(__name__)

# Configuration constants
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

# Fallback model configuration
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "haiku")


def should_use_ralph_loop(task: Task, project_dir: Path) -> bool:
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


def should_use_unified_loop(task: Task, project_dir: Path) -> bool:
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


def get_unified_loop_config(
    task: Task,
    project_dir: Path,
    use_fallback_model: bool = False,
    fallback_model: Optional[str] = None,
) -> UnifiedLoopConfig:
    """Get unified loop configuration for a task.

    Args:
        task: Task to implement
        project_dir: Project directory
        use_fallback_model: Whether to use fallback model due to budget constraints
        fallback_model: Name of fallback model to use (e.g., 'haiku')

    Returns:
        Configured UnifiedLoopConfig
    """
    # Determine agent type
    agent_type = LOOP_AGENT
    if task.get("agent_type"):
        agent_type = task.get("agent_type")
    elif task.get("primary_cli"):
        agent_type = task.get("primary_cli")

    # Determine model - use fallback if budget constrained
    if use_fallback_model and fallback_model:
        model = fallback_model
        logger.info(f"Using fallback model '{model}' for unified loop due to budget constraints")
    else:
        task_model = task.get("model")
        model = str(task_model) if task_model else (LOOP_MODEL or "opus")

    # Determine verification type
    verification = "tests"
    if task.get("test_files"):
        verification = "tests"
    elif task.get("verification"):
        verification = task.get("verification")

    # Adjust budget per iteration based on model
    budget_per_iteration = 0.05 if use_fallback_model else 0.50
    max_budget = 0.50 if use_fallback_model else 5.00

    return UnifiedLoopConfig(
        agent_type=agent_type,
        model=model,
        max_iterations=10,
        iteration_timeout=300,
        verification=verification,
        enable_session=(agent_type.lower() == "claude"),
        enable_error_context=True,
        enable_budget=True,
        budget_per_iteration=budget_per_iteration,
        max_budget=max_budget,
        save_iteration_logs=True,
    )


async def implement_with_ralph_loop(
    state: WorkflowState,
    task: Task,
    updated_task: dict,
    project_dir: Path,
    use_fallback_model: bool = False,
    fallback_model: Optional[str] = None,
) -> dict[str, Any]:
    """Implement task using Ralph Wiggum iterative loop.

    Runs Claude in a loop until all tests pass, with fresh context
    each iteration to avoid degradation.

    Args:
        state: Workflow state
        task: Task definition
        updated_task: Task with updated attempt count
        project_dir: Project directory
        use_fallback_model: Whether to use fallback model due to budget constraints
        fallback_model: Name of fallback model to use (e.g., 'haiku')

    Returns:
        State updates
    """
    task_id = task["id"]

    # Configure Ralph loop
    test_command = detect_test_framework(project_dir)

    # Adjust budget per iteration if using fallback model
    budget_per_iteration = 0.50 if not use_fallback_model else 0.05

    config = RalphLoopConfig(
        max_iterations=10,
        iteration_timeout=300,  # 5 min per iteration
        test_command=test_command,
        save_iteration_logs=True,
        model=fallback_model if use_fallback_model else None,
        budget_per_iteration=budget_per_iteration,
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
            save_task_result(
                project_dir,
                task_id,
                {
                    "status": "completed",
                    "implementation_mode": "ralph_wiggum",
                    "iterations": result.iterations,
                    "total_time_seconds": result.total_time_seconds,
                    "completion_reason": result.completion_reason,
                    **(result.final_output or {}),
                },
                state["project_name"],
            )

            updated_task["implementation_notes"] = (
                f"Completed via Ralph loop in {result.iterations} iteration(s). "
                f"Reason: {result.completion_reason}"
            )

            logger.info(
                f"Task {task_id} completed via Ralph loop " f"in {result.iterations} iterations"
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
            logger.warning(f"Ralph loop failed for task {task_id}: {result.error}")
            return handle_task_error(  # type: ignore[no-any-return]
                updated_task,
                f"Ralph loop failed after {result.iterations} iterations: {result.error}",
            )

    except asyncio.TimeoutError:
        logger.error(f"Ralph loop for task {task_id} timed out")
        return handle_task_error(  # type: ignore[no-any-return]
            updated_task,
            f"Ralph loop timed out after {RALPH_TIMEOUT // 60} minutes",
        )
    except Exception as e:
        logger.error(f"Ralph loop for task {task_id} failed: {e}")
        return handle_task_error(updated_task, str(e))  # type: ignore[no-any-return]


async def implement_with_unified_loop(
    state: WorkflowState,
    task: Task,
    updated_task: dict,
    project_dir: Path,
    use_fallback_model: bool = False,
    fallback_model: Optional[str] = None,
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
        use_fallback_model: Whether to use fallback model due to budget constraints
        fallback_model: Name of fallback model to use (e.g., 'haiku')

    Returns:
        State updates
    """
    task_id = task["id"]

    # Get unified loop configuration with fallback model support
    config = get_unified_loop_config(task, project_dir, use_fallback_model, fallback_model)

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
            save_task_result(
                project_dir,
                task_id,
                {
                    "status": "completed",
                    "implementation_mode": "unified_loop",
                    "agent_type": result.agent_type,
                    "model": result.model,
                    "iterations": result.iterations,
                    "total_time_seconds": result.total_time_seconds,
                    "total_cost_usd": result.total_cost_usd,
                    "completion_reason": result.completion_reason,
                    **(result.final_output or {}),
                },
                state["project_name"],
            )

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
            logger.warning(f"Unified loop failed for task {task_id}: {result.error}")
            return handle_task_error(  # type: ignore[no-any-return]
                updated_task,
                f"Unified loop failed after {result.iterations} iterations "
                f"({result.agent_type}): {result.error}",
            )

    except asyncio.TimeoutError:
        logger.error(f"Unified loop for task {task_id} timed out")
        return handle_task_error(  # type: ignore[no-any-return]
            updated_task,
            f"Unified loop timed out after {RALPH_TIMEOUT // 60} minutes",
        )
    except Exception as e:
        logger.error(f"Unified loop for task {task_id} failed: {e}")
        return handle_task_error(updated_task, str(e))  # type: ignore[no-any-return]


async def implement_standard(
    state: WorkflowState,
    task: Task,
    updated_task: dict,
    project_dir: Path,
    use_fallback_model: bool = False,
    fallback_model: Optional[str] = None,
) -> dict[str, Any]:
    """Implement task using standard single-invocation approach via Specialist Runner.

    Args:
        state: Workflow state
        task: Task definition
        updated_task: Task with updated attempt count
        project_dir: Project directory
        use_fallback_model: Whether to use fallback model due to budget constraints
        fallback_model: Name of fallback model to use (e.g., 'haiku')

    Returns:
        State updates
    """
    task_id = task["id"]
    start_time = time.time()

    # Build prompt using scoped or full context
    prompt = build_task_prompt(task, state, project_dir)
    model_used = fallback_model if use_fallback_model else "claude"

    try:
        # Use SpecialistRunner to execute A04-implementer
        # Running in thread to avoid blocking event loop
        runner = SpecialistRunner(project_dir)

        # Check if agents/ directory exists for specialist agents
        if runner.has_agents_dir():
            # Use specialist agent A04-implementer
            agent = runner.create_agent("A04-implementer")
            if use_fallback_model and fallback_model:
                logger.info(f"Using fallback model '{fallback_model}' for standard implementation")
                agent.model = fallback_model
                model_used = fallback_model
        else:
            # Fall back to direct ClaudeAgent invocation
            logger.info("Agents directory not found, using direct ClaudeAgent for implementation")
            from ....agents.claude_agent import ClaudeAgent

            agent = ClaudeAgent(
                project_dir,
                allowed_tools=[
                    "Read",
                    "Write",
                    "Edit",
                    "Glob",
                    "Grep",
                    "Bash(npm*)",
                    "Bash(pytest*)",
                    "Bash(npx*)",
                    "Bash(git*)",
                ],
            )
            if use_fallback_model and fallback_model:
                logger.info(f"Using fallback model '{fallback_model}' for standard implementation")
                # ClaudeAgent doesn't have a model attribute, but we track it for logging
                model_used = fallback_model

        result = await asyncio.to_thread(agent.run, prompt)

        if not result.success:
            raise Exception(result.error or "Task implementation failed")

        # Parse the raw output string into JSON
        output = parse_task_output(result.output, task_id)

        # Track successful agent execution
        execution = create_agent_execution(
            agent="claude",
            node="implement_task",
            template_name="task_implementation",
            prompt=prompt[:5000],
            output=result.output[:10000] if result.output else "",
            success=True,
            exit_code=0,
            duration_seconds=(time.time() - start_time),
            model=model_used,
            task_id=task_id,
        )

        # Check if worker needs clarification
        if output.get("status") == "needs_clarification":
            logger.info(f"Task {task_id} needs clarification")
            updated_task["status"] = TaskStatus.BLOCKED
            updated_task["error"] = f"Needs clarification: {output.get('question', 'Unknown')}"

            # Save clarification request
            save_clarification_request(project_dir, task_id, output, state["project_name"])

            return {
                "tasks": [updated_task],
                "errors": [
                    {
                        "type": "task_clarification_needed",
                        "task_id": task_id,
                        "question": output.get("question"),
                        "options": output.get("options", []),
                        "timestamp": datetime.now().isoformat(),
                    }
                ],
                "next_decision": "escalate",
                "updated_at": datetime.now().isoformat(),
                "last_agent_execution": execution,
                "execution_history": [execution],
            }

        # Task implemented - save result
        save_task_result(project_dir, task_id, output, state["project_name"])

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
            "last_agent_execution": execution,
            "execution_history": [execution],
        }

    except asyncio.TimeoutError:
        logger.error(f"Task {task_id} timed out after {TASK_TIMEOUT}s")

        # Create error context for timeout
        timeout_error = TimeoutError(f"Task timed out after {TASK_TIMEOUT // 60} minutes")
        error_context = create_error_context(
            source_node="implement_task",
            exception=timeout_error,
            state=dict(state),
            recoverable=True,
        )

        # Track failed execution
        failed_execution = create_agent_execution(
            agent="claude",
            node="implement_task",
            template_name="task_implementation",
            prompt=prompt[:5000],
            output="Timeout",
            success=False,
            exit_code=1,
            duration_seconds=(time.time() - start_time),
            model=model_used,
            task_id=task_id,
            error_context=error_context,
        )

        error_result: dict[str, Any] = handle_task_error(
            updated_task,
            f"Task timed out after {TASK_TIMEOUT // 60} minutes",
        )
        error_result["error_context"] = error_context
        error_result["last_agent_execution"] = failed_execution
        error_result["execution_history"] = [failed_execution]
        return error_result

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")

        # Create error context
        error_context = create_error_context(
            source_node="implement_task",
            exception=e,
            state=dict(state),
            recoverable=True,
        )

        # Track failed execution
        failed_execution = create_agent_execution(
            agent="claude",
            node="implement_task",
            template_name="task_implementation",
            prompt=prompt[:5000],
            output=str(e),
            success=False,
            exit_code=1,
            duration_seconds=(time.time() - start_time),
            model=model_used,
            task_id=task_id,
            error_context=error_context,
        )

        error_result = handle_task_error(updated_task, str(e))
        error_result["error_context"] = error_context
        error_result["last_agent_execution"] = failed_execution
        error_result["execution_history"] = [failed_execution]
        return error_result  # type: ignore[no-any-return]
