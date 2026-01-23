"""Router for fix_bug node."""

from typing import Literal

from ..state import WorkflowState


def fix_bug_router(state: WorkflowState) -> Literal["verify_task", "human_escalation"]:
    """Route from fix_bug node.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    if state.get("next_decision") == "escalate":
        return "human_escalation"

    return "verify_task"
