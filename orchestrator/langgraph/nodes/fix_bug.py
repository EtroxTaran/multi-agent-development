"""Fix bug node.

Uses A05-bug-fixer to analyze errors and apply targeted fixes
when verification or implementation fails.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ...specialists.runner import SpecialistRunner
from ..integrations.board_sync import sync_board
from ..state import WorkflowState, get_task_by_id

logger = logging.getLogger(__name__)


async def fix_bug_node(state: WorkflowState) -> dict[str, Any]:
    """Analyze and fix bugs for the current task.

    Args:
        state: Current workflow state

    Returns:
        State updates with fix result
    """
    task_id = state.get("current_task_id")
    if not task_id:
        return {
            "errors": [
                {
                    "type": "fix_bug_error",
                    "message": "No task selected for bug fixing",
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "escalate",
        }

    task = get_task_by_id(state, task_id)
    if not task:
        return {
            "errors": [
                {
                    "type": "fix_bug_error",
                    "message": f"Task {task_id} not found",
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "escalate",
        }

    # Get the last error to analyze
    errors = state.get("errors", [])
    last_error = errors[-1] if errors else None
    error_context = ""
    if last_error:
        error_context = f"ERROR TO FIX:\n{json.dumps(last_error, indent=2)}"
    elif task.get("error"):
        error_context = f"ERROR TO FIX:\n{task.get('error')}"

    logger.info(f"Fixing bugs for task: {task_id}")
    project_dir = Path(state["project_dir"])

    # Update attempt count
    updated_task = dict(task)
    updated_task["attempts"] = updated_task.get("attempts", 0) + 1

    # Build prompt for A05
    prompt = f"""TASK: {task_id}
TITLE: {task.get('title')}

FILES INVOLVED:
{_format_list(task.get('files_to_create', []) + task.get('files_to_modify', []))}

TEST FILES:
{_format_list(task.get('test_files', []))}

{error_context}

Please analyze the error and fix the code to make tests pass.
"""

    try:
        runner = SpecialistRunner(project_dir)

        # Run A05-bug-fixer
        result = await asyncio.to_thread(runner.create_agent("A05-bug-fixer").run, prompt)

        if not result.success:
            raise Exception(result.error or "Bug fixing failed")

        output = _parse_output(result.output)

        updated_task["implementation_notes"] = (
            updated_task.get("implementation_notes", "")
            + f"\nBug fix applied: {output.get('fix_applied', 'See code changes')}"
        )

        # Sync to board
        try:
            tasks = state.get("tasks", [])
            updated_tasks_list = [t for t in tasks if t["id"] != task_id] + [updated_task]
            sync_state = dict(state)
            sync_state["tasks"] = updated_tasks_list
            sync_board(sync_state)
        except Exception as e:
            logger.warning(f"Failed to sync board in fix bug: {e}")

        return {
            "tasks": [updated_task],
            "next_decision": "continue",  # Retry verification
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Bug fixing failed: {e}")
        return {
            "errors": [
                {
                    "type": "bug_fixing_failed",
                    "task_id": task_id,
                    "message": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "escalate",
        }


def _format_list(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {i}" for i in items)


def _parse_output(stdout: str) -> dict:
    """Parse JSON output from agent."""
    try:
        if not stdout:
            return {{}}
        # Try finding JSON block
        import re

        json_match = re.search(r"{{[\s\S]*}}", stdout)
        if json_match:
            return json.loads(json_match.group(0))
        return {{}}
    except Exception:
        return {{}}
