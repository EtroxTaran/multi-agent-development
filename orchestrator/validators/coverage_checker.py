"""Coverage checker for test coverage enforcement.

Detects and parses coverage reports from various test frameworks
and validates against configurable thresholds.
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CoverageStatus(str, Enum):
    """Status of coverage check."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class FileCoverage:
    """Coverage data for a single file."""
    file_path: str
    lines_total: int
    lines_covered: int
    lines_percent: float
    branches_total: Optional[int] = None
    branches_covered: Optional[int] = None
    branches_percent: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "lines_total": self.lines_total,
            "lines_covered": self.lines_covered,
            "lines_percent": self.lines_percent,
            "branches_total": self.branches_total,
            "branches_covered": self.branches_covered,
            "branches_percent": self.branches_percent,
        }


@dataclass
class CoverageCheckResult:
    """Result of coverage check."""
    status: CoverageStatus
    overall_percent: float
    threshold: float
    meets_threshold: bool
    message: str
    files: list[FileCoverage] = field(default_factory=list)
    uncovered_files: list[str] = field(default_factory=list)
    low_coverage_files: list[tuple[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "overall_percent": self.overall_percent,
            "threshold": self.threshold,
            "meets_threshold": self.meets_threshold,
            "message": self.message,
            "files": [f.to_dict() for f in self.files],
            "uncovered_files": self.uncovered_files,
            "low_coverage_files": self.low_coverage_files,
        }


class CoverageChecker:
    """Checks test coverage against configurable thresholds."""

    # Known coverage report paths
    COVERAGE_PATHS = {
        # Node.js / Vitest / Jest
        "vitest": ["coverage/coverage-summary.json", "coverage/coverage-final.json"],
        "jest": ["coverage/coverage-summary.json", "coverage/coverage-final.json"],
        "nyc": ["coverage/coverage-summary.json", ".nyc_output/coverage-summary.json"],
        # Python
        "pytest": ["coverage.json", "htmlcov/status.json", ".coverage"],
        # Go
        "go": ["coverage.out", "cover.out"],
        # Generic
        "lcov": ["coverage/lcov.info", "lcov.info"],
    }

    def __init__(
        self,
        project_dir: str | Path,
        threshold: float = 70.0,
        blocking: bool = False,
    ):
        """Initialize the coverage checker.

        Args:
            project_dir: Path to the project directory
            threshold: Minimum coverage percentage (0-100)
            blocking: Whether failing threshold should block workflow
        """
        self.project_dir = Path(project_dir)
        self.threshold = threshold
        self.blocking = blocking

    def check(self, run_coverage: bool = False) -> CoverageCheckResult:
        """Check coverage from existing reports or by running tests.

        Args:
            run_coverage: If True, run tests with coverage before checking

        Returns:
            CoverageCheckResult
        """
        if run_coverage:
            self._run_coverage_command()

        # Try to find and parse coverage report
        coverage_data = self._find_and_parse_coverage()

        if coverage_data is None:
            return CoverageCheckResult(
                status=CoverageStatus.SKIPPED,
                overall_percent=0.0,
                threshold=self.threshold,
                meets_threshold=False,
                message="No coverage report found",
            )

        overall_percent, files, uncovered, low_coverage = coverage_data

        meets_threshold = overall_percent >= self.threshold

        if meets_threshold:
            status = CoverageStatus.PASSED
            message = f"Coverage {overall_percent:.1f}% meets threshold {self.threshold}%"
        elif self.blocking:
            status = CoverageStatus.FAILED
            message = f"Coverage {overall_percent:.1f}% is below threshold {self.threshold}%"
        else:
            status = CoverageStatus.WARNING
            message = f"Coverage {overall_percent:.1f}% is below threshold {self.threshold}% (non-blocking)"

        return CoverageCheckResult(
            status=status,
            overall_percent=overall_percent,
            threshold=self.threshold,
            meets_threshold=meets_threshold,
            message=message,
            files=files,
            uncovered_files=uncovered,
            low_coverage_files=low_coverage,
        )

    def _run_coverage_command(self) -> None:
        """Run the coverage command for the project."""
        coverage_cmd = self._detect_coverage_command()
        if not coverage_cmd:
            logger.warning("Could not detect coverage command")
            return

        logger.info(f"Running coverage: {coverage_cmd}")
        try:
            subprocess.run(
                coverage_cmd,
                shell=True,
                cwd=self.project_dir,
                timeout=300,
                capture_output=True,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Coverage command timed out")
        except Exception as e:
            logger.warning(f"Error running coverage: {e}")

    def _detect_coverage_command(self) -> Optional[str]:
        """Detect the coverage command for the project."""
        package_json = self.project_dir / "package.json"

        if package_json.exists():
            try:
                pkg = json.loads(package_json.read_text())
                scripts = pkg.get("scripts", {})
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

                # Check for coverage script
                if "coverage" in scripts:
                    return "npm run coverage"
                if "test:coverage" in scripts:
                    return "npm run test:coverage"

                # Check for vitest
                if "vitest" in deps:
                    return "npx vitest run --coverage"

                # Check for jest
                if "jest" in deps:
                    return "npx jest --coverage"

            except Exception:
                pass

        # Python
        if (self.project_dir / "pyproject.toml").exists():
            return "pytest --cov --cov-report=json"

        # Go
        if (self.project_dir / "go.mod").exists():
            return "go test -coverprofile=coverage.out ./..."

        return None

    def _find_and_parse_coverage(self) -> Optional[tuple[float, list[FileCoverage], list[str], list[tuple[str, float]]]]:
        """Find and parse coverage report.

        Returns:
            Tuple of (overall_percent, file_coverages, uncovered_files, low_coverage_files)
            or None if no report found
        """
        # Try Vitest/Jest JSON format
        for path in self.COVERAGE_PATHS["vitest"]:
            report_path = self.project_dir / path
            if report_path.exists():
                result = self._parse_json_coverage(report_path)
                if result:
                    return result

        # Try pytest JSON format
        for path in self.COVERAGE_PATHS["pytest"]:
            report_path = self.project_dir / path
            if report_path.exists() and path.endswith(".json"):
                result = self._parse_pytest_coverage(report_path)
                if result:
                    return result

        # Try LCOV format
        for path in self.COVERAGE_PATHS["lcov"]:
            report_path = self.project_dir / path
            if report_path.exists():
                result = self._parse_lcov_coverage(report_path)
                if result:
                    return result

        # Try Go coverage format
        for path in self.COVERAGE_PATHS["go"]:
            report_path = self.project_dir / path
            if report_path.exists():
                result = self._parse_go_coverage(report_path)
                if result:
                    return result

        return None

    def _parse_json_coverage(self, report_path: Path) -> Optional[tuple[float, list[FileCoverage], list[str], list[tuple[str, float]]]]:
        """Parse Vitest/Jest JSON coverage report."""
        try:
            data = json.loads(report_path.read_text())

            # Check for summary format
            if "total" in data:
                total = data["total"]
                lines = total.get("lines", {})
                overall = lines.get("pct", 0.0)

                files: list[FileCoverage] = []
                uncovered: list[str] = []
                low_coverage: list[tuple[str, float]] = []

                for file_path, file_data in data.items():
                    if file_path == "total":
                        continue

                    file_lines = file_data.get("lines", {})
                    file_branches = file_data.get("branches", {})

                    fc = FileCoverage(
                        file_path=file_path,
                        lines_total=file_lines.get("total", 0),
                        lines_covered=file_lines.get("covered", 0),
                        lines_percent=file_lines.get("pct", 0.0),
                        branches_total=file_branches.get("total"),
                        branches_covered=file_branches.get("covered"),
                        branches_percent=file_branches.get("pct"),
                    )
                    files.append(fc)

                    if fc.lines_percent == 0:
                        uncovered.append(file_path)
                    elif fc.lines_percent < self.threshold:
                        low_coverage.append((file_path, fc.lines_percent))

                return overall, files, uncovered, low_coverage

            # Check for coverage-final format
            elif any(key.endswith(".js") or key.endswith(".ts") for key in data.keys()):
                total_statements = 0
                covered_statements = 0
                files = []
                uncovered = []
                low_coverage = []

                for file_path, file_data in data.items():
                    s = file_data.get("s", {})
                    total = len(s)
                    covered = sum(1 for v in s.values() if v > 0)

                    total_statements += total
                    covered_statements += covered

                    pct = (covered / total * 100) if total > 0 else 0

                    fc = FileCoverage(
                        file_path=file_path,
                        lines_total=total,
                        lines_covered=covered,
                        lines_percent=pct,
                    )
                    files.append(fc)

                    if pct == 0:
                        uncovered.append(file_path)
                    elif pct < self.threshold:
                        low_coverage.append((file_path, pct))

                overall = (covered_statements / total_statements * 100) if total_statements > 0 else 0
                return overall, files, uncovered, low_coverage

        except Exception as e:
            logger.warning(f"Error parsing JSON coverage: {e}")

        return None

    def _parse_pytest_coverage(self, report_path: Path) -> Optional[tuple[float, list[FileCoverage], list[str], list[tuple[str, float]]]]:
        """Parse pytest coverage JSON report."""
        try:
            data = json.loads(report_path.read_text())

            totals = data.get("totals", {})
            overall = totals.get("percent_covered", 0.0)

            files = []
            uncovered = []
            low_coverage = []

            for file_path, file_data in data.get("files", {}).items():
                summary = file_data.get("summary", {})

                fc = FileCoverage(
                    file_path=file_path,
                    lines_total=summary.get("num_statements", 0),
                    lines_covered=summary.get("covered_lines", 0),
                    lines_percent=summary.get("percent_covered", 0.0),
                    branches_total=summary.get("num_branches"),
                    branches_covered=summary.get("covered_branches"),
                    branches_percent=summary.get("percent_covered_branches"),
                )
                files.append(fc)

                if fc.lines_percent == 0:
                    uncovered.append(file_path)
                elif fc.lines_percent < self.threshold:
                    low_coverage.append((file_path, fc.lines_percent))

            return overall, files, uncovered, low_coverage

        except Exception as e:
            logger.warning(f"Error parsing pytest coverage: {e}")

        return None

    def _parse_lcov_coverage(self, report_path: Path) -> Optional[tuple[float, list[FileCoverage], list[str], list[tuple[str, float]]]]:
        """Parse LCOV format coverage report."""
        try:
            content = report_path.read_text()

            files = []
            uncovered = []
            low_coverage = []

            total_lines = 0
            total_hits = 0

            current_file = None
            file_lines = 0
            file_hits = 0

            for line in content.splitlines():
                if line.startswith("SF:"):
                    if current_file and file_lines > 0:
                        pct = (file_hits / file_lines * 100)
                        fc = FileCoverage(
                            file_path=current_file,
                            lines_total=file_lines,
                            lines_covered=file_hits,
                            lines_percent=pct,
                        )
                        files.append(fc)

                        if pct == 0:
                            uncovered.append(current_file)
                        elif pct < self.threshold:
                            low_coverage.append((current_file, pct))

                    current_file = line[3:]
                    file_lines = 0
                    file_hits = 0

                elif line.startswith("DA:"):
                    parts = line[3:].split(",")
                    if len(parts) >= 2:
                        file_lines += 1
                        total_lines += 1
                        hits = int(parts[1])
                        if hits > 0:
                            file_hits += 1
                            total_hits += 1

                elif line == "end_of_record":
                    if current_file and file_lines > 0:
                        pct = (file_hits / file_lines * 100)
                        fc = FileCoverage(
                            file_path=current_file,
                            lines_total=file_lines,
                            lines_covered=file_hits,
                            lines_percent=pct,
                        )
                        files.append(fc)

                        if pct == 0:
                            uncovered.append(current_file)
                        elif pct < self.threshold:
                            low_coverage.append((current_file, pct))

                    current_file = None

            overall = (total_hits / total_lines * 100) if total_lines > 0 else 0
            return overall, files, uncovered, low_coverage

        except Exception as e:
            logger.warning(f"Error parsing LCOV coverage: {e}")

        return None

    def _parse_go_coverage(self, report_path: Path) -> Optional[tuple[float, list[FileCoverage], list[str], list[tuple[str, float]]]]:
        """Parse Go coverage profile."""
        try:
            content = report_path.read_text()

            files_data: dict[str, tuple[int, int]] = {}  # file -> (total, covered)

            for line in content.splitlines():
                if line.startswith("mode:"):
                    continue

                # Format: file:startline.startcol,endline.endcol statements count
                match = re.match(r"(.+?):(\d+)\.(\d+),(\d+)\.(\d+)\s+(\d+)\s+(\d+)", line)
                if match:
                    file_path = match.group(1)
                    statements = int(match.group(6))
                    count = int(match.group(7))

                    if file_path not in files_data:
                        files_data[file_path] = (0, 0)

                    total, covered = files_data[file_path]
                    total += statements
                    if count > 0:
                        covered += statements
                    files_data[file_path] = (total, covered)

            files = []
            uncovered = []
            low_coverage = []
            total_stmts = 0
            covered_stmts = 0

            for file_path, (total, covered) in files_data.items():
                total_stmts += total
                covered_stmts += covered

                pct = (covered / total * 100) if total > 0 else 0

                fc = FileCoverage(
                    file_path=file_path,
                    lines_total=total,
                    lines_covered=covered,
                    lines_percent=pct,
                )
                files.append(fc)

                if pct == 0:
                    uncovered.append(file_path)
                elif pct < self.threshold:
                    low_coverage.append((file_path, pct))

            overall = (covered_stmts / total_stmts * 100) if total_stmts > 0 else 0
            return overall, files, uncovered, low_coverage

        except Exception as e:
            logger.warning(f"Error parsing Go coverage: {e}")

        return None


def check_coverage(
    project_dir: str | Path,
    threshold: float = 70.0,
    blocking: bool = False,
    run_coverage: bool = False,
) -> CoverageCheckResult:
    """Convenience function to check coverage.

    Args:
        project_dir: Path to the project directory
        threshold: Minimum coverage percentage
        blocking: Whether failing threshold should block workflow
        run_coverage: Whether to run coverage command first

    Returns:
        CoverageCheckResult
    """
    checker = CoverageChecker(project_dir, threshold, blocking)
    return checker.check(run_coverage)
