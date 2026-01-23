"""Prompt building for task implementation.

Builds focused prompts for worker Claude with appropriate context.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ...state import WorkflowState, Task
from ....agents.prompts import load_prompt, format_prompt
from .context import (
    load_context_preferences,
    load_research_findings,
    build_completed_context,
    build_diff_context,
    load_task_clarification_answers,
)

logger = logging.getLogger(__name__)

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


def format_criteria(criteria: list[str]) -> str:
    """Format acceptance criteria as numbered list.

    Args:
        criteria: List of acceptance criteria

    Returns:
        Formatted string
    """
    if not criteria:
        return "- No specific criteria defined"
    return "\n".join(f"- [ ] {c}" for c in criteria)


def format_files(files: list[str]) -> str:
    """Format file list.

    Args:
        files: List of file paths

    Returns:
        Formatted string
    """
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
    task_id = task.get("id", "unknown")
    title = task.get("title", "Unknown task")
    description = task.get("description", title)
    acceptance_criteria = task.get("acceptance_criteria", [])
    files_to_create = task.get("files_to_create", [])
    files_to_modify = task.get("files_to_modify", [])
    test_files = task.get("test_files", [])

    # Try to load external template with fallback to inline
    try:
        template = load_prompt("claude", "task")
        prompt = format_prompt(
            template,
            task_id=task_id,
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria or ["No specific criteria defined"],
            files_to_create=files_to_create or ["None"],
            files_to_modify=files_to_modify or ["None"],
            test_files=test_files or ["None"],
        )
        logger.debug("Using external task template")
        return prompt
    except FileNotFoundError:
        logger.debug("Task template not found, using inline prompt")
        return SCOPED_TASK_PROMPT.format(
            task_id=task_id,
            description=description,
            acceptance_criteria="\n".join(
                f"- {c}" for c in acceptance_criteria
            ) or "- No specific criteria defined",
            files_to_create="\n".join(
                f"- {f}" for f in files_to_create
            ) or "- None",
            files_to_modify="\n".join(
                f"- {f}" for f in files_to_modify
            ) or "- None",
            test_files="\n".join(
                f"- {f}" for f in test_files
            ) or "- None",
        )


def build_full_prompt(task: Task, state: Optional[WorkflowState] = None) -> str:
    """Build a full prompt when file lists are not specified.

    Args:
        task: Task to implement
        state: Optional workflow state for context

    Returns:
        Full prompt string
    """
    completed_context = build_completed_context(state) if state else ""
    description = task.get("description", task.get("title", "Unknown task"))
    user_story = task.get("user_story", "No user story provided")
    dependencies = task.get("dependencies", [])

    prompt = f"""## Task
{description}

## User Story
{user_story}

## Acceptance Criteria
{format_criteria(task.get("acceptance_criteria", []))}

## Dependencies
{format_files(dependencies)}

## Files to Create
{format_files(task.get("files_to_create", []))}

## Files to Modify
{format_files(task.get("files_to_modify", []))}

## Test Files
{format_files(task.get("test_files", []))}
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

    Args:
        task: Task to implement
        state: Optional workflow state
        project_dir: Project directory

    Returns:
        Complete prompt string
    """
    has_file_scope = bool(
        task.get("files_to_create") or task.get("files_to_modify") or task.get("test_files")
    )

    prompt = build_scoped_prompt(task) if has_file_scope else build_full_prompt(task, state)

    # Check for correction prompt from failed verification (Phase 4 retry)
    if state:
        correction_prompt = state.get("correction_prompt")
        if correction_prompt:
            prompt = f"{correction_prompt}\n\n---\n\n{prompt}"
            logger.info(f"Task {task.get('id')} prompt includes correction context from failed verification")

    # Include CONTEXT.md preferences (GSD pattern)
    context_preferences = load_context_preferences(project_dir)
    if context_preferences:
        prompt += f"\n\n## Project Context (from CONTEXT.md)\n{context_preferences}"

    # Include research findings if available (from DB)
    project_name = state.get("project_name") if state else project_dir.name
    research_findings = load_research_findings(project_name)
    if research_findings:
        prompt += f"\n\n## Research Findings\n{research_findings}"

    diff_context = build_diff_context(project_dir, task)
    if diff_context:
        prompt += f"\n\n## Diff Context\n```diff\n{diff_context}\n```"

    clarification_answers = load_task_clarification_answers(project_name, task.get("id", "unknown"))
    if clarification_answers:
        prompt += f"\n\nCLARIFICATION ANSWERS:\n{json.dumps(clarification_answers, indent=2)}"

    return prompt
