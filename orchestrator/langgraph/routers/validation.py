"""Validation phase router.

Routes after the validation fan-in node based on approval results.
"""

from typing import Literal

from ..state import WorkflowState, WorkflowDecision


def validation_router(
    state: WorkflowState,
) -> Literal["implementation", "planning", "human_escalation", "__end__"]:
    """Route after validation based on results.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "implementation": Validation passed, proceed
        - "planning": Validation failed, need to revise plan
        - "human_escalation": Max retries exceeded, escalate
        - "__end__": Abort workflow
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "implementation"

    if decision == WorkflowDecision.RETRY or decision == "retry":
        return "planning"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Default: check phase status
    phase_status = state.get("phase_status", {})
    phase_2 = phase_status.get("2")

    if phase_2 and hasattr(phase_2, "status"):
        from ..state import PhaseStatus

        if phase_2.status == PhaseStatus.COMPLETED:
            return "implementation"
        elif phase_2.status == PhaseStatus.FAILED:
            if phase_2.attempts >= phase_2.max_attempts:
                return "human_escalation"
            return "planning"

    # Default to escalation if unknown state
    return "human_escalation"
