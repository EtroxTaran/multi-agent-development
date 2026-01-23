"""Router for write_tests node."""

from typing import Literal

from ..state import WorkflowState


def write_tests_router(state: WorkflowState) -> Literal["implement_task", "human_escalation"]:
    """Route from write_tests node.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    if state.get("next_decision") == "escalate":
        return "human_escalation"

    return "implement_task"
