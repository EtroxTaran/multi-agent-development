"""Approval gate node.

Pauses workflow for human approval at configured phases.
Uses LangGraph's interrupt() for human-in-the-loop.
In autonomous mode, auto-approves and continues without human input.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from langgraph.types import interrupt

from ...config import load_project_config
from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def approval_gate_node(state: WorkflowState) -> dict[str, Any]:
    """Human approval gate.

    Pauses workflow for human approval using interrupt().
    The human can:
    - approve: Continue to next phase
    - reject: Abort workflow
    - request_changes: Retry previous phase

    Args:
        state: Current workflow state

    Returns:
        State updates based on human response
    """
    project_dir = Path(state["project_dir"])
    current_phase = state.get("current_phase", 1)

    logger.info(f"Approval gate at phase {current_phase} for: {state['project_name']}")

    # Load project config
    config = load_project_config(project_dir)

    # Check if approval gates are enabled for this phase
    if not config.workflow.features.approval_gates:
        logger.info("Approval gates disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    if current_phase not in config.workflow.approval_phases:
        logger.info(f"Phase {current_phase} not in approval_phases, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Check execution mode - auto-approve in autonomous mode
    execution_mode = state.get("execution_mode", "hitl")
    if execution_mode == "afk":
        logger.info(f"[AUTONOMOUS] Auto-approving phase {current_phase} (autonomous mode)")

        # Save auto-approval record for audit trail to database
        from ...db.repositories.logs import get_logs_repository
        from ...storage.async_utils import run_async

        repo = get_logs_repository(state["project_name"])
        run_async(
            repo.create_log(
                log_type="approval_response",
                content={
                    "phase": current_phase,
                    "timestamp": datetime.now().isoformat(),
                    "action": "approve",
                    "feedback": "Auto-approved in autonomous mode",
                    "autonomous": True,
                },
            )
        )

        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Prepare approval context
    approval_context = _build_approval_context(state, current_phase)

    # Save context for human review to database
    from ...db.repositories.logs import get_logs_repository
    from ...storage.async_utils import run_async

    repo = get_logs_repository(state["project_name"])
    run_async(
        repo.create_log(
            log_type="approval_context",
            content={
                "phase": current_phase,
                "context": approval_context,
            },
        )
    )

    logger.info(f"Waiting for human approval at phase {current_phase}")

    # Interrupt workflow for human input
    # The human will respond with: {"action": "approve" | "reject" | "request_changes", "feedback": "..."}
    human_response = interrupt(
        {
            "type": "approval_required",
            "phase": current_phase,
            "project": state["project_name"],
            "context": approval_context,
            "options": ["approve", "reject", "request_changes"],
            "message": f"Phase {current_phase} requires approval. Review the context and choose an action.",
        }
    )

    # Process human response
    action = human_response.get("action", "reject")
    feedback = human_response.get("feedback", "")

    logger.info(f"Received approval response: action={action}")

    # Save response to database
    run_async(
        repo.create_log(
            log_type="approval_response",
            content={
                "phase": current_phase,
                "timestamp": datetime.now().isoformat(),
                "action": action,
                "feedback": feedback,
            },
        )
    )

    if action == "approve":
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    elif action == "reject":
        return {
            "errors": [
                {
                    "type": "approval_rejected",
                    "message": f"Phase {current_phase} rejected by human reviewer",
                    "feedback": feedback,
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "abort",
            "updated_at": datetime.now().isoformat(),
        }

    elif action == "request_changes":
        return {
            "errors": [
                {
                    "type": "changes_requested",
                    "message": f"Changes requested at phase {current_phase}",
                    "feedback": feedback,
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "retry",
            "updated_at": datetime.now().isoformat(),
        }

    else:
        # Unknown action, treat as rejection
        logger.warning(f"Unknown approval action: {action}")
        return {
            "errors": [
                {
                    "type": "unknown_approval_action",
                    "message": f"Unknown approval action: {action}",
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "abort",
            "updated_at": datetime.now().isoformat(),
        }


def _build_approval_context(state: WorkflowState, phase: int) -> dict[str, Any]:
    """Build context for human approval review.

    Args:
        state: Current workflow state
        phase: Current phase number

    Returns:
        Context dictionary for review
    """
    context = {
        "phase": phase,
        "project_name": state.get("project_name"),
        "iteration_count": state.get("iteration_count", 0),
    }

    if phase == 2:
        # After planning, show plan summary
        plan = state.get("plan")
        if plan:
            context["plan_summary"] = {
                "tasks": len(plan.get("tasks", [])),
                "estimated_complexity": plan.get("estimated_complexity"),
                "key_files": plan.get("key_files", [])[:10],
            }

    elif phase == 3:
        # After validation, show validation feedback
        validation_feedback = state.get("validation_feedback")
        if validation_feedback:
            context["validation_summary"] = {}
            for agent, feedback in validation_feedback.items():
                if hasattr(feedback, "to_dict"):
                    context["validation_summary"][agent] = {
                        "approved": feedback.approved,
                        "score": feedback.score,
                        "concerns_count": len(feedback.concerns),
                    }

    elif phase == 4:
        # After implementation, show implementation summary
        impl_result = state.get("implementation_result")
        if impl_result:
            context["implementation_summary"] = {
                "status": impl_result.get("status"),
                "files_changed": impl_result.get("files_changed", [])[:10],
                "tests_added": impl_result.get("tests_added", []),
            }

    elif phase == 5:
        # After verification, show verification feedback
        verification_feedback = state.get("verification_feedback")
        if verification_feedback:
            context["verification_summary"] = {}
            for agent, feedback in verification_feedback.items():
                if hasattr(feedback, "to_dict"):
                    context["verification_summary"][agent] = {
                        "approved": feedback.approved,
                        "score": feedback.score,
                        "concerns_count": len(feedback.concerns),
                    }

    # Add recent errors if any
    errors = state.get("errors", [])
    if errors:
        context["recent_errors"] = errors[-5:]  # Last 5 errors

    return context
