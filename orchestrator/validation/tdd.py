"""
TDD (Test-Driven Development) validator.

Ensures TDD discipline is followed throughout the workflow:
1. RED phase: Tests must exist and FAIL (no implementation yet)
2. GREEN phase: Implementation must make tests PASS
3. REFACTOR phase: Tests must stay GREEN after changes

Usage:
    from orchestrator.validation import TDDValidator

    validator = TDDValidator(project_dir)
    result = validator.validate_test_phase(test_files, acceptance_criteria)
    result = validator.validate_implement_phase(source_files, test_files)
"""

import asyncio
import logging
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TDDPhase(str, Enum):
    """Phases of TDD."""

    RED = "red"  # Tests fail (no implementation)
    GREEN = "green"  # Tests pass (minimal implementation)
    REFACTOR = "refactor"  # Tests still pass (improved code)


@dataclass
class TestResult:
    """Result of running a test suite."""

    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    total: int = 0
    coverage: float = 0.0
    execution_time_seconds: float = 0.0
    output: str = ""
    failed_tests: List[Dict[str, str]] = field(default_factory=list)

    @property
    def all_pass(self) -> bool:
        """Check if all tests passed."""
        return self.failed == 0 and self.errors == 0 and self.total > 0

    @property
    def all_fail(self) -> bool:
        """Check if all tests failed (or errored)."""
        return self.passed == 0 and (self.failed > 0 or self.errors > 0)


@dataclass
class TDDValidationResult:
    """Result of TDD validation."""

    valid: bool
    phase: TDDPhase
    message: str
    test_result: Optional[TestResult] = None
    criteria_coverage: float = 0.0
    uncovered_criteria: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "valid": self.valid,
            "phase": self.phase.value,
            "message": self.message,
            "criteria_coverage": self.criteria_coverage,
            "uncovered_criteria": self.uncovered_criteria,
            "issues": self.issues,
            "warnings": self.warnings,
            "test_result": {
                "passed": self.test_result.passed if self.test_result else 0,
                "failed": self.test_result.failed if self.test_result else 0,
                "total": self.test_result.total if self.test_result else 0,
                "all_pass": self.test_result.all_pass if self.test_result else False,
            },
        }


class TDDValidator:
    """Validates TDD discipline throughout the workflow."""

    # Test file patterns
    TEST_FILE_PATTERNS = [
        "**/test_*.py",
        "**/*_test.py",
        "**/tests/*.py",
        "**/test/*.py",
        "**/*.test.ts",
        "**/*.spec.ts",
        "**/*.test.js",
        "**/*.spec.js",
        "**/tests/**/*.ts",
        "**/tests/**/*.js",
    ]

    # Source file patterns (not tests)
    SOURCE_FILE_PATTERNS = [
        "src/**/*.py",
        "lib/**/*.py",
        "app/**/*.py",
        "src/**/*.ts",
        "src/**/*.js",
        "lib/**/*.ts",
        "lib/**/*.js",
    ]

    # Test runner commands by extension
    TEST_RUNNERS = {
        ".py": "pytest {files} -v --tb=short",
        ".ts": "npx jest {files} --verbose",
        ".js": "npx jest {files} --verbose",
    }

    # Coverage commands
    COVERAGE_RUNNERS = {
        ".py": "pytest {files} --cov={source_dir} --cov-report=term-missing -v",
        ".ts": "npx jest {files} --coverage --verbose",
        ".js": "npx jest {files} --coverage --verbose",
    }

    # Minimum coverage threshold
    COVERAGE_THRESHOLD = 80.0

    def __init__(
        self,
        project_dir: Path,
        coverage_threshold: float = COVERAGE_THRESHOLD,
    ):
        """Initialize TDD validator.

        Args:
            project_dir: Project directory
            coverage_threshold: Minimum required coverage percentage
        """
        self.project_dir = Path(project_dir)
        self.coverage_threshold = coverage_threshold

    async def run_tests(
        self,
        test_files: List[str],
        with_coverage: bool = False,
        source_dir: str = "src",
    ) -> TestResult:
        """Run tests and return results.

        Args:
            test_files: List of test file paths
            with_coverage: Whether to run with coverage
            source_dir: Source directory for coverage

        Returns:
            TestResult with test execution details
        """
        if not test_files:
            return TestResult(output="No test files provided")

        # Determine test runner based on file extension
        extensions = set(Path(f).suffix for f in test_files)
        if len(extensions) > 1:
            logger.warning(f"Mixed test file types: {extensions}")

        ext = list(extensions)[0] if extensions else ".py"

        # Build command as list to avoid shell injection
        file_paths = [str(self.project_dir / f) for f in test_files]

        if ext == ".py":
            if with_coverage:
                cmd = ["pytest"] + file_paths + [
                    f"--cov={source_dir}",
                    "--cov-report=term-missing",
                    "-v"
                ]
            else:
                cmd = ["pytest"] + file_paths + ["-v", "--tb=short"]
        elif ext in (".ts", ".js"):
            cmd = ["npx", "jest"] + file_paths + ["--verbose"]
            if with_coverage:
                cmd.append("--coverage")
        else:
            return TestResult(output=f"No test runner configured for {ext} files")

        logger.info(f"Running tests: {' '.join(cmd)}")

        try:
            # Use create_subprocess_exec to avoid shell injection
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_dir),
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=300,  # 5 minute timeout
            )

            output = stdout.decode() + "\n" + stderr.decode()
            return self._parse_test_output(output, ext)

        except asyncio.TimeoutError:
            return TestResult(
                errors=1,
                total=1,
                output="Test execution timed out after 5 minutes",
            )
        except Exception as e:
            return TestResult(
                errors=1,
                total=1,
                output=f"Test execution failed: {str(e)}",
            )

    def _parse_test_output(self, output: str, ext: str) -> TestResult:
        """Parse test runner output to extract results.

        Args:
            output: Test runner output
            ext: File extension (.py, .ts, .js)

        Returns:
            TestResult with parsed values
        """
        result = TestResult(output=output)

        if ext == ".py":
            # Parse pytest output
            # Look for "X passed, Y failed, Z skipped"
            summary_match = re.search(
                r"(\d+) passed(?:, (\d+) failed)?(?:, (\d+) skipped)?",
                output,
            )
            if summary_match:
                result.passed = int(summary_match.group(1) or 0)
                result.failed = int(summary_match.group(2) or 0)
                result.skipped = int(summary_match.group(3) or 0)
                result.total = result.passed + result.failed + result.skipped

            # Also check for error count
            error_match = re.search(r"(\d+) error", output)
            if error_match:
                result.errors = int(error_match.group(1))
                result.total += result.errors

            # Parse coverage if present
            coverage_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
            if coverage_match:
                result.coverage = float(coverage_match.group(1))

            # Extract failed test names
            failed_matches = re.findall(
                r"FAILED (.+?)::(.+?) - (.+?)$",
                output,
                re.MULTILINE,
            )
            for file, test, reason in failed_matches:
                result.failed_tests.append({
                    "file": file,
                    "name": test,
                    "error": reason,
                })

        else:
            # Parse Jest output
            # Look for "Tests: X passed, Y failed, Z total"
            summary_match = re.search(
                r"Tests:\s+(?:(\d+) failed,\s+)?(?:(\d+) skipped,\s+)?(\d+) passed,\s+(\d+) total",
                output,
            )
            if summary_match:
                result.failed = int(summary_match.group(1) or 0)
                result.skipped = int(summary_match.group(2) or 0)
                result.passed = int(summary_match.group(3) or 0)
                result.total = int(summary_match.group(4) or 0)

            # Parse coverage
            coverage_match = re.search(r"All files\s+\|\s+(\d+\.?\d*)", output)
            if coverage_match:
                result.coverage = float(coverage_match.group(1))

        # If we couldn't parse, check for error indicators
        if result.total == 0:
            if "FAILED" in output or "failed" in output.lower():
                result.failed = 1
                result.total = 1
            elif "PASSED" in output or "passed" in output.lower():
                result.passed = 1
                result.total = 1
            elif "Error" in output or "error" in output.lower():
                result.errors = 1
                result.total = 1

        return result

    def validate_test_phase(
        self,
        test_files: List[str],
        acceptance_criteria: List[str],
    ) -> TDDValidationResult:
        """Validate the RED phase of TDD.

        In the RED phase:
        1. Test files must exist
        2. Tests must FAIL (no implementation yet)
        3. Tests must cover the acceptance criteria

        Args:
            test_files: List of test file paths
            acceptance_criteria: List of acceptance criteria to cover

        Returns:
            TDDValidationResult
        """
        issues = []
        warnings = []

        # Check test files exist
        if not test_files:
            return TDDValidationResult(
                valid=False,
                phase=TDDPhase.RED,
                message="No test files created",
                issues=["A03 Test Writer must create test files"],
            )

        missing_files = [f for f in test_files if not (self.project_dir / f).exists()]
        if missing_files:
            issues.append(f"Test files not found: {missing_files}")

        # Run tests - they MUST fail
        loop = asyncio.get_event_loop()
        test_result = loop.run_until_complete(self.run_tests(test_files))

        if test_result.all_pass:
            return TDDValidationResult(
                valid=False,
                phase=TDDPhase.RED,
                message="Tests pass without implementation - tests may be trivial or wrong",
                test_result=test_result,
                issues=[
                    "Tests should FAIL in RED phase (before implementation)",
                    "Passing tests indicate either trivial tests or existing implementation",
                ],
            )

        if test_result.total == 0:
            return TDDValidationResult(
                valid=False,
                phase=TDDPhase.RED,
                message="No tests were executed",
                test_result=test_result,
                issues=["Test files must contain runnable tests"],
            )

        # Check acceptance criteria coverage
        coverage, uncovered = self._check_criteria_coverage(test_files, acceptance_criteria)

        if coverage < 0.9:  # Require 90% criteria coverage
            warnings.append(
                f"Tests cover only {coverage * 100:.0f}% of acceptance criteria"
            )

        return TDDValidationResult(
            valid=len(issues) == 0,
            phase=TDDPhase.RED,
            message=f"RED phase valid: {test_result.failed + test_result.errors} tests fail as expected",
            test_result=test_result,
            criteria_coverage=coverage,
            uncovered_criteria=uncovered,
            issues=issues,
            warnings=warnings,
        )

    def validate_implement_phase(
        self,
        source_files: List[str],
        test_files: List[str],
        modified_test_files: Optional[List[str]] = None,
    ) -> TDDValidationResult:
        """Validate the GREEN phase of TDD.

        In the GREEN phase:
        1. Tests must now PASS
        2. Test files must NOT be modified (implementer shouldn't change tests)
        3. Coverage should meet threshold

        Args:
            source_files: List of source files created/modified
            test_files: List of test files to run
            modified_test_files: Test files that were modified (should be empty)

        Returns:
            TDDValidationResult
        """
        issues = []
        warnings = []

        # Check that test files weren't modified
        if modified_test_files:
            issues.append(
                f"Implementer modified test files: {modified_test_files}. "
                "Tests should only be written by A03 Test Writer."
            )

        # Run tests - they MUST pass
        loop = asyncio.get_event_loop()
        test_result = loop.run_until_complete(
            self.run_tests(test_files, with_coverage=True)
        )

        if not test_result.all_pass:
            return TDDValidationResult(
                valid=False,
                phase=TDDPhase.GREEN,
                message=f"{test_result.failed + test_result.errors} tests still failing",
                test_result=test_result,
                issues=[
                    "Implementation must make all tests pass",
                    f"Failed tests: {[t['name'] for t in test_result.failed_tests]}",
                ],
            )

        # Check coverage
        if test_result.coverage < self.coverage_threshold:
            warnings.append(
                f"Coverage {test_result.coverage:.1f}% is below threshold "
                f"{self.coverage_threshold}%"
            )

        return TDDValidationResult(
            valid=len(issues) == 0,
            phase=TDDPhase.GREEN,
            message=f"GREEN phase valid: {test_result.passed} tests pass, "
            f"{test_result.coverage:.1f}% coverage",
            test_result=test_result,
            criteria_coverage=test_result.coverage / 100.0,
            issues=issues,
            warnings=warnings,
        )

    def validate_refactor_phase(
        self,
        test_files: List[str],
        modified_source_files: List[str],
    ) -> TDDValidationResult:
        """Validate the REFACTOR phase of TDD.

        In the REFACTOR phase:
        1. Tests must still PASS after refactoring
        2. Coverage should not decrease

        Args:
            test_files: List of test files to run
            modified_source_files: Source files that were refactored

        Returns:
            TDDValidationResult
        """
        issues = []
        warnings = []

        # Run tests - they MUST still pass
        loop = asyncio.get_event_loop()
        test_result = loop.run_until_complete(
            self.run_tests(test_files, with_coverage=True)
        )

        if not test_result.all_pass:
            return TDDValidationResult(
                valid=False,
                phase=TDDPhase.REFACTOR,
                message=f"Refactoring broke {test_result.failed + test_result.errors} tests",
                test_result=test_result,
                issues=[
                    "Refactoring must keep all tests passing",
                    f"Broken tests: {[t['name'] for t in test_result.failed_tests]}",
                ],
            )

        return TDDValidationResult(
            valid=True,
            phase=TDDPhase.REFACTOR,
            message=f"REFACTOR phase valid: {test_result.passed} tests still pass",
            test_result=test_result,
            issues=issues,
            warnings=warnings,
        )

    def _check_criteria_coverage(
        self,
        test_files: List[str],
        acceptance_criteria: List[str],
    ) -> Tuple[float, List[str]]:
        """Check how well tests cover acceptance criteria.

        Uses heuristic text matching to estimate coverage.

        Args:
            test_files: Test files to check
            acceptance_criteria: Criteria to cover

        Returns:
            Tuple of (coverage percentage, list of uncovered criteria)
        """
        if not acceptance_criteria:
            return 1.0, []

        # Read all test file contents
        test_content = ""
        for test_file in test_files:
            test_path = self.project_dir / test_file
            if test_path.exists():
                test_content += test_path.read_text().lower()

        # Check each criterion
        covered = []
        uncovered = []

        for criterion in acceptance_criteria:
            # Extract key terms from criterion
            terms = self._extract_key_terms(criterion)

            # Check if any key terms appear in tests
            found = any(term in test_content for term in terms)

            if found:
                covered.append(criterion)
            else:
                uncovered.append(criterion)

        coverage = len(covered) / len(acceptance_criteria) if acceptance_criteria else 1.0
        return coverage, uncovered

    def _extract_key_terms(self, text: str) -> List[str]:
        """Extract key terms from a criterion for matching.

        Args:
            text: Criterion text

        Returns:
            List of lowercase key terms
        """
        # Remove common words and punctuation
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "must", "shall",
            "can", "need", "to", "of", "in", "for", "on", "with", "at",
            "by", "from", "as", "into", "through", "during", "before",
            "after", "above", "below", "between", "under", "again",
            "further", "then", "once", "here", "there", "when", "where",
            "why", "how", "all", "each", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "only", "own", "same",
            "so", "than", "too", "very", "just", "and", "but", "if", "or",
        }

        # Extract words
        words = re.findall(r"\b\w+\b", text.lower())

        # Filter and return key terms
        terms = [w for w in words if w not in stop_words and len(w) > 2]

        return terms


def validate_test_phase(
    project_dir: Path,
    test_files: List[str],
    acceptance_criteria: List[str],
) -> TDDValidationResult:
    """Convenience function to validate test phase.

    Args:
        project_dir: Project directory
        test_files: Test files created
        acceptance_criteria: Criteria to cover

    Returns:
        TDDValidationResult
    """
    validator = TDDValidator(project_dir)
    return validator.validate_test_phase(test_files, acceptance_criteria)


def validate_implement_phase(
    project_dir: Path,
    source_files: List[str],
    test_files: List[str],
    modified_test_files: Optional[List[str]] = None,
) -> TDDValidationResult:
    """Convenience function to validate implementation phase.

    Args:
        project_dir: Project directory
        source_files: Source files created/modified
        test_files: Test files to run
        modified_test_files: Test files that were modified

    Returns:
        TDDValidationResult
    """
    validator = TDDValidator(project_dir)
    return validator.validate_implement_phase(source_files, test_files, modified_test_files)
