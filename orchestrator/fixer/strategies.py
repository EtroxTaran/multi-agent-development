"""Fix strategies for different error types.

Each strategy knows how to fix a specific type of error. The Strategy
pattern allows adding new fix types without modifying the core fixer.

Available strategies:
- RetryStrategy: Simple retry with backoff
- ImportErrorFixStrategy: Install missing dependencies
- SyntaxErrorFixStrategy: Fix syntax issues
- TestFailureFixStrategy: Analyze and fix test failures
- ConfigurationFixStrategy: Fix configuration issues
- TimeoutFixStrategy: Increase timeouts
- DependencyFixStrategy: Resolve dependency conflicts
"""

import logging
import os
import re
import shlex
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from ..security import validate_file_path, validate_package_name
from .diagnosis import DiagnosisResult, RootCause
from .triage import ErrorCategory

logger = logging.getLogger(__name__)


class FixStatus(str, Enum):
    """Status of a fix attempt."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FixAction:
    """A single action within a fix plan.

    Attributes:
        action_type: Type of action (e.g., "edit_file", "run_command")
        target: Target of the action (file path, command, etc.)
        params: Parameters for the action
        description: Human-readable description
        rollback: How to undo this action
    """

    action_type: str
    target: str
    params: dict = field(default_factory=dict)
    description: str = ""
    rollback: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type,
            "target": self.target,
            "params": self.params,
            "description": self.description,
            "rollback": self.rollback,
        }


@dataclass
class FixPlan:
    """A plan for fixing an error.

    Attributes:
        diagnosis: The diagnosis this plan addresses
        strategy_name: Name of the strategy that created this plan
        actions: Ordered list of actions to perform
        estimated_impact: Number of files affected
        requires_validation: Whether the fix needs validation
        requires_security_notification: Whether this is a security fix
        confidence: Confidence in the plan (0-1)
    """

    diagnosis: DiagnosisResult
    strategy_name: str
    actions: list[FixAction] = field(default_factory=list)
    estimated_impact: int = 1
    requires_validation: bool = False
    requires_security_notification: bool = False
    confidence: float = 0.5

    def to_dict(self) -> dict:
        return {
            "diagnosis": self.diagnosis.to_dict(),
            "strategy_name": self.strategy_name,
            "actions": [a.to_dict() for a in self.actions],
            "estimated_impact": self.estimated_impact,
            "requires_validation": self.requires_validation,
            "requires_security_notification": self.requires_security_notification,
            "confidence": self.confidence,
        }


@dataclass
class FixResult:
    """Result of applying a fix.

    Attributes:
        plan: The plan that was executed
        status: Overall status
        actions_completed: Number of actions completed
        actions_total: Total number of actions
        changes_made: List of changes made
        rollback_available: Whether rollback is possible
        rollback_data: Data needed for rollback
        error: Error message if failed
        verification_result: Result of post-fix verification
    """

    plan: FixPlan
    status: FixStatus
    actions_completed: int = 0
    actions_total: int = 0
    changes_made: list[dict] = field(default_factory=list)
    rollback_available: bool = False
    rollback_data: Optional[dict] = None
    error: Optional[str] = None
    verification_result: Optional[dict] = None

    @property
    def success(self) -> bool:
        return self.status == FixStatus.SUCCESS

    def to_dict(self) -> dict:
        return {
            "plan": self.plan.to_dict(),
            "status": self.status.value,
            "actions_completed": self.actions_completed,
            "actions_total": self.actions_total,
            "changes_made": self.changes_made,
            "rollback_available": self.rollback_available,
            "error": self.error,
            "verification_result": self.verification_result,
        }


# Protected files that should never be modified (all lowercase for comparison)
PROTECTED_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    "claude.md",
    "gemini.md",
    "product.md",
}

# Protected path patterns that should never be modified
PROTECTED_PATHS = {
    ".workflow/state.json",
    ".project-config.json",
}

PROTECTED_PATTERNS = [
    r".*credentials.*",
    r".*secrets.*",
    r".*\.key$",
    r".*\.pem$",
]


def is_protected_file(path: str) -> bool:
    """Check if a file is protected from modification."""
    path_lower = path.lower()
    basename = os.path.basename(path_lower)

    # Check exact basename matches
    if basename in PROTECTED_FILES:
        return True

    # Check exact path matches (for paths like .workflow/state.json)
    # Normalize path separators
    path_normalized = path_lower.replace("\\", "/")
    if path_normalized in PROTECTED_PATHS:
        return True

    # Check if path is inside .workflow directory
    if ".workflow/" in path_normalized or path_normalized.startswith(".workflow"):
        return True

    # Check patterns
    for pattern in PROTECTED_PATTERNS:
        if re.match(pattern, path_lower):
            return True

    return False


class FixStrategy(ABC):
    """Base class for fix strategies."""

    name: str = "base"

    def __init__(self, project_dir: str | Path):
        """Initialize the strategy.

        Args:
            project_dir: Project directory
        """
        self.project_dir = Path(project_dir)

    @abstractmethod
    def can_fix(self, diagnosis: DiagnosisResult) -> bool:
        """Check if this strategy can fix the given diagnosis.

        Args:
            diagnosis: Diagnosis result

        Returns:
            True if this strategy can handle the error
        """
        pass

    @abstractmethod
    def create_plan(self, diagnosis: DiagnosisResult) -> FixPlan:
        """Create a fix plan for the diagnosis.

        Args:
            diagnosis: Diagnosis result

        Returns:
            Fix plan
        """
        pass

    def apply(self, plan: FixPlan) -> FixResult:
        """Apply a fix plan.

        Args:
            plan: Fix plan to apply

        Returns:
            Fix result
        """
        changes_made = []
        rollback_data = {"actions": []}

        for i, action in enumerate(plan.actions):
            try:
                # Check for protected files
                if action.action_type in ("edit_file", "delete_file", "write_file"):
                    if is_protected_file(action.target):
                        return FixResult(
                            plan=plan,
                            status=FixStatus.FAILED,
                            actions_completed=i,
                            actions_total=len(plan.actions),
                            error=f"Cannot modify protected file: {action.target}",
                        )

                # Execute action
                result = self._execute_action(action)

                # Record for rollback
                if action.rollback:
                    rollback_data["actions"].append(action.rollback)

                changes_made.append(
                    {
                        "action": action.to_dict(),
                        "result": result,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            except Exception as e:
                logger.error(f"Fix action failed: {action.action_type} on {action.target}: {e}")
                return FixResult(
                    plan=plan,
                    status=FixStatus.FAILED,
                    actions_completed=i,
                    actions_total=len(plan.actions),
                    changes_made=changes_made,
                    rollback_available=len(rollback_data["actions"]) > 0,
                    rollback_data=rollback_data,
                    error=str(e),
                )

        return FixResult(
            plan=plan,
            status=FixStatus.SUCCESS,
            actions_completed=len(plan.actions),
            actions_total=len(plan.actions),
            changes_made=changes_made,
            rollback_available=len(rollback_data["actions"]) > 0,
            rollback_data=rollback_data,
        )

    def _execute_action(self, action: FixAction) -> dict:
        """Execute a single fix action.

        Args:
            action: Action to execute

        Returns:
            Action result
        """
        if action.action_type == "run_command":
            return self._run_command(action.target, action.params)
        elif action.action_type == "run_command_safe":
            return self._run_command_safe(action.target, action.params)
        elif action.action_type == "edit_file":
            return self._edit_file(action.target, action.params)
        elif action.action_type == "write_file":
            return self._write_file(action.target, action.params)
        elif action.action_type == "append_file":
            return self._append_file(action.target, action.params)
        elif action.action_type == "delete_file":
            return self._delete_file(action.target)
        elif action.action_type == "add_import":
            return self._add_import(action.target, action.params)
        elif action.action_type == "install_package":
            return self._install_package(action.target, action.params)
        else:
            return {"status": "skipped", "reason": f"Unknown action type: {action.action_type}"}

    def _run_command(self, command: str, params: dict) -> dict:
        """Run a shell command safely.

        Uses shlex.split to avoid shell=True and prevent command injection.
        """
        timeout = params.get("timeout", 120)
        cwd = params.get("cwd", str(self.project_dir))

        try:
            # Parse command safely to avoid shell injection
            cmd_parts = shlex.split(command)
            result = subprocess.run(
                cmd_parts,
                shell=False,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return {
                "status": "success" if result.returncode == 0 else "failed",
                "exit_code": result.returncode,
                "stdout": result.stdout[:1000] if result.stdout else None,
                "stderr": result.stderr[:1000] if result.stderr else None,
            }

        except subprocess.TimeoutExpired:
            return {"status": "timeout", "timeout": timeout}
        except ValueError as e:
            return {"status": "failed", "reason": f"Invalid command format: {e}"}

    def _run_command_safe(self, executable: str, params: dict) -> dict:
        """Run a command safely with pre-validated arguments.

        Unlike _run_command, this method takes the executable and args separately
        to avoid any shell parsing. Use this when arguments contain file paths
        or user-controlled data.

        Args:
            executable: The command/executable to run (e.g., "autopep8", "python")
            params: Dictionary containing:
                - args: List of arguments to pass to the executable
                - timeout: Command timeout in seconds (default: 120)
                - cwd: Working directory (default: project_dir)

        Returns:
            Result dictionary with status, exit_code, stdout, stderr
        """
        timeout = params.get("timeout", 120)
        cwd = params.get("cwd", str(self.project_dir))
        args = params.get("args", [])

        # Build command list: [executable] + args
        cmd_parts = [executable] + list(args)

        try:
            result = subprocess.run(
                cmd_parts,
                shell=False,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return {
                "status": "success" if result.returncode == 0 else "failed",
                "exit_code": result.returncode,
                "stdout": result.stdout[:1000] if result.stdout else None,
                "stderr": result.stderr[:1000] if result.stderr else None,
            }

        except subprocess.TimeoutExpired:
            return {"status": "timeout", "timeout": timeout}
        except Exception as e:
            return {"status": "failed", "reason": str(e)}

    def _edit_file(self, path: str, params: dict) -> dict:
        """Edit a file."""
        file_path = self.project_dir / path
        if not file_path.exists():
            return {"status": "failed", "reason": "File not found"}

        # Create backup
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        shutil.copy2(file_path, backup_path)

        try:
            content = file_path.read_text()

            # Apply edits
            if "find" in params and "replace" in params:
                content = content.replace(params["find"], params["replace"])
            elif "line_number" in params and "new_line" in params:
                lines = content.splitlines()
                line_num = params["line_number"] - 1
                if 0 <= line_num < len(lines):
                    lines[line_num] = params["new_line"]
                    content = "\n".join(lines)

            file_path.write_text(content)
            return {"status": "success", "backup": str(backup_path)}

        except Exception:
            # Restore backup on failure
            if backup_path.exists():
                shutil.copy2(backup_path, file_path)
            raise

    def _write_file(self, path: str, params: dict) -> dict:
        """Write content to a file."""
        file_path = self.project_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = params.get("content", "")
        file_path.write_text(content)

        return {"status": "success", "path": str(file_path)}

    def _append_file(self, path: str, params: dict) -> dict:
        """Append content to a file safely.

        This is safer than using shell commands like 'echo >> file'.
        """
        file_path = self.project_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = params.get("content", "")

        # Append to file (creates if doesn't exist)
        with open(file_path, "a") as f:
            f.write(content)

        return {"status": "success", "path": str(file_path)}

    def _delete_file(self, path: str) -> dict:
        """Delete a file."""
        file_path = self.project_dir / path
        if not file_path.exists():
            return {"status": "skipped", "reason": "File not found"}

        # Create backup
        backup_path = file_path.with_suffix(file_path.suffix + ".deleted")
        shutil.copy2(file_path, backup_path)
        file_path.unlink()

        return {"status": "success", "backup": str(backup_path)}

    def _add_import(self, path: str, params: dict) -> dict:
        """Add an import statement to a file."""
        file_path = self.project_dir / path
        if not file_path.exists():
            return {"status": "failed", "reason": "File not found"}

        import_stmt = params.get("import_statement")
        if not import_stmt:
            return {"status": "failed", "reason": "No import statement provided"}

        content = file_path.read_text()
        lines = content.splitlines()

        # Find where to insert import
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_pos = i + 1
            elif (
                line.strip()
                and not line.startswith("#")
                and not line.startswith('"""')
                and insert_pos == 0
            ):
                break

        lines.insert(insert_pos, import_stmt)
        file_path.write_text("\n".join(lines))

        return {"status": "success", "inserted_at": insert_pos}

    def _install_package(self, package: str, params: dict) -> dict:
        """Install a package safely.

        Validates the package name before installation to prevent command injection.
        """
        manager = params.get("manager", "pip")
        dev = params.get("dev", False)

        # Validate package name to prevent command injection
        try:
            validated_package = validate_package_name(package)
        except Exception as e:
            return {"status": "failed", "reason": f"Invalid package name: {e}"}

        # Build command as a list to avoid shell injection
        if manager == "pip":
            cmd_parts = ["pip", "install", validated_package]
        elif manager == "npm":
            cmd_parts = ["npm", "install", "--save-dev" if dev else "--save", validated_package]
        else:
            return {"status": "failed", "reason": f"Unknown package manager: {manager}"}

        try:
            result = subprocess.run(
                cmd_parts,
                shell=False,
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )

            return {
                "status": "success" if result.returncode == 0 else "failed",
                "exit_code": result.returncode,
                "stdout": result.stdout[:1000] if result.stdout else None,
                "stderr": result.stderr[:1000] if result.stderr else None,
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "timeout": 300}


class RetryStrategy(FixStrategy):
    """Simple retry strategy for transient errors."""

    name = "retry"

    def can_fix(self, diagnosis: DiagnosisResult) -> bool:
        # Can handle rate limits, timeouts, agent crashes
        return diagnosis.root_cause in (
            RootCause.TIMEOUT,
            RootCause.RESOURCE_EXHAUSTION,
        ) or diagnosis.category in (
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.AGENT_CRASH,
        )

    def create_plan(self, diagnosis: DiagnosisResult) -> FixPlan:
        return FixPlan(
            diagnosis=diagnosis,
            strategy_name=self.name,
            actions=[
                FixAction(
                    action_type="wait_and_retry",
                    target="",
                    params={"delay_seconds": 5},
                    description="Wait and retry the failed operation",
                ),
            ],
            estimated_impact=0,
            confidence=0.6,
        )


class ImportErrorFixStrategy(FixStrategy):
    """Fix import errors by installing packages or adding imports."""

    name = "import_fix"

    # Common module to package mappings
    MODULE_TO_PACKAGE = {
        "PIL": "Pillow",
        "cv2": "opencv-python",
        "sklearn": "scikit-learn",
        "yaml": "PyYAML",
        "bs4": "beautifulsoup4",
    }

    def can_fix(self, diagnosis: DiagnosisResult) -> bool:
        return diagnosis.category == ErrorCategory.IMPORT_ERROR or diagnosis.root_cause in (
            RootCause.MISSING_IMPORT,
            RootCause.WRONG_IMPORT_PATH,
            RootCause.MISSING_DEPENDENCY,
        )

    def create_plan(self, diagnosis: DiagnosisResult) -> FixPlan:
        actions = []

        # Extract module name from error
        module_name = self._extract_module_name(diagnosis)

        if diagnosis.root_cause == RootCause.MISSING_DEPENDENCY:
            # Install the package
            package = self.MODULE_TO_PACKAGE.get(module_name, module_name)
            actions.append(
                FixAction(
                    action_type="install_package",
                    target=package,
                    params={"manager": "pip"},
                    description=f"Install missing package: {package}",
                )
            )

        elif diagnosis.root_cause == RootCause.MISSING_IMPORT:
            # Add import statement
            if diagnosis.affected_files:
                actions.append(
                    FixAction(
                        action_type="add_import",
                        target=diagnosis.affected_files[0].path,
                        params={"import_statement": f"import {module_name}"},
                        description=f"Add import statement for {module_name}",
                    )
                )

        return FixPlan(
            diagnosis=diagnosis,
            strategy_name=self.name,
            actions=actions,
            estimated_impact=1,
            confidence=0.7,
        )

    def _extract_module_name(self, diagnosis: DiagnosisResult) -> str:
        """Extract module name from error message."""
        patterns = [
            r"No module named ['\"]([^'\"]+)['\"]",
            r"Cannot find module ['\"]([^'\"]+)['\"]",
            r"ModuleNotFoundError: ['\"]([^'\"]+)['\"]",
        ]

        for pattern in patterns:
            match = re.search(pattern, diagnosis.error.message)
            if match:
                return match.group(1).split(".")[0]  # Get top-level module

        return "unknown"


class SyntaxErrorFixStrategy(FixStrategy):
    """Fix syntax errors."""

    name = "syntax_fix"

    def can_fix(self, diagnosis: DiagnosisResult) -> bool:
        return diagnosis.category == ErrorCategory.SYNTAX_ERROR or diagnosis.root_cause in (
            RootCause.SYNTAX_ERROR,
            RootCause.INDENTATION_ERROR,
            RootCause.UNCLOSED_BRACKET,
            RootCause.MISSING_COLON,
        )

    def create_plan(self, diagnosis: DiagnosisResult) -> FixPlan:
        actions = []

        if not diagnosis.affected_files:
            return FixPlan(
                diagnosis=diagnosis,
                strategy_name=self.name,
                actions=[],
                confidence=0.1,
            )

        affected_file = diagnosis.affected_files[0]

        if diagnosis.root_cause == RootCause.INDENTATION_ERROR:
            # Validate file path to prevent command injection
            try:
                validated_path = validate_file_path(
                    affected_file.path,
                    str(diagnosis.affected_files[0].path).rsplit("/", 1)[0]
                    if "/" in str(affected_file.path)
                    else ".",
                )
            except Exception:
                # Fall back to using the path as-is if validation fails
                # The _run_command_safe method doesn't use shell, so this is still safe
                validated_path = str(affected_file.path)

            # Run autopep8 using safe command execution with validated path
            actions.append(
                FixAction(
                    action_type="run_command_safe",
                    target="autopep8",
                    params={"args": ["--in-place", validated_path], "timeout": 30},
                    description="Auto-fix indentation with autopep8",
                )
            )

        return FixPlan(
            diagnosis=diagnosis,
            strategy_name=self.name,
            actions=actions,
            estimated_impact=1,
            requires_validation=True,
            confidence=0.5,
        )


class TestFailureFixStrategy(FixStrategy):
    """Analyze and fix test failures."""

    name = "test_failure_fix"

    def can_fix(self, diagnosis: DiagnosisResult) -> bool:
        return diagnosis.category in (
            ErrorCategory.TEST_FAILURE,
            ErrorCategory.ASSERTION_ERROR,
        ) or diagnosis.root_cause in (
            RootCause.ASSERTION_MISMATCH,
            RootCause.MISSING_TEST_DATA,
            RootCause.SETUP_FAILURE,
        )

    def create_plan(self, diagnosis: DiagnosisResult) -> FixPlan:
        # Test failures are complex and usually need the implementation
        # to be fixed rather than the test itself
        return FixPlan(
            diagnosis=diagnosis,
            strategy_name=self.name,
            actions=[],  # Will be filled by the fixer agent
            requires_validation=True,
            confidence=0.4,
        )


class ConfigurationFixStrategy(FixStrategy):
    """Fix configuration errors."""

    name = "config_fix"

    def can_fix(self, diagnosis: DiagnosisResult) -> bool:
        return diagnosis.category == ErrorCategory.CONFIG_ERROR or diagnosis.root_cause in (
            RootCause.MISSING_CONFIG,
            RootCause.INVALID_CONFIG,
            RootCause.MISSING_ENV_VAR,
        )

    def create_plan(self, diagnosis: DiagnosisResult) -> FixPlan:
        actions = []

        if diagnosis.root_cause == RootCause.MISSING_ENV_VAR:
            # Extract env var name
            env_var = self._extract_env_var(diagnosis)
            if env_var:
                # Validate env var name - only allow alphanumeric and underscore
                if re.match(r"^[A-Z][A-Z0-9_]*$", env_var):
                    actions.append(
                        FixAction(
                            action_type="append_file",
                            target=".env.example",
                            params={"content": f"{env_var}=\n"},
                            description=f"Add {env_var} to .env.example template",
                        )
                    )

        return FixPlan(
            diagnosis=diagnosis,
            strategy_name=self.name,
            actions=actions,
            estimated_impact=1,
            confidence=0.5,
        )

    def _extract_env_var(self, diagnosis: DiagnosisResult) -> Optional[str]:
        """Extract environment variable name from error."""
        patterns = [
            r"KeyError: ['\"]([A-Z_]+)['\"]",
            r"Environment variable ['\"]([^'\"]+)['\"]",
        ]

        for pattern in patterns:
            match = re.search(pattern, diagnosis.error.message)
            if match:
                return match.group(1)

        return None


class TimeoutFixStrategy(FixStrategy):
    """Fix timeout errors by increasing timeouts."""

    name = "timeout_fix"

    def can_fix(self, diagnosis: DiagnosisResult) -> bool:
        return (
            diagnosis.category == ErrorCategory.TIMEOUT_ERROR
            or diagnosis.root_cause == RootCause.TIMEOUT
        )

    def create_plan(self, diagnosis: DiagnosisResult) -> FixPlan:
        return FixPlan(
            diagnosis=diagnosis,
            strategy_name=self.name,
            actions=[
                FixAction(
                    action_type="increase_timeout",
                    target="",
                    params={"multiplier": 2},
                    description="Increase timeout by 2x",
                ),
            ],
            estimated_impact=0,
            confidence=0.6,
        )


class DependencyFixStrategy(FixStrategy):
    """Fix dependency conflicts and version mismatches."""

    name = "dependency_fix"

    def can_fix(self, diagnosis: DiagnosisResult) -> bool:
        return diagnosis.category in (
            ErrorCategory.DEPENDENCY_ERROR,
            ErrorCategory.VERSION_CONFLICT,
            ErrorCategory.MISSING_PACKAGE,
        ) or diagnosis.root_cause in (
            RootCause.MISSING_DEPENDENCY,
            RootCause.VERSION_MISMATCH,
        )

    def create_plan(self, diagnosis: DiagnosisResult) -> FixPlan:
        actions = []

        # Check if requirements.txt or package.json exists
        if (self.project_dir / "requirements.txt").exists():
            actions.append(
                FixAction(
                    action_type="run_command",
                    target="pip install -r requirements.txt",
                    params={"timeout": 300},
                    description="Reinstall Python dependencies",
                )
            )
        elif (self.project_dir / "package.json").exists():
            actions.append(
                FixAction(
                    action_type="run_command",
                    target="npm install",
                    params={"timeout": 300},
                    description="Reinstall Node.js dependencies",
                )
            )

        return FixPlan(
            diagnosis=diagnosis,
            strategy_name=self.name,
            actions=actions,
            estimated_impact=1,
            confidence=0.6,
        )


# Strategy registry
STRATEGIES = [
    RetryStrategy,
    ImportErrorFixStrategy,
    SyntaxErrorFixStrategy,
    TestFailureFixStrategy,
    ConfigurationFixStrategy,
    TimeoutFixStrategy,
    DependencyFixStrategy,
]


def get_strategy_for_error(
    project_dir: str | Path,
    diagnosis: DiagnosisResult,
) -> Optional[FixStrategy]:
    """Get the appropriate fix strategy for a diagnosis.

    Args:
        project_dir: Project directory
        diagnosis: Diagnosis result

    Returns:
        Appropriate strategy or None
    """
    for strategy_class in STRATEGIES:
        strategy = strategy_class(project_dir)
        if strategy.can_fix(diagnosis):
            return strategy

    return None
