"""Error dispatch node.

This node acts as an interceptor that routes errors to either
the fixer or human escalation based on fixer configuration.
"""

import logging
from datetime import datetime
from typing import Any

from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def error_dispatch_node(state: WorkflowState) -> dict[str, Any]:
    """Dispatch errors to fixer or human escalation.

    This node checks if the fixer is enabled and can handle the error,
    then routes accordingly.

    Args:
        state: Current workflow state

    Returns:
        State updates with routing decision
    """
    fixer_enabled = state.get("fixer_enabled", True)
    circuit_breaker_open = state.get("fixer_circuit_breaker_open", False)

    # Log the dispatch decision
    logger.info(
        f"Error dispatch: fixer_enabled={fixer_enabled}, "
        f"circuit_breaker_open={circuit_breaker_open}"
    )

    if fixer_enabled and not circuit_breaker_open:
        logger.info("Routing to fixer_triage")
        return {
            "next_decision": "use_fixer",
            "updated_at": datetime.now().isoformat(),
        }
    else:
        reason = "disabled" if not fixer_enabled else "circuit_breaker_open"
        logger.info(f"Routing to human_escalation (fixer {reason})")
        return {
            "next_decision": "use_human",
            "updated_at": datetime.now().isoformat(),
        }


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
