"""Fixer diagnosis node.

This node analyzes errors to determine their root cause and
creates a fix plan.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..state import WorkflowState

if TYPE_CHECKING:
    from ...fixer import FixPlan, KnownFix
    from ...fixer.diagnosis import DiagnosisResult

logger = logging.getLogger(__name__)


def _extract_placeholder_value(
    diagnosis: "DiagnosisResult",
    known_fix: "KnownFix",
) -> Optional[str]:
    """Extract placeholder value from error message using known fix pattern.

    Args:
        diagnosis: The diagnosis result containing error info
        known_fix: The known fix with pattern to match

    Returns:
        Extracted value (e.g., module name, env var) or None
    """
    error_text = f"{diagnosis.error.message}\n{diagnosis.error.stack_trace or ''}"
    pattern = known_fix.pattern.pattern

    match = re.search(pattern, error_text, re.IGNORECASE)
    if match and match.groups():
        return match.group(1)

    return None


def _create_plan_from_known_fix(
    diagnosis: "DiagnosisResult",
    known_fix: "KnownFix",
) -> Optional["FixPlan"]:
    """Create a FixPlan from a KnownFix when no strategy is available.

    Args:
        diagnosis: The diagnosis result
        known_fix: The known fix to create plan from

    Returns:
        FixPlan or None if plan cannot be created
    """
    from ...fixer import FixPlan
    from ...fixer.strategies import FixAction

    fix_type = known_fix.fix_type
    fix_data = known_fix.fix_data
    extracted_value = _extract_placeholder_value(diagnosis, known_fix)
    actions = []

    # Map fix_type to FixAction objects
    if fix_type == "install_package":
        command_template = fix_data.get("command", "pip install {module}")
        if extracted_value:
            command = command_template.replace("{module}", extracted_value)
        else:
            # Cannot create plan without knowing which module
            return None
        actions.append(
            FixAction(
                action_type="run_command",
                target=command,
                params={"timeout": 300},
                description=f"Install missing package: {extracted_value}",
            )
        )

    elif fix_type == "add_import":
        if not diagnosis.affected_files:
            return None
        module = fix_data.get("module", "{name}")
        if extracted_value:
            module = module.replace("{name}", extracted_value)
        actions.append(
            FixAction(
                action_type="add_import",
                target=diagnosis.affected_files[0].path,
                params={"import_statement": f"import {module}"},
                description=f"Add import statement for {module}",
            )
        )

    elif fix_type == "fix_indentation":
        if not diagnosis.affected_files:
            return None
        actions.append(
            FixAction(
                action_type="run_command",
                target=f"autopep8 --in-place {diagnosis.affected_files[0].path}",
                params={"timeout": 30},
                description="Auto-fix indentation with autopep8",
            )
        )

    elif fix_type == "increase_timeout":
        multiplier = fix_data.get("multiplier", 2)
        actions.append(
            FixAction(
                action_type="increase_timeout",
                target="",
                params={"multiplier": multiplier},
                description=f"Increase timeout by {multiplier}x",
            )
        )

    elif fix_type == "add_env_var":
        if not extracted_value:
            return None
        default = fix_data.get("default", "")
        actions.append(
            FixAction(
                action_type="run_command",
                target=f"echo '{extracted_value}={default}' >> .env.example",
                params={},
                description=f"Add {extracted_value} to .env.example template",
            )
        )

    elif fix_type == "use_parameterized_query":
        if not diagnosis.affected_files:
            return None
        actions.append(
            FixAction(
                action_type="security_fix",
                target=diagnosis.affected_files[0].path,
                params={"fix_type": "parameterized_query"},
                description="Convert to parameterized SQL query (requires agent)",
            )
        )

    elif fix_type == "analyze_test_failure":
        # This requires agent analysis - return empty plan to trigger escalation
        # But with a plan object so we have context
        pass

    else:
        logger.warning(f"Unknown fix_type: {fix_type}")
        return None

    # Create plan with confidence based on known fix success rate
    confidence = max(0.3, known_fix.success_rate) if known_fix.success_rate > 0 else 0.5

    return FixPlan(
        diagnosis=diagnosis,
        strategy_name=f"known_fix:{known_fix.id}",
        actions=actions,
        estimated_impact=len(diagnosis.affected_files) if diagnosis.affected_files else 1,
        requires_validation=fix_type in ("use_parameterized_query", "analyze_test_failure"),
        requires_security_notification=fix_type == "use_parameterized_query",
        confidence=confidence,
    )


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
        ErrorCategory,
        FixerError,
        KnownFixDatabase,
        RootCause,
        get_strategy_for_error,
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
    diagnosis = await diagnosis_engine.diagnose(error, category, state)

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
        plan = _create_plan_from_known_fix(diagnosis, known_fix)

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
    requires_research = diagnosis.root_cause in (
        RootCause.API_MISUSE,
        RootCause.MISSING_DOCUMENTATION,
        RootCause.DEPRECATED_FEATURE,
    )

    if requires_research:
        next_decision = "research"
    else:
        requires_validation = (
            plan.requires_validation or plan.requires_security_notification or plan.confidence < 0.5
        )
        next_decision = "validate" if requires_validation else "apply"

    return {
        "current_fix_attempt": {
            **current_fix,
            "diagnosis": diagnosis.to_dict(),
            "plan": plan.to_dict() if plan else None,
            "known_fix_id": known_fix.id if known_fix else None,
        },
        "next_decision": next_decision,
        "updated_at": datetime.now().isoformat(),
    }
