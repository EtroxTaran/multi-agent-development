"""Fixer triage node.

This node is the entry point for the fixer when an error occurs.
It determines whether the fixer can handle the error or if it
should be escalated to a human.
"""

import logging
from datetime import datetime
from typing import Any

from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def fixer_triage_node(state: WorkflowState) -> dict[str, Any]:
    """Triage an error to determine if the fixer can handle it.

    This node:
    1. Stops background processes if critical error
    2. Checks circuit breaker status
    3. Checks per-error/session limits
    4. Categorizes the error type
    5. Routes to diagnosis or escalates to human

    Args:
        state: Current workflow state

    Returns:
        State updates
    """
    from ...fixer import ErrorTriage, FixerError, TriageDecision

    project_dir = state["project_dir"]
    errors = state.get("errors", [])
    fixer_enabled = state.get("fixer_enabled", True)
    circuit_breaker_open = state.get("fixer_circuit_breaker_open", False)
    fix_history = state.get("fix_history", [])
    fixer_attempts = state.get("fixer_attempts", 0)

    # Get the most recent error
    if not errors:
        logger.warning("Fixer triage called but no errors in state")
        return {
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    last_error = errors[-1]
    error = FixerError.from_state_error(last_error, len(errors) - 1)

    logger.info(f"Fixer triage: {error.error_type} - {error.message[:100]}")

    # Quick checks before full triage
    if not fixer_enabled:
        logger.info("Fixer is disabled, escalating to human")
        return {
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    if circuit_breaker_open:
        logger.info("Circuit breaker is open, escalating to human")
        return {
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    # Full triage
    triage = ErrorTriage(
        max_attempts_per_error=2,
        max_attempts_per_session=10,
    )

    triage_result = triage.triage(
        error=error,
        fixer_enabled=fixer_enabled,
        circuit_breaker_open=circuit_breaker_open,
        fix_history=fix_history,
    )

    logger.info(
        f"Triage result: category={triage_result.category.value}, "
        f"decision={triage_result.decision.value}, "
        f"confidence={triage_result.confidence:.2f}"
    )

    # Build state updates
    updates = {
        "updated_at": datetime.now().isoformat(),
        "current_fix_attempt": {
            "error_id": error.error_id,
            "error_type": error.error_type,
            "triage": triage_result.to_dict(),
            "started_at": datetime.now().isoformat(),
        },
    }

    if triage_result.decision == TriageDecision.ATTEMPT_FIX:
        updates["next_decision"] = "diagnose"
        updates["fixer_attempts"] = fixer_attempts + 1
    elif triage_result.decision == TriageDecision.ESCALATE:
        updates["next_decision"] = "escalate"
    elif triage_result.decision == TriageDecision.SKIP:
        updates["next_decision"] = "skip"
    else:  # RETRY_LATER
        updates["next_decision"] = "retry_later"

    return updates
