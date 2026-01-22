"""Fixer diagnosis node.

This node analyzes errors to determine their root cause and
creates a fix plan.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def fixer_diagnose_node(state: WorkflowState) -> dict[str, Any]:
    """Diagnose an error and create a fix plan.

    This node:
    1. Gets the current fix attempt from state
    2. Runs diagnosis to determine root cause
    3. Creates a fix plan
    4. Routes to validation or direct application

    Args:
        state: Current workflow state

    Returns:
        State updates with diagnosis and plan
    """
    from ...fixer import (
        DiagnosisEngine,
        FixerError,
        ErrorCategory,
        get_strategy_for_error,
        KnownFixDatabase,
    )

    project_dir = Path(state["project_dir"])
    workflow_dir = project_dir / ".workflow"
    current_fix = state.get("current_fix_attempt", {})

    if not current_fix:
        logger.warning("Fixer diagnose called but no current fix attempt")
        return {
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    # Get error and triage info
    error_id = current_fix.get("error_id")
    triage_data = current_fix.get("triage", {})
    category = ErrorCategory(triage_data.get("category", "unknown"))

    # Find the error in state
    errors = state.get("errors", [])
    error_data = next((e for e in errors if e.get("id") == error_id), errors[-1] if errors else {})
    error = FixerError.from_state_error(error_data, len(errors) - 1)

    logger.info(f"Diagnosing error: {error.error_type} ({category.value})")

    # Run diagnosis
    diagnosis_engine = DiagnosisEngine(project_dir)
    diagnosis = diagnosis_engine.diagnose(error, category, state)

    logger.info(
        f"Diagnosis: root_cause={diagnosis.root_cause.value}, "
        f"confidence={diagnosis.confidence.value}, "
        f"affected_files={len(diagnosis.affected_files)}"
    )

    # Check known fixes
    known_fixes = KnownFixDatabase(workflow_dir)
    known_fix = known_fixes.find_matching_fix(diagnosis)

    # Get appropriate strategy and create plan
    strategy = get_strategy_for_error(project_dir, diagnosis)

    if strategy is None and known_fix is None:
        logger.warning(f"No strategy or known fix for {diagnosis.root_cause}")
        return {
            "current_fix_attempt": {
                **current_fix,
                "diagnosis": diagnosis.to_dict(),
                "error": "No fix strategy available",
            },
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    # Create fix plan
    if strategy:
        plan = strategy.create_plan(diagnosis)
    else:
        # Use known fix to create plan
        plan = None  # TODO: Create plan from known fix

    if plan is None or not plan.actions:
        logger.warning("Could not create fix plan")
        return {
            "current_fix_attempt": {
                **current_fix,
                "diagnosis": diagnosis.to_dict(),
                "error": "Could not create fix plan",
            },
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    logger.info(
        f"Created fix plan: strategy={plan.strategy_name}, "
        f"actions={len(plan.actions)}, "
        f"confidence={plan.confidence:.2f}"
    )

    # Determine next step
    requires_validation = (
        plan.requires_validation or
        plan.requires_security_notification or
        plan.confidence < 0.5
    )

    next_decision = "validate" if requires_validation else "apply"

    return {
        "current_fix_attempt": {
            **current_fix,
            "diagnosis": diagnosis.to_dict(),
            "plan": plan.to_dict(),
            "known_fix_id": known_fix.id if known_fix else None,
        },
        "next_decision": next_decision,
        "updated_at": datetime.now().isoformat(),
    }
