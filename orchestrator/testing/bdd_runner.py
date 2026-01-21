"""
BDD (Behavior-Driven Development) test runner.

Runs Gherkin feature files using pytest-bdd and collects results.

Usage:
    from orchestrator.testing import BDDRunner

    runner = BDDRunner(project_dir)
    result = await runner.run_features(["features/auth.feature"])
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScenarioResult:
    """Result of a single BDD scenario."""

    name: str
    feature: str
    status: str  # "passed", "failed", "skipped", "pending"
    tags: List[str] = field(default_factory=list)
    steps_total: int = 0
    steps_passed: int = 0
    steps_failed: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    failed_step: Optional[str] = None

    @property
    def passed(self) -> bool:
        """Check if scenario passed."""
        return self.status == "passed"


@dataclass
class FeatureResult:
    """Result of a BDD feature file."""

    name: str
    path: str
    description: str = ""
    scenarios: List[ScenarioResult] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def passed(self) -> int:
        """Count of passed scenarios."""
        return sum(1 for s in self.scenarios if s.status == "passed")

    @property
    def failed(self) -> int:
        """Count of failed scenarios."""
        return sum(1 for s in self.scenarios if s.status == "failed")

    @property
    def skipped(self) -> int:
        """Count of skipped scenarios."""
        return sum(1 for s in self.scenarios if s.status == "skipped")

    @property
    def all_pass(self) -> bool:
        """Check if all scenarios passed."""
        return self.failed == 0 and len(self.scenarios) > 0


@dataclass
class BDDResult:
    """Complete result of BDD test run."""

    features: List[FeatureResult] = field(default_factory=list)
    total_scenarios: int = 0
    passed_scenarios: int = 0
    failed_scenarios: int = 0
    skipped_scenarios: int = 0
    duration_seconds: float = 0.0
    output: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def all_pass(self) -> bool:
        """Check if all features passed."""
        return self.failed_scenarios == 0 and self.total_scenarios > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_scenarios": self.total_scenarios,
            "passed_scenarios": self.passed_scenarios,
            "failed_scenarios": self.failed_scenarios,
            "skipped_scenarios": self.skipped_scenarios,
            "duration_seconds": self.duration_seconds,
            "all_pass": self.all_pass,
            "features": [
                {
                    "name": f.name,
                    "path": f.path,
                    "passed": f.passed,
                    "failed": f.failed,
                    "all_pass": f.all_pass,
                }
                for f in self.features
            ],
            "timestamp": self.timestamp.isoformat(),
        }


class BDDRunner:
    """Runs BDD/Gherkin tests using pytest-bdd."""

    # Default pytest-bdd command
    DEFAULT_COMMAND = "pytest --gherkin-terminal-reporter -v {files}"

    # JSON report command
    JSON_COMMAND = "pytest --json-report --json-report-file={report_file} -v {files}"

    def __init__(
        self,
        project_dir: Path,
        features_dir: str = "features",
        steps_dir: str = "tests/step_defs",
    ):
        """Initialize BDD runner.

        Args:
            project_dir: Project directory
            features_dir: Directory containing .feature files
            steps_dir: Directory containing step definitions
        """
        self.project_dir = Path(project_dir)
        self.features_dir = self.project_dir / features_dir
        self.steps_dir = self.project_dir / steps_dir

    def discover_features(
        self,
        tags: Optional[List[str]] = None,
    ) -> List[Path]:
        """Discover feature files in the project.

        Args:
            tags: Optional list of tags to filter by

        Returns:
            List of feature file paths
        """
        features = []

        if self.features_dir.exists():
            for feature_file in self.features_dir.rglob("*.feature"):
                if tags:
                    # Read file and check for tags
                    content = feature_file.read_text()
                    file_tags = self._extract_tags(content)
                    if any(tag in file_tags for tag in tags):
                        features.append(feature_file)
                else:
                    features.append(feature_file)

        return features

    def _extract_tags(self, content: str) -> List[str]:
        """Extract tags from feature file content.

        Args:
            content: Feature file content

        Returns:
            List of tags (without @)
        """
        tags = re.findall(r"@(\w+)", content)
        return tags

    def parse_feature_file(self, feature_path: Path) -> FeatureResult:
        """Parse a feature file to extract metadata.

        Args:
            feature_path: Path to .feature file

        Returns:
            FeatureResult with parsed metadata
        """
        content = feature_path.read_text()

        # Extract feature name
        feature_match = re.search(r"Feature:\s*(.+)", content)
        feature_name = feature_match.group(1).strip() if feature_match else feature_path.stem

        # Extract feature tags
        feature_tags = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.strip().startswith("Feature:"):
                # Tags are on lines before Feature:
                for j in range(max(0, i - 3), i):
                    feature_tags.extend(re.findall(r"@(\w+)", lines[j]))
                break

        # Extract scenario names
        scenarios = []
        current_tags = []
        for line in lines:
            if line.strip().startswith("@"):
                current_tags.extend(re.findall(r"@(\w+)", line))
            elif line.strip().startswith("Scenario:") or line.strip().startswith("Scenario Outline:"):
                scenario_match = re.search(r"(?:Scenario|Scenario Outline):\s*(.+)", line)
                if scenario_match:
                    scenarios.append(
                        ScenarioResult(
                            name=scenario_match.group(1).strip(),
                            feature=feature_name,
                            status="pending",
                            tags=current_tags.copy(),
                        )
                    )
                current_tags = []

        return FeatureResult(
            name=feature_name,
            path=str(feature_path.relative_to(self.project_dir)),
            tags=feature_tags,
            scenarios=scenarios,
        )

    async def run_features(
        self,
        feature_files: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        timeout: int = 300,
    ) -> BDDResult:
        """Run BDD tests.

        Args:
            feature_files: Specific feature files to run (optional)
            tags: Tags to filter by (optional)
            timeout: Timeout in seconds

        Returns:
            BDDResult with test results
        """
        start_time = datetime.utcnow()

        # Determine files to run
        if feature_files:
            files = [self.project_dir / f for f in feature_files]
        else:
            files = self.discover_features(tags)

        if not files:
            return BDDResult(
                output="No feature files found",
            )

        # Build command as list to avoid shell injection
        file_paths = [str(f) for f in files]
        report_file = self.project_dir / ".workflow" / "temp" / "bdd_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "pytest",
            "--json-report",
            f"--json-report-file={report_file}",
            "-v",
        ] + file_paths

        logger.info(f"Running BDD tests: {' '.join(cmd)}")

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

            # Parse JSON report if available
            if report_file.exists():
                result = self._parse_json_report(report_file)
            else:
                result = self._parse_terminal_output(output, files)

            result.output = output
            result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()

            return result

        except asyncio.TimeoutError:
            return BDDResult(
                output=f"BDD tests timed out after {timeout}s",
            )
        except Exception as e:
            return BDDResult(
                output=f"BDD tests failed: {str(e)}",
            )
        finally:
            # Cleanup report file
            if report_file.exists():
                report_file.unlink()

    def _parse_json_report(self, report_file: Path) -> BDDResult:
        """Parse pytest-json-report output.

        Args:
            report_file: Path to JSON report

        Returns:
            BDDResult
        """
        try:
            report = json.loads(report_file.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return BDDResult()

        result = BDDResult()
        features_map: Dict[str, FeatureResult] = {}

        for test in report.get("tests", []):
            nodeid = test.get("nodeid", "")
            outcome = test.get("outcome", "unknown")
            duration = test.get("call", {}).get("duration", 0)

            # Parse feature and scenario from nodeid
            # Format: tests/features/test_auth.py::test_login_success
            parts = nodeid.split("::")
            feature_path = parts[0] if parts else "unknown"
            scenario_name = parts[-1] if len(parts) > 1 else "unknown"

            # Get or create feature
            if feature_path not in features_map:
                features_map[feature_path] = FeatureResult(
                    name=Path(feature_path).stem,
                    path=feature_path,
                )

            # Map pytest outcome to BDD status
            status_map = {
                "passed": "passed",
                "failed": "failed",
                "skipped": "skipped",
                "error": "failed",
            }
            status = status_map.get(outcome, "pending")

            # Add scenario
            scenario = ScenarioResult(
                name=scenario_name.replace("test_", "").replace("_", " "),
                feature=features_map[feature_path].name,
                status=status,
                duration_seconds=duration,
            )

            if outcome == "failed":
                longrepr = test.get("call", {}).get("longrepr", "")
                scenario.error = str(longrepr)[:500]  # Truncate

            features_map[feature_path].scenarios.append(scenario)

        result.features = list(features_map.values())

        # Calculate totals
        for feature in result.features:
            result.total_scenarios += len(feature.scenarios)
            result.passed_scenarios += feature.passed
            result.failed_scenarios += feature.failed
            result.skipped_scenarios += feature.skipped
            result.duration_seconds += feature.duration_seconds

        return result

    def _parse_terminal_output(
        self,
        output: str,
        files: List[Path],
    ) -> BDDResult:
        """Parse terminal output when JSON report not available.

        Args:
            output: Terminal output
            files: Feature files that were run

        Returns:
            BDDResult
        """
        result = BDDResult()

        # Parse pytest summary
        # "5 passed, 2 failed, 1 skipped"
        summary_match = re.search(
            r"(\d+) passed(?:, (\d+) failed)?(?:, (\d+) skipped)?",
            output,
        )

        if summary_match:
            result.passed_scenarios = int(summary_match.group(1) or 0)
            result.failed_scenarios = int(summary_match.group(2) or 0)
            result.skipped_scenarios = int(summary_match.group(3) or 0)
            result.total_scenarios = (
                result.passed_scenarios +
                result.failed_scenarios +
                result.skipped_scenarios
            )

        # Create basic feature results from files
        for file_path in files:
            feature = self.parse_feature_file(file_path)
            result.features.append(feature)

        return result

    async def run_by_tags(
        self,
        tags: List[str],
        timeout: int = 300,
    ) -> BDDResult:
        """Run tests matching specific tags.

        Args:
            tags: List of tags to run (e.g., ["integration", "smoke"])
            timeout: Timeout in seconds

        Returns:
            BDDResult
        """
        features = self.discover_features(tags)
        if not features:
            return BDDResult(
                output=f"No features found with tags: {tags}",
            )

        return await self.run_features(
            [str(f.relative_to(self.project_dir)) for f in features],
            tags=tags,
            timeout=timeout,
        )
