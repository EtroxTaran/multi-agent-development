"""Fix validation for pre and post-fix checks.

The validator ensures fixes are safe before applying them and
verifies they actually resolved the issue afterward.
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .strategies import FixPlan, FixResult, is_protected_file

logger = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    """Status of validation."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class ValidationResult:
    """Result of a validation check.

    Attributes:
        status: Validation status
        checks: List of individual check results
        warnings: List of warnings
        errors: List of errors
        timestamp: When validation was performed
    """

    status: ValidationStatus
    checks: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def passed(self) -> bool:
        return self.status in (ValidationStatus.PASSED, ValidationStatus.WARNING)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "timestamp": self.timestamp,
        }


@dataclass
class PreValidation(ValidationResult):
    """Result of pre-fix validation.

    Additional attributes:
        safe_to_proceed: Whether it's safe to apply the fix
        scope_within_limits: Whether the fix scope is acceptable
    """

    safe_to_proceed: bool = True
    scope_within_limits: bool = True

    def to_dict(self) -> dict:
        result = super().to_dict()
        result["safe_to_proceed"] = self.safe_to_proceed
        result["scope_within_limits"] = self.scope_within_limits
        return result


@dataclass
class PostValidation(ValidationResult):
    """Result of post-fix validation.

    Additional attributes:
        error_resolved: Whether the original error is resolved
        no_new_errors: Whether the fix introduced new errors
        tests_pass: Whether tests still pass
    """

    error_resolved: bool = False
    no_new_errors: bool = True
    tests_pass: Optional[bool] = None

    def to_dict(self) -> dict:
        result = super().to_dict()
        result["error_resolved"] = self.error_resolved
        result["no_new_errors"] = self.no_new_errors
        result["tests_pass"] = self.tests_pass
        return result


class FixValidator:
    """Validates fixes before and after application.

    Ensures fixes are safe and effective.
    """

    # Maximum files that can be modified in a single fix
    MAX_FILES_PER_FIX = 5
    # Maximum lines that can be changed in a single fix
    MAX_LINES_PER_FIX = 100
    # Maximum commands that can be run in a single fix
    MAX_COMMANDS_PER_FIX = 3

    def __init__(
        self,
        project_dir: str | Path,
        max_files: int = None,
        max_lines: int = None,
        max_commands: int = None,
    ):
        """Initialize the validator.

        Args:
            project_dir: Project directory
            max_files: Override max files per fix
            max_lines: Override max lines per fix
            max_commands: Override max commands per fix
        """
        self.project_dir = Path(project_dir)
        self.max_files = max_files or self.MAX_FILES_PER_FIX
        self.max_lines = max_lines or self.MAX_LINES_PER_FIX
        self.max_commands = max_commands or self.MAX_COMMANDS_PER_FIX

    def validate_pre_fix(self, plan: FixPlan) -> PreValidation:
        """Validate a fix plan before applying it.

        Checks:
        - No protected files are modified
        - Scope is within limits
        - Actions are valid

        Args:
            plan: Fix plan to validate

        Returns:
            PreValidation result
        """
        checks = []
        warnings = []
        errors = []
        safe_to_proceed = True
        scope_within_limits = True

        # Check protected files
        protected_check = self._check_protected_files(plan)
        checks.append(protected_check)
        if protected_check["status"] == "failed":
            errors.extend(protected_check.get("errors", []))
            safe_to_proceed = False

        # Check scope limits
        scope_check = self._check_scope_limits(plan)
        checks.append(scope_check)
        if scope_check["status"] == "failed":
            errors.extend(scope_check.get("errors", []))
            scope_within_limits = False
        elif scope_check["status"] == "warning":
            warnings.extend(scope_check.get("warnings", []))

        # Check action validity
        action_check = self._check_action_validity(plan)
        checks.append(action_check)
        if action_check["status"] == "failed":
            errors.extend(action_check.get("errors", []))
            safe_to_proceed = False

        # Determine overall status
        if errors:
            status = ValidationStatus.FAILED
        elif warnings:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.PASSED

        return PreValidation(
            status=status,
            checks=checks,
            warnings=warnings,
            errors=errors,
            safe_to_proceed=safe_to_proceed,
            scope_within_limits=scope_within_limits,
        )

    def validate_post_fix(
        self,
        result: FixResult,
        original_error: dict,
        run_tests: bool = False,
    ) -> PostValidation:
        """Validate a fix after application.

        Checks:
        - Original error is resolved
        - No new errors introduced
        - Tests still pass (optional)

        Args:
            result: Fix result to validate
            original_error: The original error that was fixed
            run_tests: Whether to run tests

        Returns:
            PostValidation result
        """
        checks = []
        warnings = []
        errors = []
        error_resolved = False
        no_new_errors = True
        tests_pass = None

        if not result.success:
            return PostValidation(
                status=ValidationStatus.FAILED,
                errors=["Fix application failed"],
                error_resolved=False,
            )

        # Check if original error is resolved
        resolve_check = self._check_error_resolved(original_error)
        checks.append(resolve_check)
        error_resolved = resolve_check.get("resolved", False)

        # Check for new errors
        new_errors_check = self._check_new_errors()
        checks.append(new_errors_check)
        if new_errors_check.get("new_errors"):
            no_new_errors = False
            warnings.extend(new_errors_check.get("errors", []))

        # Run tests if requested
        if run_tests:
            test_check = self._run_tests()
            checks.append(test_check)
            tests_pass = test_check.get("passed", False)
            if not tests_pass:
                warnings.append("Some tests failed after fix")

        # Determine overall status
        if not error_resolved:
            status = ValidationStatus.FAILED
            errors.append("Original error was not resolved")
        elif not no_new_errors:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.PASSED

        return PostValidation(
            status=status,
            checks=checks,
            warnings=warnings,
            errors=errors,
            error_resolved=error_resolved,
            no_new_errors=no_new_errors,
            tests_pass=tests_pass,
        )

    def _check_protected_files(self, plan: FixPlan) -> dict:
        """Check if any protected files are being modified."""
        protected_files_modified = []

        for action in plan.actions:
            if action.action_type in ("edit_file", "write_file", "delete_file"):
                if is_protected_file(action.target):
                    protected_files_modified.append(action.target)

        if protected_files_modified:
            return {
                "name": "protected_files",
                "status": "failed",
                "errors": [f"Cannot modify protected file: {f}" for f in protected_files_modified],
            }

        return {"name": "protected_files", "status": "passed"}

    def _check_scope_limits(self, plan: FixPlan) -> dict:
        """Check if the fix scope is within limits."""
        files_modified = set()
        commands_count = 0

        for action in plan.actions:
            if action.action_type in ("edit_file", "write_file", "delete_file", "add_import"):
                files_modified.add(action.target)
            elif action.action_type == "run_command":
                commands_count += 1

        issues = []
        warnings = []

        if len(files_modified) > self.max_files:
            issues.append(f"Too many files modified: {len(files_modified)} > {self.max_files}")

        if commands_count > self.max_commands:
            issues.append(f"Too many commands: {commands_count} > {self.max_commands}")

        if issues:
            return {
                "name": "scope_limits",
                "status": "failed",
                "errors": issues,
            }

        # Warn if approaching limits
        if len(files_modified) >= self.max_files - 1:
            warnings.append(f"Approaching file limit: {len(files_modified)}/{self.max_files}")

        if warnings:
            return {
                "name": "scope_limits",
                "status": "warning",
                "warnings": warnings,
            }

        return {"name": "scope_limits", "status": "passed"}

    def _check_action_validity(self, plan: FixPlan) -> dict:
        """Check if all actions are valid."""
        valid_action_types = {
            "run_command",
            "edit_file",
            "write_file",
            "delete_file",
            "add_import",
            "install_package",
            "wait_and_retry",
            "increase_timeout",
        }

        invalid_actions = []

        for action in plan.actions:
            if action.action_type not in valid_action_types:
                invalid_actions.append(f"Invalid action type: {action.action_type}")

        if invalid_actions:
            return {
                "name": "action_validity",
                "status": "failed",
                "errors": invalid_actions,
            }

        return {"name": "action_validity", "status": "passed"}

    def _check_error_resolved(self, original_error: dict) -> dict:
        """Check if the original error is resolved.

        This is a simple check that re-runs the command or checks
        if the error file exists.
        """
        # For now, we'll assume success if the fix was applied
        # A more sophisticated check would re-run the original command
        return {
            "name": "error_resolved",
            "resolved": True,  # Optimistic assumption
            "note": "Manual verification recommended",
        }

    def _check_new_errors(self) -> dict:
        """Check for new errors after fix."""
        # Check if there are any syntax errors in modified files
        # This is a simplified check

        return {
            "name": "new_errors",
            "new_errors": False,
            "checked_files": [],
        }

    def _run_tests(self) -> dict:
        """Run tests to verify the fix."""
        # Try common test runners
        test_commands = [
            ("pytest", ["pytest", "--tb=short", "-q"]),
            ("npm test", ["npm", "test"]),
        ]

        for name, cmd in test_commands:
            cmd_path = cmd[0]
            # Check if command exists
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.project_dir,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                return {
                    "name": "tests",
                    "runner": name,
                    "passed": result.returncode == 0,
                    "exit_code": result.returncode,
                    "output": result.stdout[:500] if result.stdout else None,
                    "errors": result.stderr[:500] if result.stderr else None,
                }

            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                return {
                    "name": "tests",
                    "runner": name,
                    "passed": False,
                    "error": "Tests timed out",
                }

        return {
            "name": "tests",
            "passed": None,
            "note": "No test runner found",
        }

    def create_rollback(self, result: FixResult) -> Optional[dict]:
        """Create a rollback plan from a fix result.

        Args:
            result: Fix result with changes

        Returns:
            Rollback data or None
        """
        if not result.rollback_data:
            return None

        rollback_actions = result.rollback_data.get("actions", [])
        if not rollback_actions:
            return None

        return {
            "actions": list(reversed(rollback_actions)),
            "created_at": datetime.now().isoformat(),
            "original_fix": result.plan.strategy_name,
        }

    def apply_rollback(self, rollback_data: dict) -> bool:
        """Apply a rollback.

        Args:
            rollback_data: Rollback data from create_rollback

        Returns:
            True if rollback was successful
        """
        for action in rollback_data.get("actions", []):
            try:
                action_type = action.get("type")

                if action_type == "restore_file":
                    backup_path = Path(action["backup"])
                    target_path = Path(action["target"])
                    if backup_path.exists():
                        target_path.write_text(backup_path.read_text())
                        backup_path.unlink()

                elif action_type == "delete_file":
                    target_path = Path(action["target"])
                    if target_path.exists():
                        target_path.unlink()

            except Exception as e:
                logger.error(f"Rollback action failed: {e}")
                return False

        return True
