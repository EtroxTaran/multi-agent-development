"""Error dispatch node.

This node acts as an interceptor that routes errors to either
the fixer or human escalation based on fixer configuration.

It uses rich ErrorContext from the state to make informed routing decisions.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from ..state import ErrorContext, WorkflowState

logger = logging.getLogger(__name__)

# Error types that should skip the fixer and go directly to human
SKIP_FIXER_ERROR_TYPES = {
    "PermissionError",  # Requires human intervention
    "AuthenticationError",  # Credentials issue
    "BudgetExceededError",  # Cost limit hit
    "CircuitBreakerError",  # Fixer already tried too many times
}

# Maximum retries per error before escalating
MAX_ERROR_RETRIES = 3


async def error_dispatch_node(state: WorkflowState) -> dict[str, Any]:
    """Dispatch errors to fixer or human escalation.

    Uses rich ErrorContext from state to make informed routing decisions:
    1. Check if error is recoverable
    2. Check retry count for this error
    3. Check fixer circuit breaker
    4. Route appropriately

    Args:
        state: Current workflow state

    Returns:
        State updates with routing decision
    """
    fixer_enabled = state.get("fixer_enabled", True)
    circuit_breaker_open = state.get("fixer_circuit_breaker_open", False)
    error_context: Optional[ErrorContext] = state.get("error_context")

    # Extract error info
    error_type = "unknown"
    error_message = "No error details"
    source_node = "unknown"
    recoverable = True
    retry_count = 0

    if error_context:
        error_type = error_context.get("error_type", "unknown")
        error_message = error_context.get("error_message", "No error details")
        source_node = error_context.get("source_node", "unknown")
        recoverable = error_context.get("recoverable", True)
        retry_count = error_context.get("retry_count", 0)

    # Log comprehensive error info
    logger.info(
        f"Error dispatch: type={error_type}, source={source_node}, "
        f"recoverable={recoverable}, retry_count={retry_count}, "
        f"fixer_enabled={fixer_enabled}, circuit_breaker_open={circuit_breaker_open}"
    )

    if error_context:
        # Log stack trace at debug level
        stack_trace = error_context.get("stack_trace", "")
        if stack_trace:
            logger.debug(f"Stack trace:\n{stack_trace}")

        # Log suggested actions
        suggested = error_context.get("suggested_actions", [])
        if suggested:
            logger.info(f"Suggested recovery actions: {suggested}")

    # Decision logic
    should_use_fixer = True
    skip_reason = None

    # Check 1: Fixer enabled?
    if not fixer_enabled:
        should_use_fixer = False
        skip_reason = "fixer_disabled"

    # Check 2: Circuit breaker open?
    elif circuit_breaker_open:
        should_use_fixer = False
        skip_reason = "circuit_breaker_open"

    # Check 3: Error type in skip list?
    elif error_type in SKIP_FIXER_ERROR_TYPES:
        should_use_fixer = False
        skip_reason = f"error_type_{error_type}_requires_human"

    # Check 4: Error marked as non-recoverable?
    elif not recoverable:
        should_use_fixer = False
        skip_reason = "error_not_recoverable"

    # Check 5: Too many retries?
    elif retry_count >= MAX_ERROR_RETRIES:
        should_use_fixer = False
        skip_reason = f"max_retries_exceeded_{retry_count}"

    # Build result
    if should_use_fixer:
        logger.info(f"Routing to fixer_triage for {error_type} from {source_node}")
        return {
            "next_decision": "use_fixer",
            "updated_at": datetime.now().isoformat(),
        }
    else:
        logger.info(f"Routing to human_escalation (reason: {skip_reason})")
        return {
            "next_decision": "use_human",
            "updated_at": datetime.now().isoformat(),
        }
