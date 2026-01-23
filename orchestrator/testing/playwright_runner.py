"""
Playwright E2E test runner.

Runs end-to-end browser tests using Playwright (via MCP or CLI).

Usage:
    from orchestrator.testing import PlaywrightRunner

    runner = PlaywrightRunner(project_dir)
    result = await runner.run_tests(["tests/e2e/test_login.py"])
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class BrowserTestResult:
    """Result of a single browser test."""

    name: str
    file: str
    browser: str = "chromium"
    status: str = "pending"  # "passed", "failed", "skipped"
    duration_seconds: float = 0.0
    error: Optional[str] = None
    screenshot: Optional[str] = None
    trace: Optional[str] = None

    @property
    def passed(self) -> bool:
        """Check if test passed."""
        return self.status == "passed"


@dataclass
class E2EResult:
    """Complete result of E2E test run."""

    tests: list[BrowserTestResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    browsers: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    screenshots: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    traces: list[str] = field(default_factory=list)
    output: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def all_pass(self) -> bool:
        """Check if all tests passed."""
        return self.failed == 0 and self.total > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "all_pass": self.all_pass,
            "browsers": self.browsers,
            "duration_seconds": self.duration_seconds,
            "screenshots": self.screenshots,
            "traces": self.traces,
            "failed_tests": [
                {"name": t.name, "error": t.error} for t in self.tests if t.status == "failed"
            ],
            "timestamp": self.timestamp.isoformat(),
        }


class PlaywrightRunner:
    """Runs E2E tests using Playwright."""

    # Default browsers to test
    DEFAULT_BROWSERS = ["chromium"]

    # Playwright CLI command
    CLI_COMMAND = "npx playwright test {files} --reporter=json --output={output_dir}"

    # pytest-playwright command
    PYTEST_COMMAND = "pytest {files} --browser={browser} -v --headed"

    def __init__(
        self,
        project_dir: Path,
        e2e_dir: str = "tests/e2e",
        artifacts_dir: str = ".workflow/artifacts",
    ):
        """Initialize Playwright runner.

        Args:
            project_dir: Project directory
            e2e_dir: Directory containing E2E tests
            artifacts_dir: Directory for test artifacts
        """
        self.project_dir = Path(project_dir)
        self.e2e_dir = self.project_dir / e2e_dir
        self.artifacts_dir = self.project_dir / artifacts_dir

    def discover_tests(self) -> list[Path]:
        """Discover E2E test files.

        Returns:
            List of test file paths
        """
        tests = []

        if self.e2e_dir.exists():
            # Python tests
            tests.extend(self.e2e_dir.rglob("test_*.py"))
            tests.extend(self.e2e_dir.rglob("*_test.py"))
            # TypeScript/JavaScript tests
            tests.extend(self.e2e_dir.rglob("*.spec.ts"))
            tests.extend(self.e2e_dir.rglob("*.spec.js"))

        return tests

    async def run_tests(
        self,
        test_files: Optional[list[str]] = None,
        browsers: Optional[list[str]] = None,
        headed: bool = False,
        timeout: int = 600,
    ) -> E2EResult:
        """Run E2E tests.

        Args:
            test_files: Specific test files to run (optional)
            browsers: Browsers to test on (optional)
            headed: Run in headed mode (visible browser)
            timeout: Timeout in seconds

        Returns:
            E2EResult with test results
        """
        start_time = datetime.utcnow()
        browsers = browsers or self.DEFAULT_BROWSERS

        # Determine files to run
        if test_files:
            files = [self.project_dir / f for f in test_files]
        else:
            files = self.discover_tests()

        if not files:
            return E2EResult(
                output="No E2E test files found",
            )

        # Ensure artifacts directory exists
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Determine if using Playwright CLI or pytest-playwright
        has_playwright_config = (self.project_dir / "playwright.config.ts").exists() or (
            self.project_dir / "playwright.config.js"
        ).exists()

        if has_playwright_config:
            result = await self._run_playwright_cli(files, browsers, headed, timeout)
        else:
            result = await self._run_pytest_playwright(files, browsers, headed, timeout)

        result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
        result.browsers = browsers

        return result

    async def _run_playwright_cli(
        self,
        files: list[Path],
        browsers: list[str],
        headed: bool,
        timeout: int,
    ) -> E2EResult:
        """Run tests using Playwright CLI.

        Args:
            files: Test files
            browsers: Browsers to use
            headed: Headed mode
            timeout: Timeout

        Returns:
            E2EResult
        """
        file_paths = [str(f) for f in files]
        output_dir = self.artifacts_dir / "playwright-results"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build command as list to avoid shell injection
        cmd = (
            [
                "npx",
                "playwright",
                "test",
            ]
            + file_paths
            + [
                f"--output={output_dir}",
                "--reporter=json",
            ]
        )

        if headed:
            cmd.append("--headed")

        if browsers:
            cmd.extend([f"--project={b}" for b in browsers])

        logger.info(f"Running Playwright tests: {' '.join(cmd)}")

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
                timeout=timeout,
            )

            output = stdout.decode() + "\n" + stderr.decode()
            return self._parse_playwright_output(output, output_dir)

        except asyncio.TimeoutError:
            return E2EResult(
                output=f"E2E tests timed out after {timeout}s",
            )
        except Exception as e:
            return E2EResult(
                output=f"E2E tests failed: {str(e)}",
            )

    async def _run_pytest_playwright(
        self,
        files: list[Path],
        browsers: list[str],
        headed: bool,
        timeout: int,
    ) -> E2EResult:
        """Run tests using pytest-playwright.

        Args:
            files: Test files
            browsers: Browsers to use
            headed: Headed mode
            timeout: Timeout

        Returns:
            E2EResult
        """
        result = E2EResult()

        for browser in browsers:
            file_paths = [str(f) for f in files]

            # Build command as list to avoid shell injection
            cmd = (
                [
                    "pytest",
                ]
                + file_paths
                + [
                    f"--browser={browser}",
                    "-v",
                    "--json-report",
                    f"--json-report-file={self.artifacts_dir}/pytest_{browser}.json",
                ]
            )

            if headed:
                cmd.append("--headed")

            logger.info(f"Running pytest-playwright: {' '.join(cmd)}")

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
                    timeout=timeout,
                )

                output = stdout.decode() + "\n" + stderr.decode()
                browser_result = self._parse_pytest_output(output, browser)

                result.tests.extend(browser_result.tests)
                result.output += output + "\n"

            except asyncio.TimeoutError:
                result.output += f"Browser {browser} timed out\n"
            except Exception as e:
                result.output += f"Browser {browser} failed: {str(e)}\n"

        # Calculate totals
        result.total = len(result.tests)
        result.passed = sum(1 for t in result.tests if t.status == "passed")
        result.failed = sum(1 for t in result.tests if t.status == "failed")
        result.skipped = sum(1 for t in result.tests if t.status == "skipped")

        # Collect artifacts
        result.screenshots = self._collect_artifacts("*.png")
        result.traces = self._collect_artifacts("*.zip")

        return result

    def _parse_playwright_output(
        self,
        output: str,
        output_dir: Path,
    ) -> E2EResult:
        """Parse Playwright CLI output.

        Args:
            output: CLI output
            output_dir: Directory with results

        Returns:
            E2EResult
        """
        result = E2EResult(output=output)

        # Try to parse JSON report
        report_file = output_dir / "results.json"
        if report_file.exists():
            try:
                report = json.loads(report_file.read_text())
                for suite in report.get("suites", []):
                    for spec in suite.get("specs", []):
                        for test in spec.get("tests", []):
                            result.tests.append(
                                BrowserTestResult(
                                    name=spec.get("title", "unknown"),
                                    file=spec.get("file", "unknown"),
                                    browser=test.get("projectName", "chromium"),
                                    status="passed"
                                    if test.get("status") == "expected"
                                    else "failed",
                                    duration_seconds=test.get("duration", 0) / 1000,
                                )
                            )
            except (json.JSONDecodeError, KeyError):
                pass

        # Fallback to parsing terminal output
        if not result.tests:
            # Parse "X passed, Y failed"
            summary_match = re.search(
                r"(\d+) passed(?:.*?(\d+) failed)?",
                output,
            )
            if summary_match:
                result.passed = int(summary_match.group(1) or 0)
                result.failed = int(summary_match.group(2) or 0)
                result.total = result.passed + result.failed

        else:
            result.total = len(result.tests)
            result.passed = sum(1 for t in result.tests if t.status == "passed")
            result.failed = sum(1 for t in result.tests if t.status == "failed")

        # Collect artifacts
        result.screenshots = self._collect_artifacts("*.png")
        result.traces = self._collect_artifacts("*.zip")

        return result

    def _parse_pytest_output(
        self,
        output: str,
        browser: str,
    ) -> E2EResult:
        """Parse pytest output.

        Args:
            output: pytest output
            browser: Browser used

        Returns:
            E2EResult
        """
        result = E2EResult()

        # Parse test results from output
        # "test_login.py::test_successful_login PASSED"
        test_matches = re.findall(
            r"([\w/\.]+)::(\w+)\s+(PASSED|FAILED|SKIPPED)",
            output,
        )

        for file, name, status in test_matches:
            result.tests.append(
                BrowserTestResult(
                    name=name,
                    file=file,
                    browser=browser,
                    status=status.lower(),
                )
            )

        return result

    def _collect_artifacts(self, pattern: str) -> list[str]:
        """Collect artifact files matching pattern.

        Args:
            pattern: Glob pattern

        Returns:
            List of relative paths
        """
        artifacts = []
        for f in self.artifacts_dir.rglob(pattern):
            artifacts.append(str(f.relative_to(self.project_dir)))
        return artifacts

    async def take_screenshot(
        self,
        url: str,
        filename: str,
    ) -> Optional[str]:
        """Take a screenshot of a URL using Playwright MCP.

        Args:
            url: URL to screenshot
            filename: Output filename

        Returns:
            Path to screenshot or None if failed
        """
        # This would use Playwright MCP tools when available
        # For now, use CLI fallback
        screenshot_path = self.artifacts_dir / filename

        # Build command as list to avoid shell injection
        cmd = ["npx", "playwright", "screenshot", url, str(screenshot_path)]

        try:
            # Use create_subprocess_exec to avoid shell injection
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_dir),
            )

            await asyncio.wait_for(process.communicate(), timeout=30)

            if screenshot_path.exists():
                return str(screenshot_path.relative_to(self.project_dir))
            return None

        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None

    async def run_visual_comparison(
        self,
        test_files: list[str],
        baseline_dir: str = "visual-baselines",
    ) -> E2EResult:
        """Run visual regression tests.

        Args:
            test_files: Test files with visual assertions
            baseline_dir: Directory with baseline screenshots

        Returns:
            E2EResult with visual comparison results
        """
        # Build command as list to avoid shell injection
        cmd = ["npx", "playwright", "test"] + test_files + ["--update-snapshots"]

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
                timeout=300,
            )

            output = stdout.decode() + "\n" + stderr.decode()
            return self._parse_playwright_output(
                output,
                self.artifacts_dir / "visual-results",
            )

        except Exception as e:
            return E2EResult(
                output=f"Visual comparison failed: {str(e)}",
            )
