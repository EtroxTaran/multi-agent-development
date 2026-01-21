"""Implement task node.

Implements a single task using worker Claude with focused scope.
Only implements the current task's acceptance criteria.

Supports two execution modes:
1. Standard: Single worker invocation with TDD prompt
2. Ralph Wiggum: Iterative loop until tests pass (fresh context each iteration)

Ralph Wiggum mode is recommended when tests already exist (TDD workflow).
"""

import asyncio
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
    get_task_by_id,
)
from ..integrations.ralph_loop import (
    RalphLoopConfig,
    run_ralph_loop,
    detect_test_framework,
)
from ..integrations import (
    create_linear_adapter,
    load_issue_mapping,
    create_markdown_tracker,
)

logger = logging.getLogger(__name__)

# Configuration
TASK_TIMEOUT = 600  # 10 minutes per task (standard mode)
RALPH_TIMEOUT = 1800  # 30 minutes total for Ralph loop
MAX_CONCURRENT_OPERATIONS = 1  # Single writer

# Environment variable to enable Ralph Wiggum mode
USE_RALPH_LOOP = os.environ.get("USE_RALPH_LOOP", "auto")  # "auto", "true", "false"

TASK_IMPLEMENTATION_PROMPT = """You are implementing a SINGLE task as part of a larger feature.

TASK: {task_id} - {title}

USER STORY:
{user_story}

ACCEPTANCE CRITERIA FOR THIS TASK:
{acceptance_criteria}

FILES TO CREATE:
{files_to_create}

FILES TO MODIFY:
{files_to_modify}

TEST FILES:
{test_files}

{completed_context}

INSTRUCTIONS:
1. Focus ONLY on this specific task - do not implement other features
2. Write tests FIRST (TDD approach)
3. Implement the minimal code to make tests pass
4. Follow existing code patterns in the project

OUTPUT FORMAT:
Return a JSON object with your implementation result:
{{
    "task_id": "{task_id}",
    "status": "completed",
    "files_created": ["list of new files"],
    "files_modified": ["list of modified files"],
    "tests_written": ["list of test files"],
    "tests_passed": true,
    "implementation_notes": "Brief notes on what was implemented"
}}

IF YOU NEED CLARIFICATION:
If you encounter something unclear, output:
{{
    "task_id": "{task_id}",
    "status": "needs_clarification",
    "question": "Specific question",
    "context": "What you've tried",
    "options": ["Option A", "Option B"],
    "recommendation": "Your recommended approach"
}}
Then STOP and wait for human input.

DO NOT implement anything beyond this task's scope.
"""

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

    # Update task attempt count
    updated_task = dict(task)
    updated_task["attempts"] = updated_task.get("attempts", 0) + 1
    updated_task["status"] = TaskStatus.IN_PROGRESS

    # Update task status in trackers
    _update_task_trackers(project_dir, task_id, TaskStatus.IN_PROGRESS)

    # Decide which execution mode to use
    use_ralph = _should_use_ralph_loop(task, project_dir)

    if use_ralph:
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
            })

            updated_task["implementation_notes"] = (
                f"Completed via Ralph loop in {result.iterations} iteration(s). "
                f"Reason: {result.completion_reason}"
            )

            logger.info(
                f"Task {task_id} completed via Ralph loop "
                f"in {result.iterations} iterations"
            )

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


async def _implement_standard(
    state: WorkflowState,
    task: Task,
    updated_task: dict,
    project_dir: Path,
) -> dict[str, Any]:
    """Implement task using standard single-invocation approach.

    Args:
        state: Workflow state
        task: Task definition
        updated_task: Task with updated attempt count
        project_dir: Project directory

    Returns:
        State updates
    """
    task_id = task["id"]

    # Build completed tasks context
    completed_context = _build_completed_context(state)

    # Build the prompt
    prompt = TASK_IMPLEMENTATION_PROMPT.format(
        task_id=task_id,
        title=task.get("title", ""),
        user_story=task.get("user_story", ""),
        acceptance_criteria=_format_criteria(task.get("acceptance_criteria", [])),
        files_to_create=_format_files(task.get("files_to_create", [])),
        files_to_modify=_format_files(task.get("files_to_modify", [])),
        test_files=_format_files(task.get("test_files", [])),
        completed_context=completed_context,
    )

    # Load any clarification answers
    clarification_answers = _load_task_clarification_answers(project_dir, task_id)
    if clarification_answers:
        prompt += f"\n\nCLARIFICATION ANSWERS:\n{json.dumps(clarification_answers, indent=2)}"

    try:
        # Spawn worker Claude with timeout
        result = await asyncio.wait_for(
            _run_task_worker(project_dir, prompt, task_id),
            timeout=TASK_TIMEOUT,
        )

        if not result["success"]:
            raise Exception(result.get("error", "Task implementation failed"))

        output = result.get("output", {})

        # Check if worker needs clarification
        if output.get("status") == "needs_clarification":
            logger.info(f"Task {task_id} needs clarification")
            updated_task["status"] = TaskStatus.BLOCKED
            updated_task["error"] = f"Needs clarification: {output.get('question', 'Unknown')}"

            # Save clarification request
            _save_clarification_request(project_dir, task_id, output)

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
        _save_task_result(project_dir, task_id, output)

        # Update task with implementation notes
        updated_task["implementation_notes"] = output.get("implementation_notes", "")

        logger.info(f"Task {task_id} implementation completed")

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


def _build_completed_context(state: WorkflowState) -> str:
    """Build context from previously completed tasks.

    Args:
        state: Current workflow state

    Returns:
        Context string for prompt
    """
    completed_ids = state.get("completed_task_ids", [])
    if not completed_ids:
        return ""

    tasks = state.get("tasks", [])
    completed_tasks = [t for t in tasks if t.get("id") in completed_ids]

    if not completed_tasks:
        return ""

    context_lines = ["PREVIOUSLY COMPLETED TASKS:"]
    for task in completed_tasks[:5]:  # Limit to last 5 for context
        context_lines.append(f"- {task.get('id')}: {task.get('title', 'Unknown')}")
        if task.get("implementation_notes"):
            context_lines.append(f"  Notes: {task.get('implementation_notes')}")

    return "\n".join(context_lines)


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


def _load_task_clarification_answers(project_dir: Path, task_id: str) -> dict:
    """Load clarification answers for a specific task."""
    answers_file = project_dir / ".workflow" / "task_clarifications" / f"{task_id}_answers.json"
    if answers_file.exists():
        try:
            return json.loads(answers_file.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_clarification_request(project_dir: Path, task_id: str, request: dict) -> None:
    """Save clarification request for human review."""
    clarification_dir = project_dir / ".workflow" / "task_clarifications"
    clarification_dir.mkdir(parents=True, exist_ok=True)

    request_file = clarification_dir / f"{task_id}_request.json"
    request_data = {
        **request,
        "task_id": task_id,
        "timestamp": datetime.now().isoformat(),
    }
    request_file.write_text(json.dumps(request_data, indent=2))


def _save_task_result(project_dir: Path, task_id: str, result: dict) -> None:
    """Save task implementation result."""
    results_dir = project_dir / ".workflow" / "phases" / "task_implementation"
    results_dir.mkdir(parents=True, exist_ok=True)

    result_file = results_dir / f"{task_id}_result.json"
    result_data = {
        **result,
        "task_id": task_id,
        "timestamp": datetime.now().isoformat(),
    }
    result_file.write_text(json.dumps(result_data, indent=2))


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


async def _run_task_worker(
    project_dir: Path,
    prompt: str,
    task_id: str,
) -> dict:
    """Run worker Claude for a single task.

    Args:
        project_dir: Project directory
        prompt: Task prompt
        task_id: Task identifier

    Returns:
        Result dict with success flag and output
    """
    allowed_tools = ",".join([
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "Bash(npm*)",
        "Bash(pytest*)",
        "Bash(python*)",
        "Bash(pnpm*)",
        "Bash(yarn*)",
        "Bash(bun*)",
        "Bash(cargo*)",
        "Bash(go*)",
    ])

    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--allowedTools",
        allowed_tools,
        "--max-turns",
        "20",  # Fewer turns for single task
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "TERM": "dumb"},
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return {
                "success": False,
                "error": stderr.decode() if stderr else f"Exit code: {process.returncode}",
            }

        output = _parse_task_output(stdout.decode() if stdout else "", task_id)

        return {
            "success": True,
            "output": output,
        }

    except FileNotFoundError:
        return {
            "success": False,
            "error": "Claude CLI not found. Ensure 'claude' is installed and in PATH.",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def _parse_task_output(stdout: str, task_id: str) -> dict:
    """Parse worker output, extracting task result JSON."""
    if not stdout:
        return {"task_id": task_id, "status": "unknown", "raw_output": ""}

    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, dict):
            parsed["task_id"] = task_id
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in output
    import re
    json_pattern = rf'\{{\s*"task_id"\s*:\s*"{task_id}"[^}}]*\}}'
    match = re.search(json_pattern, stdout, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Generic JSON extraction
    json_match = re.search(r"\{[\s\S]*\}", stdout)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                parsed["task_id"] = task_id
                return parsed
        except json.JSONDecodeError:
            pass

    return {"task_id": task_id, "status": "unknown", "raw_output": stdout}


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
