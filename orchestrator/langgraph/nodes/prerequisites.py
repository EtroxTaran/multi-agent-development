"""Prerequisites check node.

Validates that all required files and tools are available
before starting the workflow.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def prerequisites_node(state: WorkflowState) -> dict[str, Any]:
    """Check prerequisites before starting workflow.

    Validates:
    - docs/ folder exists with documentation
    - Required CLI tools are available (or SDK keys are set)
    - Project directory structure is valid

    Args:
        state: Current workflow state

    Returns:
        State updates with prerequisite check results
    """
    logger.info(f"Checking prerequisites for project: {state['project_name']}")

    project_dir = Path(state["project_dir"])
    errors = []

    # Check for docs/ folder with documentation
    doc_dirs = ["docs", "Docs", "DOCS"]
    has_docs_folder = False

    for d in doc_dirs:
        folder = project_dir / d
        if folder.exists() and folder.is_dir():
            # Check if folder has any markdown files (recursively)
            md_files = list(folder.rglob("*.md"))
            if md_files:
                has_docs_folder = True
                logger.info(f"Found docs folder with {len(md_files)} markdown files")
                break

    if not has_docs_folder:
        errors.append(
            {
                "type": "missing_documentation",
                "file": "docs/",
                "message": (
                    "No docs/ folder found. Please create a docs/ folder with:\n"
                    "- Product vision and requirements (e.g., docs/product/overview.md)\n"
                    "- Architecture documentation (e.g., docs/design/architecture.md)"
                ),
                "timestamp": datetime.now().isoformat(),
            }
        )

    # Check for workflow directory
    workflow_dir = project_dir / ".workflow"
    if not workflow_dir.exists():
        workflow_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created workflow directory: {workflow_dir}")

    # Check CLI agent availability
    from ...agents import ClaudeAgent, CursorAgent, GeminiAgent

    claude_cli = ClaudeAgent(project_dir)
    cursor_cli = CursorAgent(project_dir)
    gemini_cli = GeminiAgent(project_dir)

    agents_available = {
        "claude_cli": claude_cli.check_available(),
        "cursor_cli": cursor_cli.check_available(),
        "gemini_cli": gemini_cli.check_available(),
    }

    # Determine if we can proceed
    can_proceed = True
    missing_agents = []

    # Need Claude CLI
    if not agents_available["claude_cli"]:
        missing_agents.append("Claude (install claude CLI)")
        can_proceed = False

    # Need Gemini CLI
    if not agents_available["gemini_cli"]:
        missing_agents.append("Gemini (install gemini CLI)")
        can_proceed = False

    # Need Cursor CLI
    if not agents_available["cursor_cli"]:
        missing_agents.append("Cursor (install cursor-agent CLI)")
        can_proceed = False

    if missing_agents:
        errors.append(
            {
                "type": "missing_agents",
                "agents": missing_agents,
                "message": f"Missing agents: {', '.join(missing_agents)}",
                "timestamp": datetime.now().isoformat(),
            }
        )

    # If we have errors, fail the prerequisite check
    if errors:
        logger.error(f"Prerequisites failed: {len(errors)} errors")
        return {
            "errors": errors,
            "next_decision": "abort",
        }

    logger.info("Prerequisites check passed")

    return {
        "updated_at": datetime.now().isoformat(),
        "next_decision": "continue",
    }
