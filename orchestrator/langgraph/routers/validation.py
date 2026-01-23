"""Validation phase router.

Routes after the validation fan-in node based on approval results.
"""


from typing import Literal

from langchain_core.runnables import RunnableConfig

from ..state import WorkflowDecision, WorkflowState


def validation_router(
    state: WorkflowState,
    config: RunnableConfig,
) -> Literal["implementation", "planning", "human_escalation", "__end__"]:
    """Route after validation based on results.

    Args:
        state: Current workflow state
        config: LangChain config containing potential callbacks

    Returns:
        Next node name
    """
    decision = _get_decision(state)

    # Emit path decision event if emitter is provided
    if config and "configurable" in config:
        emitter = config["configurable"].get("path_emitter")
        if emitter and callable(emitter):
            try:
                emitter(router="validation_router", decision=decision, state=state)
            except Exception:
                # Don't fail workflow if emission fails
                pass

    return decision


def _get_decision(state: WorkflowState) -> str:
    """Determine the next step."""
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
