"""General routers for workflow phases.

Contains routers for prerequisites, planning, implementation, and completion phases.
"""

from typing import Literal

from ..state import WorkflowState, WorkflowDecision, PhaseStatus


def prerequisites_router(
    state: WorkflowState,
) -> Literal["planning", "human_escalation", "__end__"]:
    """Route after prerequisites check.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "planning": Prerequisites met, proceed to planning
        - "human_escalation": Prerequisites not met, need human help
        - "__end__": Abort workflow
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "planning"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Check phase status
    phase_status = state.get("phase_status", {})
    phase_0 = phase_status.get("0")

    if phase_0 and hasattr(phase_0, "status"):
        if phase_0.status == PhaseStatus.COMPLETED:
            return "planning"
        elif phase_0.status == PhaseStatus.FAILED:
            return "human_escalation"

    # Default: check for errors
    errors = state.get("errors", [])
    if errors:
        # Check if any errors are blocking
        blocking_errors = [
            e for e in errors
            if e.get("type") in ("missing_product_md", "no_agents_available")
        ]
        if blocking_errors:
            return "human_escalation"

    # Default to planning if no issues
    return "planning"


def planning_router(
    state: WorkflowState,
) -> Literal["cursor_validate", "human_escalation", "__end__"]:
    """Route after planning phase.

    Note: Planning routes to cursor_validate which runs in parallel with
    gemini_validate due to the graph structure.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "cursor_validate": Plan created, proceed to validation
        - "human_escalation": Planning failed, need human help
        - "__end__": Abort workflow
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "cursor_validate"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Check if plan exists
    plan = state.get("plan")
    if plan and plan.get("plan_name"):
        return "cursor_validate"

    # Check phase status
    phase_status = state.get("phase_status", {})
    phase_1 = phase_status.get("1")

    if phase_1 and hasattr(phase_1, "status"):
        if phase_1.status == PhaseStatus.COMPLETED:
            return "cursor_validate"
        elif phase_1.status == PhaseStatus.FAILED:
            if phase_1.attempts >= phase_1.max_attempts:
                return "human_escalation"
            # Retry planning - but this should be handled by the node itself
            return "human_escalation"

    # Default to validation if plan exists
    if plan:
        return "cursor_validate"

    return "human_escalation"


def implementation_router(
    state: WorkflowState,
) -> Literal["cursor_review", "planning", "human_escalation", "__end__"]:
    """Route after implementation phase.

    Note: Implementation routes to cursor_review which runs in parallel with
    gemini_review due to the graph structure.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "cursor_review": Implementation done, proceed to verification
        - "planning": Implementation failed, go back to planning
        - "human_escalation": Max retries exceeded
        - "__end__": Abort workflow
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "cursor_review"

    if decision == WorkflowDecision.RETRY or decision == "retry":
        # Go back to planning to revise the plan
        return "planning"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Check phase status
    phase_status = state.get("phase_status", {})
    phase_3 = phase_status.get("3")

    if phase_3 and hasattr(phase_3, "status"):
        if phase_3.status == PhaseStatus.COMPLETED:
            return "cursor_review"
        elif phase_3.status == PhaseStatus.FAILED:
            if phase_3.attempts >= phase_3.max_attempts:
                return "human_escalation"
            return "planning"

    # Check implementation result
    impl_result = state.get("implementation_result", {})
    if impl_result.get("success"):
        return "cursor_review"

    # Check for test failures
    test_results = impl_result.get("test_results", {})
    if test_results.get("failed", 0) > 0:
        return "planning"

    # Default to verification
    return "cursor_review"


def completion_router(
    state: WorkflowState,
) -> Literal["__end__"]:
    """Route after completion phase.

    Completion always ends the workflow.

    Args:
        state: Current workflow state

    Returns:
        Always returns "__end__"
    """
    # Completion always ends the workflow
    return "__end__"


def human_escalation_router(
    state: WorkflowState,
) -> Literal["planning", "implementation", "completion", "__end__"]:
    """Route after human escalation.

    Based on human response, route to the appropriate phase.

    Args:
        state: Current workflow state

    Returns:
        Next node based on human decision
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        # Continue from where we left off
        current_phase = state.get("current_phase", 0)
        if current_phase <= 1:
            return "planning"
        elif current_phase <= 3:
            return "implementation"
        else:
            return "completion"

    if decision == WorkflowDecision.RETRY or decision == "retry":
        # Retry the current phase
        current_phase = state.get("current_phase", 0)
        if current_phase <= 2:
            return "planning"
        else:
            return "implementation"

    # Default: abort
    return "__end__"


# New routers for risk mitigation nodes

def product_validation_router(
    state: WorkflowState,
) -> Literal["planning", "human_escalation", "__end__"]:
    """Route after product validation.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "planning": Validation passed, proceed to planning
        - "human_escalation": Validation failed, need human help
        - "__end__": Abort workflow
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "planning"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Default to planning if no issues
    return "planning"


def pre_implementation_router(
    state: WorkflowState,
) -> Literal["implementation", "human_escalation", "__end__"]:
    """Route after pre-implementation checks.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "implementation": Checks passed, proceed to implementation
        - "human_escalation": Checks failed, need human help
        - "__end__": Abort workflow
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "implementation"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Default to implementation
    return "implementation"


def build_verification_router(
    state: WorkflowState,
) -> Literal["cursor_review", "implementation", "human_escalation", "__end__"]:
    """Route after build verification.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "cursor_review": Build passed, proceed to verification
        - "implementation": Build failed, retry implementation
        - "human_escalation": Max retries exceeded
        - "__end__": Abort workflow
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "cursor_review"

    if decision == WorkflowDecision.RETRY or decision == "retry":
        return "implementation"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Default to verification
    return "cursor_review"


def coverage_check_router(
    state: WorkflowState,
) -> Literal["security_scan", "implementation", "human_escalation", "__end__"]:
    """Route after coverage check.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "security_scan": Coverage passed/non-blocking, proceed
        - "implementation": Coverage failed (blocking), retry
        - "human_escalation": Max retries exceeded
        - "__end__": Abort workflow
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "security_scan"

    if decision == WorkflowDecision.RETRY or decision == "retry":
        return "implementation"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Default to security scan
    return "security_scan"


def security_scan_router(
    state: WorkflowState,
) -> Literal["completion", "implementation", "human_escalation", "__end__"]:
    """Route after security scan.

    Args:
        state: Current workflow state

    Returns:
        Next node name:
        - "completion": Scan passed, proceed to completion
        - "implementation": Blocking issues, retry implementation
        - "human_escalation": Max retries exceeded
        - "__end__": Abort workflow
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "completion"

    if decision == WorkflowDecision.RETRY or decision == "retry":
        return "implementation"

    if decision == WorkflowDecision.ESCALATE or decision == "escalate":
        return "human_escalation"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Default to completion
    return "completion"


def approval_gate_router(
    state: WorkflowState,
) -> Literal["pre_implementation", "planning", "human_escalation", "__end__"]:
    """Route after approval gate (post-validation).

    Args:
        state: Current workflow state

    Returns:
        Next node name based on approval decision
    """
    decision = state.get("next_decision")

    if decision == WorkflowDecision.CONTINUE or decision == "continue":
        return "pre_implementation"

    if decision == WorkflowDecision.RETRY or decision == "retry":
        return "planning"

    if decision == WorkflowDecision.ABORT or decision == "abort":
        return "__end__"

    # Default to pre-implementation
    return "pre_implementation"
