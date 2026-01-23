"""Fixer workflow routers.

These routers determine the next node in the fixer flow based on
state conditions.
"""

import logging
from typing import Literal

from ..state import WorkflowState

logger = logging.getLogger(__name__)


def fixer_triage_router(
    state: WorkflowState,
) -> Literal["fixer_diagnose", "human_escalation", "skip_fixer"]:
    """Route from fixer_triage based on triage decision.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    decision = state.get("next_decision")

    if decision == "diagnose":
        return "fixer_diagnose"
    elif decision == "skip":
        return "skip_fixer"
    else:  # escalate, retry_later, or unknown
        return "human_escalation"


def fixer_diagnose_router(
    state: WorkflowState,
) -> Literal["fixer_validate", "fixer_apply", "fixer_research", "human_escalation"]:
    """Route from fixer_diagnose based on diagnosis result.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    decision = state.get("next_decision")

    if decision == "validate":
        return "fixer_validate"
    elif decision == "apply":
        return "fixer_apply"
    elif decision == "research":
        return "fixer_research"
    else:  # escalate
        return "human_escalation"


def fixer_research_router(
    state: WorkflowState,
) -> Literal["fixer_validate", "human_escalation"]:
    """Route from fixer_research based on research result.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    decision = state.get("next_decision")

    if decision == "validate":
        return "fixer_validate"
    else:  # escalate
        return "human_escalation"


def fixer_validate_router(
    state: WorkflowState,
) -> Literal["fixer_apply", "human_escalation"]:
    """Route from fixer_validate based on validation result.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    decision = state.get("next_decision")

    if decision == "apply":
        return "fixer_apply"
    else:  # escalate
        return "human_escalation"


def fixer_apply_router(
    state: WorkflowState,
) -> Literal["fixer_verify", "human_escalation"]:
    """Route from fixer_apply based on application result.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    decision = state.get("next_decision")

    if decision == "verify":
        return "fixer_verify"
    else:  # escalate
        return "human_escalation"


def fixer_verify_router(
    state: WorkflowState,
) -> Literal["resume_workflow", "human_escalation"]:
    """Route from fixer_verify based on verification result.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    decision = state.get("next_decision")

    if decision == "resume":
        return "resume_workflow"
    else:  # escalate
        return "human_escalation"


def should_use_fixer_router(
    state: WorkflowState,
) -> Literal["fixer_triage", "human_escalation"]:
    """Determine whether to use fixer or go directly to escalation.

    This router is used as the first check when an error occurs.
    It checks if the fixer is enabled and the circuit breaker allows.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    fixer_enabled = state.get("fixer_enabled", True)
    circuit_breaker_open = state.get("fixer_circuit_breaker_open", False)

    if fixer_enabled and not circuit_breaker_open:
        return "fixer_triage"
    else:
        return "human_escalation"