"""Verification phase router.

Routes after the verification fan-in node based on review results.
"""

from typing import Literal

from ..state import WorkflowDecision, WorkflowState


def verification_router(
    state: WorkflowState,
) -> Literal["completion", "implementation", "human_escalation", "__end__"]:
    """Route after verification based on results.

    Also checks for build verification failures that occurred before
    the parallel review fan-out.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "completion": Verification passed, proceed to completion
        - "implementation": Verification failed, need to fix code
        - "human_escalation": Max retries exceeded, escalate
        - "__end__": Abort workflow
    """
    # First, check for build verification errors
    # Build verification runs before parallel reviews, and build failures
    # are stored in errors. We need to check for them here.
    errors = state.get("errors", [])
    build_errors = [e for e in errors if e.get("type") == "build_verification_failed"]
    if build_errors:
        # Check iteration count to decide retry vs escalate
        iteration_count = state.get("iteration_count", 0)
        if iteration_count >= 3:
            return "human_escalation"
        return "implementation"

    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "completion"

    if decision == WorkflowDecision.RETRY or decision == "retry":
        return "implementation"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Default: check phase status
    phase_status = state.get("phase_status", {})
    phase_4 = phase_status.get("4")

    if phase_4 and hasattr(phase_4, "status"):
        from ..state import PhaseStatus

        if phase_4.status == PhaseStatus.COMPLETED:
            return "completion"
        elif phase_4.status == PhaseStatus.FAILED:
            if phase_4.attempts >= phase_4.max_attempts:
                return "human_escalation"
            return "implementation"

    # Default to escalation if unknown state
    return "human_escalation"
