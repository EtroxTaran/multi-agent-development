"""Prerequisites check node.

Validates that all required files and tools are available
before starting the workflow.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState, PhaseStatus

logger = logging.getLogger(__name__)


async def prerequisites_node(state: WorkflowState) -> dict[str, Any]:
    """Check prerequisites before starting workflow.

    Validates:
    - PRODUCT.md exists
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

    # Check PRODUCT.md
    product_file = project_dir / "PRODUCT.md"
    if not product_file.exists():
        errors.append({
            "type": "missing_file",
            "file": "PRODUCT.md",
            "message": "PRODUCT.md not found. Create it with your feature specification.",
            "timestamp": datetime.now().isoformat(),
        })

    # Check for workflow directory
    workflow_dir = project_dir / ".workflow"
    if not workflow_dir.exists():
        workflow_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created workflow directory: {workflow_dir}")

    # Check agent availability
    from ...sdk import ClaudeSDKAgent, GeminiSDKAgent

    agents_available = {
        "claude_sdk": ClaudeSDKAgent.is_available(),
        "gemini_sdk": GeminiSDKAgent.is_available(),
    }

    # Check CLI fallbacks
    from ...agents import ClaudeAgent, CursorAgent, GeminiAgent

    claude_cli = ClaudeAgent(project_dir)
    cursor_cli = CursorAgent(project_dir)
    gemini_cli = GeminiAgent(project_dir)

    agents_available["claude_cli"] = claude_cli.check_available()
    agents_available["cursor_cli"] = cursor_cli.check_available()
    agents_available["gemini_cli"] = gemini_cli.check_available()

    # Determine if we can proceed
    can_proceed = True
    missing_agents = []

    # Need at least one way to call Claude
    if not (agents_available["claude_sdk"] or agents_available["claude_cli"]):
        missing_agents.append("Claude (set ANTHROPIC_API_KEY or install claude CLI)")
        can_proceed = False

    # Need at least one way to call Gemini
    if not (agents_available["gemini_sdk"] or agents_available["gemini_cli"]):
        missing_agents.append("Gemini (set GOOGLE_API_KEY or install gemini CLI)")
        can_proceed = False

    # Cursor is CLI only
    if not agents_available["cursor_cli"]:
        missing_agents.append("Cursor (install cursor-agent CLI)")
        can_proceed = False

    if missing_agents:
        errors.append({
            "type": "missing_agents",
            "agents": missing_agents,
            "message": f"Missing agents: {', '.join(missing_agents)}",
            "timestamp": datetime.now().isoformat(),
        })

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
