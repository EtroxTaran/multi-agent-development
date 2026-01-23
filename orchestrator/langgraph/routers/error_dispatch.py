"""Error dispatch router."""

from ..state import WorkflowState


def error_dispatch_router(
    state: WorkflowState,
) -> str:
    """Route from error_dispatch based on fixer availability.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    decision = state.get("next_decision")

    if decision == "use_fixer":
        return "fixer_triage"
    else:
        return "human_escalation"
