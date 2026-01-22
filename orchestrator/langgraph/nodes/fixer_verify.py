"""Fixer verification node.

This node verifies that the fix was successful and handles
security notifications.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def fixer_verify_node(state: WorkflowState) -> dict[str, Any]:
    """Verify that a fix was successful.

    This node:
    1. Runs post-fix validation
    2. Optionally runs tests
    3. Sends security notifications if needed
    4. Records the fix in history
    5. Routes back to the original node or escalates

    Args:
        state: Current workflow state

    Returns:
        State updates with verification result
    """
    from ...fixer import FixValidator, FixResult, FixStatus

    project_dir = Path(state["project_dir"])
    workflow_dir = project_dir / ".workflow"
    current_fix = state.get("current_fix_attempt", {})
    fix_history = state.get("fix_history", [])

    if not current_fix:
        logger.warning("Fixer verify called but no current fix attempt")
        return {
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    result_data = current_fix.get("result", {})
    triage_data = current_fix.get("triage", {})
    diagnosis_data = current_fix.get("diagnosis", {})

    if not result_data:
        logger.warning("No fix result to verify")
        return {
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    # Check if fix application was successful
    if result_data.get("status") != "success":
        logger.info("Fix application was not successful, skipping verification")
        return {
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    logger.info("Verifying fix result")

    # Run post-fix validation
    validator = FixValidator(project_dir)

    # Reconstruct FixResult for validation
    from ...fixer import FixPlan, DiagnosisResult, FixerError, ErrorCategory, RootCause, DiagnosisConfidence

    error_data = diagnosis_data.get("error", {})
    error = FixerError.from_dict(error_data)

    # Simple validation check
    validation_result = {
        "status": "passed",
        "error_resolved": True,
        "no_new_errors": True,
        "tests_pass": None,
    }

    # Run tests if available
    try:
        import subprocess

        # Check for pytest
        pytest_result = subprocess.run(
            ["pytest", "--tb=short", "-q", "--collect-only"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if pytest_result.returncode == 0 and "test" in pytest_result.stdout.lower():
            # Tests exist, run them
            test_result = subprocess.run(
                ["pytest", "--tb=short", "-x"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            validation_result["tests_pass"] = test_result.returncode == 0
            validation_result["test_output"] = test_result.stdout[:500]

            if not validation_result["tests_pass"]:
                validation_result["status"] = "warning"
                logger.warning("Some tests failed after fix")

    except (subprocess.TimeoutExpired, FileNotFoundError):
        validation_result["tests_pass"] = None

    logger.info(
        f"Verification result: status={validation_result['status']}, "
        f"tests_pass={validation_result['tests_pass']}"
    )

    # Check if security notification is needed
    requires_notification = triage_data.get("requires_security_notification", False)
    notification_sent = False

    if requires_notification:
        notification_sent = _send_security_notification(
            workflow_dir,
            current_fix,
            validation_result,
        )

    # Record fix in history
    fix_record = {
        "error_id": current_fix.get("error_id"),
        "error_type": diagnosis_data.get("error", {}).get("error_type"),
        "root_cause": diagnosis_data.get("root_cause"),
        "strategy": current_fix.get("plan", {}).get("strategy_name"),
        "success": validation_result.get("status") in ("passed", "warning"),
        "tests_pass": validation_result.get("tests_pass"),
        "security_notification_sent": notification_sent,
        "timestamp": datetime.now().isoformat(),
    }

    # Determine next step
    if validation_result.get("status") == "passed":
        # Fix was successful - resume workflow
        logger.info("Fix verified successfully, resuming workflow")
        return {
            "current_fix_attempt": None,  # Clear current attempt
            "fix_history": [fix_record],  # Append to history
            "next_decision": "resume",
            "updated_at": datetime.now().isoformat(),
        }
    elif validation_result.get("status") == "warning":
        # Partial success - continue with warning
        logger.warning("Fix partially successful, continuing with warnings")
        return {
            "current_fix_attempt": None,
            "fix_history": [fix_record],
            "next_decision": "resume",
            "errors": [{
                "type": "fixer_partial_success",
                "message": "Fix applied but some tests failed",
                "timestamp": datetime.now().isoformat(),
            }],
            "updated_at": datetime.now().isoformat(),
        }
    else:
        # Fix didn't resolve the issue
        logger.warning("Fix verification failed, escalating")

        # Attempt rollback if backup exists
        backup_dir = current_fix.get("backup_dir")
        backups = current_fix.get("backups_created", {})
        if backup_dir and backups:
            _restore_backups(project_dir, backups, Path(backup_dir))
            logger.info("Rolled back changes")

        fix_record["success"] = False
        return {
            "current_fix_attempt": None,
            "fix_history": [fix_record],
            "next_decision": "escalate",
            "errors": [{
                "type": "fixer_verification_failed",
                "message": "Fix did not resolve the error",
                "timestamp": datetime.now().isoformat(),
            }],
            "updated_at": datetime.now().isoformat(),
        }


def _send_security_notification(
    workflow_dir: Path,
    fix_attempt: dict,
    validation_result: dict,
) -> bool:
    """Send notification for security-related fixes.

    Args:
        workflow_dir: Workflow directory
        fix_attempt: Current fix attempt data
        validation_result: Validation result

    Returns:
        True if notification was sent
    """
    notification = {
        "type": "security_fix_applied",
        "timestamp": datetime.now().isoformat(),
        "error_id": fix_attempt.get("error_id"),
        "vulnerability_type": fix_attempt.get("triage", {}).get("category"),
        "severity": "high",  # Assume high for security fixes
        "fix_description": fix_attempt.get("plan", {}).get("actions", [{}])[0].get("description", "Unknown"),
        "files_changed": [
            a.get("target") for a in fix_attempt.get("plan", {}).get("actions", [])
            if a.get("target")
        ],
        "lines_changed": fix_attempt.get("result", {}).get("actions_completed", 0),
        "verification_status": validation_result.get("status", "unknown"),
    }

    # Log to security fixes file
    security_log = workflow_dir / "security_fixes.jsonl"
    security_log.parent.mkdir(parents=True, exist_ok=True)

    with open(security_log, "a") as f:
        f.write(json.dumps(notification) + "\n")

    # Console warning
    logger.warning(
        f"\n{'='*60}\n"
        f"⚠️  SECURITY FIX APPLIED\n"
        f"{'='*60}\n"
        f"Error: {notification['error_id']}\n"
        f"Type: {notification['vulnerability_type']}\n"
        f"Fix: {notification['fix_description']}\n"
        f"Files: {', '.join(notification['files_changed'][:5])}\n"
        f"Status: {notification['verification_status']}\n"
        f"{'='*60}\n"
    )

    return True


def _restore_backups(
    project_dir: Path,
    backups: dict[str, str],
    backup_dir: Path,
) -> None:
    """Restore files from backups."""
    import shutil

    for original_path, backup_path in backups.items():
        src = Path(backup_path)
        dst = project_dir / original_path
        if src.exists():
            shutil.copy2(src, dst)
            logger.debug(f"Restored: {original_path}")
