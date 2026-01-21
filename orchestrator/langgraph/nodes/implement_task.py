"""Implement task node.

Implements a single task using worker Claude with focused scope.
Only implements the current task's acceptance criteria.
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

logger = logging.getLogger(__name__)

# Configuration
TASK_TIMEOUT = 600  # 10 minutes per task
MAX_CONCURRENT_OPERATIONS = 1  # Single writer

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


async def implement_task_node(state: WorkflowState) -> dict[str, Any]:
    """Implement the current task.

    Spawns a worker Claude to implement the single selected task
    with focused scope and TDD practices.

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
