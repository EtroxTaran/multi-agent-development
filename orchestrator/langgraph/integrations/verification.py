"""Verification strategy layer for unified loop execution.

Provides pluggable verification strategies that can be used to validate
task implementation. Each strategy has a specific focus (tests, linting,
security) and can be composed together.

Usage:
    from orchestrator.langgraph.integrations.verification import (
        create_verifier,
        VerificationType,
    )

    verifier = create_verifier(VerificationType.TESTS, project_dir)
    result = await verifier.verify(context)

    if result.passed:
        print("Verification passed!")
    else:
        print(f"Failures: {result.failures}")
"""

import asyncio
import json
import logging
import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class VerificationType(str, Enum):
    """Types of verification strategies."""

    TESTS = "tests"
    LINT = "lint"
    SECURITY = "security"
    COMPOSITE = "composite"
    NONE = "none"


@dataclass
class VerificationResult:
    """Result from a verification strategy.

    Attributes:
        passed: Whether verification passed
        verification_type: Type of verification performed
        summary: Human-readable summary
        failures: List of failure descriptions
        warnings: List of warning descriptions
        details: Additional verification details
        duration_seconds: Time taken for verification
        command_output: Raw command output
    """

    passed: bool
    verification_type: VerificationType
    summary: str = ""
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    command_output: str = ""

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "passed": self.passed,
            "verification_type": self.verification_type.value,
            "summary": self.summary,
            "failures": self.failures,
            "warnings": self.warnings,
            "details": self.details,
            "duration_seconds": self.duration_seconds,
            "timestamp": datetime.now().isoformat(),
        }


@dataclass
class VerificationContext:
    """Context for verification.

    Attributes:
        project_dir: Project directory
        test_files: Specific test files to run
        source_files: Source files that were changed
        task_id: Task identifier
        iteration: Current loop iteration
        previous_failures: Failures from previous iteration
        timeout: Timeout in seconds
    """

    project_dir: Path
    test_files: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    task_id: str = ""
    iteration: int = 0
    previous_failures: list[str] = field(default_factory=list)
    timeout: int = 60


class VerificationStrategy(ABC):
    """Base class for verification strategies."""

    def __init__(self, project_dir: Path, timeout: int = 60):
        """Initialize the verification strategy.

        Args:
            project_dir: Project directory
            timeout: Default timeout in seconds
        """
        self.project_dir = Path(project_dir)
        self.timeout = timeout

    @property
    @abstractmethod
    def verification_type(self) -> VerificationType:
        """Get the verification type."""
        pass

    @abstractmethod
    async def verify(self, context: VerificationContext) -> VerificationResult:
        """Run verification.

        Args:
            context: Verification context

        Returns:
            VerificationResult with results
        """
        pass

    async def _run_command(
        self,
        cmd: list[str],
        timeout: Optional[int] = None,
        cwd: Optional[Path] = None,
    ) -> tuple[int, str, str]:
        """Run a command and capture output.

        Args:
            cmd: Command to run
            timeout: Timeout in seconds
            cwd: Working directory

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        timeout = timeout or self.timeout
        cwd = cwd or self.project_dir

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            return (
                process.returncode or 0,
                stdout.decode() if stdout else "",
                stderr.decode() if stderr else "",
            )

        except asyncio.TimeoutError:
            return (-1, "", f"Command timed out after {timeout} seconds")
        except FileNotFoundError as e:
            return (-1, "", f"Command not found: {e}")
        except Exception as e:
            return (-1, "", f"Error running command: {e}")


class TestVerification(VerificationStrategy):
    """Run tests to verify implementation.

    Supports multiple test frameworks:
    - pytest (Python)
    - jest/vitest (JavaScript/TypeScript)
    - bun test (Bun)
    - cargo test (Rust)
    - go test (Go)
    """

    @property
    def verification_type(self) -> VerificationType:
        return VerificationType.TESTS

    async def verify(self, context: VerificationContext) -> VerificationResult:
        """Run tests and check results."""
        start_time = datetime.now()

        # Detect test framework
        test_cmd = self._detect_test_framework()

        # Build command with specific test files if provided
        if context.test_files:
            cmd = self._build_test_command(test_cmd, context.test_files)
        else:
            cmd = test_cmd.split()

        return_code, stdout, stderr = await self._run_command(
            cmd,
            timeout=context.timeout or self.timeout,
        )

        duration = (datetime.now() - start_time).total_seconds()

        # Parse test results
        passed = return_code == 0
        summary = self._extract_test_summary(stdout, stderr)
        failures = self._extract_test_failures(stdout, stderr)

        return VerificationResult(
            passed=passed,
            verification_type=self.verification_type,
            summary=summary,
            failures=failures,
            details={
                "test_command": " ".join(cmd),
                "return_code": return_code,
                "test_files": context.test_files,
            },
            duration_seconds=duration,
            command_output=stdout + stderr,
        )

    def _detect_test_framework(self) -> str:
        """Detect the test framework used in the project."""
        # Check for Python test config
        if (self.project_dir / "pytest.ini").exists():
            return "pytest -v --tb=short"
        if (self.project_dir / "pyproject.toml").exists():
            pyproject = (self.project_dir / "pyproject.toml").read_text()
            if "[tool.pytest" in pyproject:
                return "pytest -v --tb=short"

        # Check for JavaScript/TypeScript
        if (self.project_dir / "package.json").exists():
            try:
                pkg = json.loads((self.project_dir / "package.json").read_text())
                devdeps = pkg.get("devDependencies", {})
                deps = pkg.get("dependencies", {})
                all_deps = {**deps, **devdeps}

                if "bun" in all_deps:
                    return "bun test"
                if "vitest" in all_deps:
                    return "npm test"
                if "jest" in all_deps:
                    return "npm test"
            except json.JSONDecodeError:
                pass

        # Check for Rust
        if (self.project_dir / "Cargo.toml").exists():
            return "cargo test"

        # Check for Go
        if (self.project_dir / "go.mod").exists():
            return "go test ./..."

        # Default to pytest
        return "pytest -v --tb=short"

    def _build_test_command(self, base_cmd: str, test_files: list[str]) -> list[str]:
        """Build test command with specific test files."""
        cmd_parts = base_cmd.split()

        if base_cmd.startswith("pytest"):
            return cmd_parts + test_files
        elif "npm" in base_cmd:
            return cmd_parts + ["--"] + test_files
        elif "bun" in base_cmd:
            return cmd_parts + test_files
        elif "cargo" in base_cmd:
            # Cargo test takes test names, not files
            return cmd_parts
        elif "go" in base_cmd:
            return cmd_parts

        return cmd_parts + test_files

    def _extract_test_summary(self, stdout: str, stderr: str) -> str:
        """Extract test summary from output."""
        output = stdout + stderr

        # Pytest summary
        pytest_match = re.search(r"=+ (\d+ passed.*?) =+", output)
        if pytest_match:
            return pytest_match.group(1)

        # Jest/Vitest summary
        jest_match = re.search(r"Tests:\s+(.+?)(?:\n|$)", output)
        if jest_match:
            return jest_match.group(1).strip()

        # Count pass/fail
        passed = len(re.findall(r"PASSED|✓|✔", output, re.IGNORECASE))
        failed = len(re.findall(r"FAILED|✕|✖", output, re.IGNORECASE))

        if passed or failed:
            return f"{passed} passed, {failed} failed"

        return "No test summary available"

    def _extract_test_failures(self, stdout: str, stderr: str) -> list[str]:
        """Extract failing test names from output."""
        output = stdout + stderr
        failures = []

        # Pytest failures
        pytest_failures = re.findall(r"FAILED\s+(\S+)", output)
        failures.extend(pytest_failures)

        # Jest failures
        jest_failures = re.findall(r"✕\s+(.+?)(?:\n|$)", output)
        failures.extend(jest_failures)

        return failures[:10]  # Limit to 10


class LintVerification(VerificationStrategy):
    """Run linters to verify code quality.

    Supports multiple linters:
    - ruff (Python)
    - eslint (JavaScript/TypeScript)
    - clippy (Rust)
    - golangci-lint (Go)
    """

    @property
    def verification_type(self) -> VerificationType:
        return VerificationType.LINT

    async def verify(self, context: VerificationContext) -> VerificationResult:
        """Run linters and check results."""
        start_time = datetime.now()

        # Detect linter
        lint_cmd = self._detect_linter()

        # Build command with source files if provided
        if context.source_files:
            cmd = self._build_lint_command(lint_cmd, context.source_files)
        else:
            cmd = lint_cmd.split()

        return_code, stdout, stderr = await self._run_command(
            cmd,
            timeout=context.timeout or self.timeout,
        )

        duration = (datetime.now() - start_time).total_seconds()

        # Parse lint results
        passed = return_code == 0
        failures = self._extract_lint_errors(stdout, stderr)
        warnings = self._extract_lint_warnings(stdout, stderr)

        summary = f"{len(failures)} errors, {len(warnings)} warnings"
        if passed:
            summary = "No lint errors"

        return VerificationResult(
            passed=passed,
            verification_type=self.verification_type,
            summary=summary,
            failures=failures,
            warnings=warnings,
            details={
                "lint_command": " ".join(cmd),
                "return_code": return_code,
                "source_files": context.source_files,
            },
            duration_seconds=duration,
            command_output=stdout + stderr,
        )

    def _detect_linter(self) -> str:
        """Detect the linter used in the project."""
        # Check for Python linters
        if shutil.which("ruff"):
            if (self.project_dir / "pyproject.toml").exists():
                return "ruff check ."
            if (self.project_dir / "ruff.toml").exists():
                return "ruff check ."

        # Check for ESLint
        if (
            (self.project_dir / ".eslintrc.js").exists()
            or (self.project_dir / ".eslintrc.json").exists()
            or (self.project_dir / "eslint.config.js").exists()
        ):
            return "npm run lint"

        # Check for Rust
        if (self.project_dir / "Cargo.toml").exists():
            return "cargo clippy -- -D warnings"

        # Check for Go
        if (self.project_dir / "go.mod").exists():
            if shutil.which("golangci-lint"):
                return "golangci-lint run"

        # Default to ruff if available
        if shutil.which("ruff"):
            return "ruff check ."

        return "echo 'No linter configured'"

    def _build_lint_command(self, base_cmd: str, source_files: list[str]) -> list[str]:
        """Build lint command with specific source files."""
        cmd_parts = base_cmd.split()

        if "ruff" in base_cmd:
            # Replace . with specific files
            if "." in cmd_parts:
                cmd_parts.remove(".")
            return cmd_parts + source_files

        return cmd_parts

    def _extract_lint_errors(self, stdout: str, stderr: str) -> list[str]:
        """Extract lint errors from output."""
        output = stdout + stderr
        errors = []

        # Ruff format: file:line:col: E### description
        ruff_errors = re.findall(r"([^\s]+:\d+:\d+:.*?(?:E|F)\d+.*?)(?:\n|$)", output)
        errors.extend(ruff_errors)

        # ESLint format: file:line:col: error description
        eslint_errors = re.findall(r"(\d+:\d+\s+error\s+.+?)(?:\n|$)", output)
        errors.extend(eslint_errors)

        return errors[:20]  # Limit to 20

    def _extract_lint_warnings(self, stdout: str, stderr: str) -> list[str]:
        """Extract lint warnings from output."""
        output = stdout + stderr
        warnings = []

        # Ruff warnings
        ruff_warnings = re.findall(r"([^\s]+:\d+:\d+:.*?(?:W)\d+.*?)(?:\n|$)", output)
        warnings.extend(ruff_warnings)

        # ESLint warnings
        eslint_warnings = re.findall(r"(\d+:\d+\s+warning\s+.+?)(?:\n|$)", output)
        warnings.extend(eslint_warnings)

        return warnings[:10]


class SecurityVerification(VerificationStrategy):
    """Run security scans to verify implementation.

    Supports:
    - bandit (Python)
    - npm audit (JavaScript)
    - cargo audit (Rust)
    - semgrep (multi-language)
    """

    @property
    def verification_type(self) -> VerificationType:
        return VerificationType.SECURITY

    async def verify(self, context: VerificationContext) -> VerificationResult:
        """Run security scan and check results."""
        start_time = datetime.now()

        # Detect security scanner
        security_cmd = self._detect_scanner()

        if security_cmd == "echo 'No security scanner configured'":
            return VerificationResult(
                passed=True,
                verification_type=self.verification_type,
                summary="No security scanner configured",
                warnings=["No security scanner available"],
                duration_seconds=0.0,
            )

        cmd = security_cmd.split()

        return_code, stdout, stderr = await self._run_command(
            cmd,
            timeout=context.timeout or 120,  # Security scans can take longer
        )

        duration = (datetime.now() - start_time).total_seconds()

        # Parse security results
        issues = self._extract_security_issues(stdout, stderr)
        passed = (
            return_code == 0 and len([i for i in issues if "HIGH" in i or "CRITICAL" in i]) == 0
        )

        summary = f"{len(issues)} security issues found"
        if passed and not issues:
            summary = "No security issues found"

        return VerificationResult(
            passed=passed,
            verification_type=self.verification_type,
            summary=summary,
            failures=[i for i in issues if "HIGH" in i or "CRITICAL" in i],
            warnings=[i for i in issues if "HIGH" not in i and "CRITICAL" not in i],
            details={
                "security_command": " ".join(cmd),
                "return_code": return_code,
            },
            duration_seconds=duration,
            command_output=stdout + stderr,
        )

    def _detect_scanner(self) -> str:
        """Detect security scanner for the project."""
        # Check for Python
        if shutil.which("bandit"):
            if (self.project_dir / "pyproject.toml").exists() or any(self.project_dir.glob("*.py")):
                return "bandit -r . -ll"

        # Check for JavaScript
        if (self.project_dir / "package.json").exists():
            return "npm audit --audit-level=high"

        # Check for Rust
        if (self.project_dir / "Cargo.toml").exists():
            if shutil.which("cargo-audit"):
                return "cargo audit"

        # Check for semgrep (multi-language)
        if shutil.which("semgrep"):
            return "semgrep --config=auto ."

        return "echo 'No security scanner configured'"

    def _extract_security_issues(self, stdout: str, stderr: str) -> list[str]:
        """Extract security issues from output."""
        output = stdout + stderr
        issues = []

        # Bandit format
        bandit_issues = re.findall(r"(>>\s+Issue:.*?)(?:\n|$)", output)
        issues.extend(bandit_issues)

        # npm audit format
        npm_issues = re.findall(r"(\w+\s+Severity:\s+\w+)", output)
        issues.extend(npm_issues)

        # Semgrep format
        semgrep_issues = re.findall(r"(severity:\w+\s+.*?)(?:\n|$)", output, re.IGNORECASE)
        issues.extend(semgrep_issues)

        return issues[:20]


class CompositeVerification(VerificationStrategy):
    """Run multiple verification strategies together.

    Can be configured to require all strategies to pass,
    or just a subset.
    """

    def __init__(
        self,
        project_dir: Path,
        strategies: Optional[list[VerificationStrategy]] = None,
        require_all: bool = True,
        timeout: int = 180,
    ):
        """Initialize composite verification.

        Args:
            project_dir: Project directory
            strategies: List of strategies to run
            require_all: Whether all strategies must pass
            timeout: Total timeout for all strategies
        """
        super().__init__(project_dir, timeout)
        self.strategies = strategies or []
        self.require_all = require_all

    @property
    def verification_type(self) -> VerificationType:
        return VerificationType.COMPOSITE

    def add_strategy(self, strategy: VerificationStrategy) -> None:
        """Add a verification strategy."""
        self.strategies.append(strategy)

    async def verify(self, context: VerificationContext) -> VerificationResult:
        """Run all strategies and aggregate results."""
        start_time = datetime.now()

        if not self.strategies:
            return VerificationResult(
                passed=True,
                verification_type=self.verification_type,
                summary="No verification strategies configured",
                duration_seconds=0.0,
            )

        # Run all strategies
        results: list[VerificationResult] = []
        for strategy in self.strategies:
            result = await strategy.verify(context)
            results.append(result)

        duration = (datetime.now() - start_time).total_seconds()

        # Aggregate results
        all_failures = []
        all_warnings = []
        summaries = []

        for result in results:
            all_failures.extend(result.failures)
            all_warnings.extend(result.warnings)
            summaries.append(f"{result.verification_type.value}: {result.summary}")

        if self.require_all:
            passed = all(r.passed for r in results)
        else:
            passed = any(r.passed for r in results)

        return VerificationResult(
            passed=passed,
            verification_type=self.verification_type,
            summary="; ".join(summaries),
            failures=all_failures,
            warnings=all_warnings,
            details={
                "strategies": [s.verification_type.value for s in self.strategies],
                "individual_results": [r.to_dict() for r in results],
                "require_all": self.require_all,
            },
            duration_seconds=duration,
        )


class NoVerification(VerificationStrategy):
    """No-op verification that always passes.

    Useful for tasks that don't need verification.
    """

    @property
    def verification_type(self) -> VerificationType:
        return VerificationType.NONE

    async def verify(self, context: VerificationContext) -> VerificationResult:
        """Always return passed."""
        return VerificationResult(
            passed=True,
            verification_type=self.verification_type,
            summary="No verification required",
            duration_seconds=0.0,
        )


# Strategy registry
STRATEGY_REGISTRY: dict[VerificationType, type[VerificationStrategy]] = {
    VerificationType.TESTS: TestVerification,
    VerificationType.LINT: LintVerification,
    VerificationType.SECURITY: SecurityVerification,
    VerificationType.NONE: NoVerification,
}


def create_verifier(
    verification_type: VerificationType | str,
    project_dir: Path,
    timeout: int = 60,
) -> VerificationStrategy:
    """Create a verification strategy by type.

    Args:
        verification_type: Type of verification
        project_dir: Project directory
        timeout: Timeout in seconds

    Returns:
        Configured verification strategy
    """
    if isinstance(verification_type, str):
        try:
            verification_type = VerificationType(verification_type.lower())
        except ValueError:
            raise ValueError(
                f"Unknown verification type: {verification_type}. "
                f"Available: {[t.value for t in VerificationType]}"
            )

    if verification_type == VerificationType.COMPOSITE:
        # For composite, create with default strategies
        return create_composite_verifier(project_dir, timeout)

    strategy_class = STRATEGY_REGISTRY.get(verification_type)
    if not strategy_class:
        raise ValueError(f"No strategy for verification type: {verification_type}")

    return strategy_class(project_dir, timeout=timeout)


def create_composite_verifier(
    project_dir: Path,
    timeout: int = 180,
    include_tests: bool = True,
    include_lint: bool = True,
    include_security: bool = False,
    require_all: bool = True,
) -> CompositeVerification:
    """Create a composite verifier with configurable strategies.

    Args:
        project_dir: Project directory
        timeout: Total timeout
        include_tests: Include test verification
        include_lint: Include lint verification
        include_security: Include security verification
        require_all: Require all strategies to pass

    Returns:
        Configured CompositeVerification
    """
    strategies = []

    if include_tests:
        strategies.append(TestVerification(project_dir))
    if include_lint:
        strategies.append(LintVerification(project_dir))
    if include_security:
        strategies.append(SecurityVerification(project_dir))

    return CompositeVerification(
        project_dir,
        strategies=strategies,
        require_all=require_all,
        timeout=timeout,
    )
