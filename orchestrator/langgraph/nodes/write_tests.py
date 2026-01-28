"""Write tests node.

Uses A03-test-writer to create failing tests before implementation (TDD).
Falls back to direct ClaudeAgent invocation when agents/ directory doesn't exist.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ...agents.claude_agent import ClaudeAgent
from ...specialists.runner import SpecialistRunner
from ..integrations.board_sync import sync_board
from ..state import WorkflowState, get_task_by_id

logger = logging.getLogger(__name__)


# Fallback prompt for test writing when agents/ directory doesn't exist
TEST_WRITER_PROMPT = """You are a TDD Test Writer. Write failing tests for this task BEFORE implementation.

{task_context}

## Instructions

1. Analyze the task requirements and acceptance criteria
2. Create test files that will FAIL initially (TDD red phase)
3. Tests should cover:
   - Happy path scenarios
   - Edge cases
   - Error conditions
   - Each acceptance criterion

4. Use the appropriate test framework for the project:
   - Python: pytest
   - TypeScript/JavaScript: jest, vitest, or playwright
   - Go: testing package

5. Output JSON with:
```json
{{
  "tests_written": ["path/to/test1.ts", "path/to/test2.ts"],
  "test_count": 5,
  "coverage_targets": ["function1", "function2"],
  "notes": "Brief notes about tests"
}}
```

Write the tests now.
"""


async def write_tests_node(state: WorkflowState) -> dict[str, Any]:
    """Write failing tests for the current task.

    Args:
        state: Current workflow state

    Returns:
        State updates with test creation result
    """
    task_id = state.get("current_task_id")
    if not task_id:
        return {
            "errors": [
                {
                    "type": "write_tests_error",
                    "message": "No task selected for test writing",
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
                    "type": "write_tests_error",
                    "message": f"Task {task_id} not found",
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "escalate",
        }

    # Check if tests are already defined/written or if task type requires it
    # For now, we assume all implementation tasks need tests unless explicit
    # refactoring tasks might use existing tests.

    # If test files already exist and we are retrying, we might skip or update.
    # But A03's job is to ensure they exist and fail.

    logger.info(f"Writing tests for task: {task_id} - {task.get('title', 'Unknown')}")
    project_dir = Path(state["project_dir"])

    # Build prompt for A03
    # A03 needs: User Story, Acceptance Criteria, Files info
    prompt = f"""TASK: {task_id}
TITLE: {task.get('title')}
USER STORY: {task.get('user_story')}

ACCEPTANCE CRITERIA:
{_format_list(task.get('acceptance_criteria', []))}

FILES TO CREATE:
{_format_list(task.get('files_to_create', []))}

FILES TO MODIFY:
{_format_list(task.get('files_to_modify', []))}

EXISTING TEST FILES:
{_format_list(task.get('test_files', []))}
"""

    try:
        runner = SpecialistRunner(project_dir)

        # Check if agents/ directory exists for specialist agents
        if runner.has_agents_dir():
            # Use specialist agent A03-test-writer
            result = await asyncio.to_thread(runner.create_agent("A03-test-writer").run, prompt)
        else:
            # Fall back to direct ClaudeAgent invocation
            logger.info("Agents directory not found, using direct ClaudeAgent for test writing")
            task_context = prompt  # The prompt we built above serves as context
            full_prompt = TEST_WRITER_PROMPT.format(task_context=task_context)

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
                ],
            )
            result = await asyncio.to_thread(agent.run, full_prompt)

        if not result.success:
            raise Exception(result.error or "Test writing failed")

        output = _parse_output(result.output)

        # Update task with new test files if any
        updated_task = dict(task)
        tests_written = output.get("tests_written", [])
        if tests_written:
            current_tests = set(updated_task.get("test_files", []))
            current_tests.update(tests_written)
            updated_task["test_files"] = list(current_tests)
            logger.info(f"Updated task {task_id} with tests: {tests_written}")

        # Sync to board
        try:
            tasks = state.get("tasks", [])
            updated_tasks_list = [t for t in tasks if t["id"] != task_id] + [updated_task]
            sync_state = dict(state)
            sync_state["tasks"] = updated_tasks_list
            sync_board(sync_state)
        except Exception as e:
            logger.warning(f"Failed to sync board in write tests: {e}")

        return {
            "tasks": [updated_task],
            "next_decision": "continue",  # Move to implement_task
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Test writing failed: {e}")
        return {
            "errors": [
                {
                    "type": "test_writing_failed",
                    "task_id": task_id,
                    "message": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "escalate",  # Or maybe skip to implementation? No, TDD requires tests.
        }


def _format_list(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {i}" for i in items)


def _parse_output(stdout: str) -> dict[str, Any]:
    """Parse JSON output from agent."""
    try:
        if not stdout:
            return {}
        # Try finding JSON block
        import re

        json_match = re.search(r"{[\s\S]*}", stdout)
        if json_match:
            result = json.loads(json_match.group(0))
            return result if isinstance(result, dict) else {}
        return {}
    except Exception:
        return {}
