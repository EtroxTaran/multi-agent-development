"""Pause checkpoint node for dashboard-controlled workflow pausing.

This node checks if a pause has been requested via the dashboard API
and uses LangGraph's interrupt() for safe pausing at checkpoints.
"""

import logging
from datetime import datetime
from typing import Any

from langgraph.types import interrupt

from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def pause_check_node(state: WorkflowState) -> dict[str, Any]:
    """Check if workflow should pause at this checkpoint.

    This node is inserted at key transition points in the workflow.
    When pause_requested is True, it uses interrupt() to safely pause
    the workflow and wait for user input to resume or abort.

    Args:
        state: Current workflow state

    Returns:
        State updates (clears pause flags on resume)
    """
    # Check if pause was requested
    if not state.get("pause_requested", False):
        # No pause requested, continue normally
        return {"updated_at": datetime.now().isoformat()}

    # Log the pause
    logger.info(
        f"Pause requested at node after phase {state.get('current_phase')}. "
        f"Reason: {state.get('pause_reason', 'No reason provided')}"
    )

    # Use interrupt() to safely pause the workflow
    # This will checkpoint the state and wait for human input
    human_response = interrupt(
        {
            "type": "pause",
            "paused_at_node": state.get("paused_at_node"),
            "paused_at_phase": state.get("current_phase"),
            "message": "Workflow paused by user request",
            "reason": state.get("pause_reason"),
            "timestamp": state.get("paused_at_timestamp"),
            "options": ["resume", "abort"],
        }
    )

    # Handle the response
    action = human_response.get("action") if human_response else "resume"

    if action == "abort":
        logger.info("User chose to abort workflow from pause")
        return {
            "next_decision": "abort",
            "pause_requested": False,
            "paused_at_node": None,
            "paused_at_timestamp": None,
            "pause_reason": None,
            "updated_at": datetime.now().isoformat(),
        }

    # Resume - clear pause flags
    logger.info("Workflow resumed from pause")
    return {
        "pause_requested": False,
        "paused_at_node": None,
        "paused_at_timestamp": None,
        "pause_reason": None,
        "updated_at": datetime.now().isoformat(),
    }


def should_check_pause(state: WorkflowState) -> bool:
    """Check if pause check is needed.

    Can be used as a conditional edge condition.

    Args:
        state: Current workflow state

    Returns:
        True if pause check is needed
    """
    return state.get("pause_requested", False)


def pause_router(state: WorkflowState) -> str:
    """Router to decide if we need to pause.

    Args:
        state: Current workflow state

    Returns:
        "pause_check" if pause requested, "continue" otherwise
    """
    if state.get("pause_requested", False):
        return "pause_check"
    return "continue"
