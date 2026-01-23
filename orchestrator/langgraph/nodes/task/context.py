"""Context loading for task implementation.

Loads developer preferences and research findings to inform implementation.
"""

import logging
from pathlib import Path
from typing import Optional

from ...state import Task, WorkflowState

logger = logging.getLogger(__name__)


def load_context_preferences(project_dir: Path) -> str:
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


def load_research_findings(project_name: str) -> str:
    """Load research findings from database.

    Args:
        project_name: Project name for DB lookup

    Returns:
        Formatted research summary or empty string
    """
    from ....db.repositories.logs import get_logs_repository
    from ....storage.async_utils import run_async

    try:
        repo = get_logs_repository(project_name)
        logs = run_async(repo.get_by_type("research_aggregated"))

        if not logs:
            return ""

        # Get most recent research
        latest = logs[0]
        findings = latest.get("content", {})

        parts = []

        # Tech stack
        tech_stack = findings.get("tech_stack")
        if tech_stack:
            languages = tech_stack.get("languages", [])
            frameworks = tech_stack.get("frameworks", [])
            if languages:
                parts.append(f"**Languages**: {', '.join(languages)}")
            if frameworks:
                fw_names = [
                    f.get("name", str(f)) if isinstance(f, dict) else str(f) for f in frameworks
                ]
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


def build_completed_context(state: Optional[WorkflowState]) -> str:
    """Build context from completed tasks to help with continuity.

    Args:
        state: Workflow state

    Returns:
        Context string with previously completed tasks
    """
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


def build_diff_context(project_dir: Path, task: Task, max_chars: int = 4000) -> str:
    """Build git diff context for task-relevant files.

    Args:
        project_dir: Project directory
        task: Task to get diff context for
        max_chars: Maximum characters to return

    Returns:
        Diff string or empty string
    """
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


def load_task_clarification_answers(project_name: str, task_id: str) -> dict:
    """Load clarification answers for a specific task from database.

    Args:
        project_name: Project name for DB lookup
        task_id: Task ID to get answers for

    Returns:
        Clarification answers dict or empty dict
    """
    from ....db.repositories.logs import get_logs_repository
    from ....storage.async_utils import run_async

    try:
        repo = get_logs_repository(project_name)
        # Look for clarification answers stored as error type with task_id
        logs = run_async(repo.get_by_task_id(task_id))

        for log in logs:
            content = log.get("content", {})
            if content.get("type") == "clarification_answers":
                return content.get("answers", {})
    except Exception:
        pass

    return {}
