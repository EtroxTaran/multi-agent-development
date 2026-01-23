"""Escalation node for human-in-the-loop.

Pauses the workflow and waits for human intervention when
automated resolution fails. In autonomous mode (afk), makes
best-practice decisions automatically without human input.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from langgraph.types import interrupt

from ..state import WorkflowState, PhaseStatus

logger = logging.getLogger(__name__)


# Maximum retries before automatic abort in autonomous mode
AUTONOMOUS_MAX_RETRIES = 3


def _make_autonomous_decision(
    state: WorkflowState,
    issue_summary: str,
    error_type: str,
    escalation: dict,
) -> dict[str, Any]:
    """Make an automatic decision in autonomous mode.

    In autonomous mode, the orchestrator makes decisions based on
    best practices instead of waiting for human input.

    Args:
        state: Current workflow state
        issue_summary: Summary of the issue
        error_type: Type of error encountered
        escalation: Full escalation context

    Returns:
        State updates with automatic decision
    """
    current_phase = state.get("current_phase", 0)
    iteration_count = state.get("iteration_count", 0)

    logger.info(f"[AUTONOMOUS] Making automatic decision for: {issue_summary}")

    # Check if we've exceeded max retries in this phase
    phase_status = state.get("phase_status", {})
    current_phase_state = phase_status.get(str(current_phase))
    phase_retry_count = 0
    if current_phase_state and hasattr(current_phase_state, "retry_count"):
        phase_retry_count = current_phase_state.retry_count

    # Decision logic based on error type
    if error_type == "planning_error":
        if phase_retry_count < AUTONOMOUS_MAX_RETRIES:
            logger.info(f"[AUTONOMOUS] Retrying planning (attempt {phase_retry_count + 1}/{AUTONOMOUS_MAX_RETRIES})")
            return {
                "next_decision": "retry",
                "updated_at": datetime.now().isoformat(),
            }
        else:
            logger.warning("[AUTONOMOUS] Planning failed after max retries, aborting")
            return {
                "next_decision": "abort",
                "errors": [{
                    "type": "autonomous_abort",
                    "message": f"Planning failed after {AUTONOMOUS_MAX_RETRIES} attempts in autonomous mode",
                    "timestamp": datetime.now().isoformat(),
                }],
            }

    elif error_type == "validation_failed":
        if phase_retry_count < AUTONOMOUS_MAX_RETRIES:
            logger.info(f"[AUTONOMOUS] Retrying validation (attempt {phase_retry_count + 1}/{AUTONOMOUS_MAX_RETRIES})")
            return {
                "next_decision": "retry",
                "updated_at": datetime.now().isoformat(),
            }
        else:
            # Skip validation and continue to implementation
            logger.warning("[AUTONOMOUS] Validation failed after max retries, skipping to implementation")
            return {
                "current_phase": 3,  # Skip to implementation
                "next_decision": "continue",
                "review_skipped": True,
                "review_skipped_reason": f"Autonomous mode: validation failed after {AUTONOMOUS_MAX_RETRIES} attempts",
                "updated_at": datetime.now().isoformat(),
            }

    elif error_type == "implementation_error":
        # Check for clarification requests
        clarifications = escalation.get("clarifications", [])
        if clarifications:
            # In autonomous mode, proceed with best-guess implementation
            logger.info("[AUTONOMOUS] Clarification needed but proceeding with best-guess implementation")
            return {
                "next_decision": "retry",
                "updated_at": datetime.now().isoformat(),
            }
        else:
            if phase_retry_count < AUTONOMOUS_MAX_RETRIES:
                logger.info(f"[AUTONOMOUS] Retrying implementation (attempt {phase_retry_count + 1}/{AUTONOMOUS_MAX_RETRIES})")
                return {
                    "next_decision": "retry",
                    "updated_at": datetime.now().isoformat(),
                }
            else:
                logger.warning("[AUTONOMOUS] Implementation failed after max retries, aborting")
                return {
                    "next_decision": "abort",
                    "errors": [{
                        "type": "autonomous_abort",
                        "message": f"Implementation failed after {AUTONOMOUS_MAX_RETRIES} attempts in autonomous mode",
                        "timestamp": datetime.now().isoformat(),
                    }],
                }

    elif error_type == "verification_failed":
        if phase_retry_count < AUTONOMOUS_MAX_RETRIES:
            logger.info(f"[AUTONOMOUS] Retrying verification (attempt {phase_retry_count + 1}/{AUTONOMOUS_MAX_RETRIES})")
            return {
                "next_decision": "retry",
                "updated_at": datetime.now().isoformat(),
            }
        else:
            # Skip verification and complete (not recommended but autonomous mode)
            logger.warning("[AUTONOMOUS] Verification failed after max retries, completing with warnings")
            return {
                "current_phase": 5,  # Skip to completion
                "next_decision": "continue",
                "review_skipped": True,
                "review_skipped_reason": f"Autonomous mode: verification failed after {AUTONOMOUS_MAX_RETRIES} attempts",
                "updated_at": datetime.now().isoformat(),
            }

    else:
        # Unknown error type - default to retry once, then abort
        if phase_retry_count < 1:
            logger.info("[AUTONOMOUS] Unknown error, attempting retry")
            return {
                "next_decision": "retry",
                "updated_at": datetime.now().isoformat(),
            }
        else:
            logger.warning("[AUTONOMOUS] Unknown error persists, aborting")
            return {
                "next_decision": "abort",
                "errors": [{
                    "type": "autonomous_abort",
                    "message": f"Unknown error in autonomous mode: {issue_summary}",
                    "timestamp": datetime.now().isoformat(),
                }],
            }


async def human_escalation_node(state: WorkflowState) -> dict[str, Any]:
    """Escalate to human for intervention.

    Uses LangGraph's interrupt() to pause execution and wait
    for human input to resolve the issue.

    Note: In most cases, errors are first routed to the fixer_triage node
    before reaching this node. This node handles cases where:
    1. The fixer is disabled
    2. The fixer circuit breaker is open
    3. The fixer could not fix the error
    4. The error type is not auto-fixable

    Args:
        state: Current workflow state

    Returns:
        State updates after human intervention
    """
    logger.warning(f"Escalating to human: {state['project_name']}")

    # Check if this escalation came from the fixer
    current_fix = state.get("current_fix_attempt")
    fixer_attempted = current_fix is not None and current_fix.get("result") is not None

    project_dir = Path(state["project_dir"])
    errors = state.get("errors", [])
    current_phase = state.get("current_phase", 0)

    # Build escalation context
    escalation = {
        "project": state["project_name"],
        "current_phase": current_phase,
        "phase_status": {
            k: v.to_dict() if hasattr(v, "to_dict") else str(v)
            for k, v in state.get("phase_status", {}).items()
        },
        "recent_errors": errors[-5:] if errors else [],
        "timestamp": datetime.now().isoformat(),
        "fixer_attempted": fixer_attempted,
        "fixer_enabled": state.get("fixer_enabled", True),
        "fixer_circuit_breaker_open": state.get("fixer_circuit_breaker_open", False),
    }

    # Add fixer context if available
    if fixer_attempted and current_fix:
        escalation["fixer_diagnosis"] = current_fix.get("diagnosis", {})
        escalation["fixer_result"] = current_fix.get("result", {})

    # Determine the issue type
    issue_summary = "Unknown issue"
    suggested_actions = []

    if errors:
        last_error = errors[-1]
        error_type = last_error.get("type", "unknown")

        if error_type == "planning_error":
            issue_summary = "Planning phase failed repeatedly"
            suggested_actions = [
                "Review PRODUCT.md for clarity",
                "Simplify the feature requirements",
                "Manually create a plan and retry validation",
            ]
        elif error_type == "validation_failed":
            issue_summary = "Plan validation failed after max attempts"
            suggested_actions = [
                "Review blocking issues from agents",
                "Modify the plan manually",
                "Reduce scope of the feature",
            ]
        elif error_type == "implementation_error":
            # Check if this is a clarification request
            clarifications = last_error.get("clarifications", [])
            if clarifications:
                issue_summary = f"Worker needs clarification: {clarifications[0].get('question', 'Unknown')}"
                suggested_actions = [
                    "Answer the clarification question below",
                    "Update the plan with more specific requirements",
                    "Provide guidance in PRODUCT.md and retry",
                ]
                # Add clarification details to escalation
                escalation["clarifications"] = clarifications
            else:
                issue_summary = "Implementation phase failed"
                suggested_actions = [
                    "Check for dependency issues",
                    "Review the plan for feasibility",
                    "Implement manually and skip to verification",
                ]
        elif error_type == "verification_failed":
            issue_summary = "Code verification failed after max attempts"
            suggested_actions = [
                "Review blocking issues from reviewers",
                "Fix issues manually",
                "Accept with known issues",
            ]

    escalation["issue_summary"] = issue_summary
    escalation["suggested_actions"] = suggested_actions

    # Save escalation details to database
    from ...db.repositories.logs import get_logs_repository
    from ...storage.async_utils import run_async

    repo = get_logs_repository(state["project_name"])
    run_async(repo.create_log(log_type="escalation", content=escalation))

    # Also save blocker entry
    blocker_entry = {
        "timestamp": datetime.now().isoformat(),
        "phase": current_phase,
        "issue_summary": issue_summary,
        "recent_errors": errors[-3:] if errors else [],
        "suggested_actions": suggested_actions,
    }
    run_async(repo.create_log(log_type="blocker", content=blocker_entry))

    logger.info(f"Escalation saved to database")

    # Check execution mode
    execution_mode = state.get("execution_mode", "hitl")

    if execution_mode == "afk":
        # Autonomous mode - make automatic decision without human input
        logger.info("[AUTONOMOUS] Making automatic escalation decision")

        # Determine error type
        error_type = "unknown"
        if errors:
            error_type = errors[-1].get("type", "unknown")

        return _make_autonomous_decision(state, issue_summary, error_type, escalation)

    # Interactive mode (hitl) - Use LangGraph interrupt to pause for human input
    # The human can:
    # 1. Modify state and resume
    # 2. Skip to a specific phase
    # 3. Abort the workflow
    human_response = interrupt({
        "type": "escalation",
        "project": state["project_name"],
        "phase": current_phase,
        "issue": issue_summary,
        "suggested_actions": suggested_actions,
        "message": (
            f"Workflow paused at phase {current_phase}: {issue_summary}. "
            f"Please resolve the issue and resume."
        ),
    })

    # Process human response
    if human_response is None:
        # Timeout or no response - abort
        return {
            "next_decision": "abort",
            "errors": [{
                "type": "escalation_timeout",
                "message": "Human escalation timed out",
                "timestamp": datetime.now().isoformat(),
            }],
        }

    action = human_response.get("action", "abort")

    if action == "retry":
        # Retry the current phase
        return {
            "next_decision": "retry",
            "updated_at": datetime.now().isoformat(),
        }
    elif action == "skip":
        # Skip to specified phase
        target_phase = human_response.get("target_phase", current_phase + 1)
        phase_status = state.get("phase_status", {}).copy()

        # Mark current phase as skipped
        if str(current_phase) in phase_status:
            ps = phase_status[str(current_phase)]
            ps.status = PhaseStatus.SKIPPED
            phase_status[str(current_phase)] = ps

        return {
            "phase_status": phase_status,
            "current_phase": target_phase,
            "next_decision": "continue",
            "updated_at": datetime.now().isoformat(),
        }
    elif action == "continue":
        # Human fixed the issue, continue
        return {
            "next_decision": "continue",
            "updated_at": datetime.now().isoformat(),
        }
    elif action == "answer_clarification":
        # Human answered clarification question - save and retry implementation
        answers = human_response.get("answers", {})
        if answers:
            # Save clarification answers to database
            run_async(repo.create_log(log_type="clarification_answers", content={
                "answers": answers,
                "timestamp": datetime.now().isoformat(),
            }))
            logger.info(f"Saved clarification answers to database: {list(answers.keys())}")

        return {
            "next_decision": "retry",
            "updated_at": datetime.now().isoformat(),
        }
    else:
        # Abort
        return {
            "next_decision": "abort",
            "errors": [{
                "type": "user_abort",
                "message": "Workflow aborted by user",
                "timestamp": datetime.now().isoformat(),
            }],
        }
