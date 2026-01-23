"""Fixer apply node.

This node applies the fix plan and creates rollback data.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def fixer_apply_node(state: WorkflowState) -> dict[str, Any]:
    """Apply a fix plan.

    This node:
    1. Creates a checkpoint/backup before applying
    2. Applies each action in the fix plan
    3. Records changes for potential rollback
    4. Routes to verification

    Args:
        state: Current workflow state

    Returns:
        State updates with fix result
    """
    from ...fixer import (
        CircuitBreaker,
        DiagnosisResult,
        FixerError,
        FixPlan,
        get_strategy_for_error,
    )

    project_dir = Path(state["project_dir"])
    workflow_dir = project_dir / ".workflow"
    current_fix = state.get("current_fix_attempt", {})

    if not current_fix:
        logger.warning("Fixer apply called but no current fix attempt")
        return {
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    plan_data = current_fix.get("plan", {})
    diagnosis_data = current_fix.get("diagnosis", {})

    if not plan_data or not plan_data.get("actions"):
        logger.warning("No fix plan actions to apply")
        return {
            "current_fix_attempt": {
                **current_fix,
                "error": "No actions in fix plan",
            },
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    logger.info(f"Applying fix plan: {plan_data.get('strategy_name')}")

    # Create backup/checkpoint
    backup_dir = workflow_dir / "fixer" / "backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Backup files that will be modified
    files_to_backup = []
    for action in plan_data.get("actions", []):
        if action.get("action_type") in ("edit_file", "delete_file", "write_file"):
            target = action.get("target", "")
            if target:
                files_to_backup.append(target)

    backups_created = _create_backups(project_dir, files_to_backup, backup_dir)
    logger.info(f"Created {len(backups_created)} backups in {backup_dir}")

    # Reconstruct diagnosis and plan objects
    error_data = diagnosis_data.get("error", {})
    error = FixerError.from_dict(error_data)

    from ...fixer import AffectedFile, DiagnosisConfidence, ErrorCategory, RootCause

    diagnosis = DiagnosisResult(
        error=error,
        root_cause=RootCause(diagnosis_data.get("root_cause", "unknown")),
        confidence=DiagnosisConfidence(diagnosis_data.get("confidence", "low")),
        category=ErrorCategory(diagnosis_data.get("category", "unknown")),
        affected_files=[AffectedFile(**af) for af in diagnosis_data.get("affected_files", [])],
        explanation=diagnosis_data.get("explanation", ""),
        suggested_fixes=diagnosis_data.get("suggested_fixes", []),
    )

    # Get strategy and apply
    strategy = get_strategy_for_error(project_dir, diagnosis)

    if strategy is None:
        logger.error("Could not find strategy to apply fix")
        return {
            "current_fix_attempt": {
                **current_fix,
                "error": "No strategy available",
            },
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    # Create plan object
    from ...fixer import FixAction, FixPlan

    plan = FixPlan(
        diagnosis=diagnosis,
        strategy_name=plan_data.get("strategy_name", "unknown"),
        actions=[
            FixAction(
                action_type=a.get("action_type", "unknown"),
                target=a.get("target", ""),
                params=a.get("params", {}),
                description=a.get("description", ""),
                rollback=a.get("rollback"),
            )
            for a in plan_data.get("actions", [])
        ],
        estimated_impact=plan_data.get("estimated_impact", 1),
        requires_validation=plan_data.get("requires_validation", False),
        requires_security_notification=plan_data.get("requires_security_notification", False),
        confidence=plan_data.get("confidence", 0.5),
    )

    # Apply the fix
    result = strategy.apply(plan)

    logger.info(
        f"Fix applied: status={result.status.value}, "
        f"actions_completed={result.actions_completed}/{result.actions_total}"
    )

    # Update circuit breaker
    circuit_breaker = CircuitBreaker(workflow_dir)
    if result.success:
        circuit_breaker.record_success()
    else:
        circuit_breaker.record_failure(result.error)

    # Build state updates
    updated_fix = {
        **current_fix,
        "result": result.to_dict(),
        "backup_dir": str(backup_dir),
        "backups_created": backups_created,
    }

    if result.success:
        return {
            "current_fix_attempt": updated_fix,
            "fixer_circuit_breaker_open": circuit_breaker.is_open,
            "next_decision": "verify",
            "updated_at": datetime.now().isoformat(),
        }
    else:
        # Attempt rollback
        if backups_created:
            _restore_backups(project_dir, backups_created, backup_dir)
            logger.info("Rolled back changes from backups")

        return {
            "current_fix_attempt": updated_fix,
            "fixer_circuit_breaker_open": circuit_breaker.is_open,
            "errors": [
                {
                    "type": "fixer_apply_failed",
                    "message": f"Fix application failed: {result.error}",
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }


def _create_backups(
    project_dir: Path,
    files: list[str],
    backup_dir: Path,
) -> dict[str, str]:
    """Create backups of files before modification.

    Returns:
        Dict mapping original path to backup path
    """
    backups = {}

    for file_path in files:
        src = project_dir / file_path
        if src.exists():
            # Create backup with same directory structure
            backup_path = backup_dir / file_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, backup_path)
            backups[file_path] = str(backup_path)
            logger.debug(f"Backed up: {file_path}")

    return backups


def _restore_backups(
    project_dir: Path,
    backups: dict[str, str],
    backup_dir: Path,
) -> None:
    """Restore files from backups."""
    for original_path, backup_path in backups.items():
        src = Path(backup_path)
        dst = project_dir / original_path
        if src.exists():
            shutil.copy2(src, dst)
            logger.debug(f"Restored: {original_path}")
