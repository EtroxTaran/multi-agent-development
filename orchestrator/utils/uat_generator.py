"""UAT (User Acceptance Testing) document generator.

Generates structured verification documents after each task or phase completion.
Used to document what was built, test results, and manual verification checklists.

Based on GSD /gsd:verify-work pattern.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class FileChange:
    """Represents a changed file with line counts."""

    path: str
    lines_added: int = 0
    lines_removed: int = 0
    change_type: str = "modified"  # created, modified, deleted

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "change_type": self.change_type,
        }


@dataclass
class TestResults:
    """Test execution results."""

    unit_passed: int = 0
    unit_failed: int = 0
    integration_passed: int = 0
    integration_failed: int = 0
    e2e_passed: int = 0
    e2e_failed: int = 0
    coverage_percentage: float = 0.0
    test_output: str = ""

    @property
    def total_passed(self) -> int:
        return self.unit_passed + self.integration_passed + self.e2e_passed

    @property
    def total_failed(self) -> int:
        return self.unit_failed + self.integration_failed + self.e2e_failed

    @property
    def all_passed(self) -> bool:
        return self.total_failed == 0

    def to_dict(self) -> dict:
        return {
            "unit": {"passed": self.unit_passed, "failed": self.unit_failed},
            "integration": {
                "passed": self.integration_passed,
                "failed": self.integration_failed,
            },
            "e2e": {"passed": self.e2e_passed, "failed": self.e2e_failed},
            "coverage_percentage": self.coverage_percentage,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "all_passed": self.all_passed,
        }


@dataclass
class UATDocument:
    """User Acceptance Testing document for a task or phase.

    Captures what was built, what changed, test results, and
    provides a manual verification checklist.
    """

    # Identification
    task_id: str
    task_title: str
    phase: int
    generated_at: datetime = field(default_factory=datetime.now)

    # What was built
    features_implemented: list[str] = field(default_factory=list)
    endpoints_created: list[str] = field(default_factory=list)
    components_added: list[str] = field(default_factory=list)

    # Changes
    files_changed: list[FileChange] = field(default_factory=list)

    # Test results
    test_results: TestResults = field(default_factory=TestResults)

    # Manual verification
    verification_checklist: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)

    # Metadata
    implementation_notes: str = ""
    known_limitations: list[str] = field(default_factory=list)

    @property
    def total_lines_added(self) -> int:
        return sum(f.lines_added for f in self.files_changed)

    @property
    def total_lines_removed(self) -> int:
        return sum(f.lines_removed for f in self.files_changed)

    def to_markdown(self) -> str:
        """Generate markdown UAT document."""
        lines = [
            f"# UAT Document - {self.task_id}",
            "",
            f"**Task**: {self.task_title}",
            f"**Phase**: {self.phase}",
            f"**Generated**: {self.generated_at.isoformat()}",
            "",
            "---",
            "",
            "## What Was Built",
            "",
        ]

        # Features
        if self.features_implemented:
            lines.append("### Features Implemented")
            for feature in self.features_implemented:
                lines.append(f"- {feature}")
            lines.append("")

        # Endpoints
        if self.endpoints_created:
            lines.append("### API Endpoints")
            for endpoint in self.endpoints_created:
                lines.append(f"- `{endpoint}`")
            lines.append("")

        # Components
        if self.components_added:
            lines.append("### Components Added")
            for component in self.components_added:
                lines.append(f"- {component}")
            lines.append("")

        # Files changed
        lines.extend(
            [
                "## Files Changed",
                "",
                "| File | Change | Lines Added | Lines Removed |",
                "|------|--------|-------------|---------------|",
            ]
        )

        for fc in self.files_changed:
            lines.append(
                f"| `{fc.path}` | {fc.change_type} | +{fc.lines_added} | -{fc.lines_removed} |"
            )

        lines.extend(
            [
                "",
                f"**Total**: +{self.total_lines_added} / -{self.total_lines_removed} lines",
                "",
            ]
        )

        # Test results
        lines.extend(
            [
                "## Test Results",
                "",
                "| Type | Passed | Failed |",
                "|------|--------|--------|",
                f"| Unit Tests | {self.test_results.unit_passed} | {self.test_results.unit_failed} |",
                f"| Integration | {self.test_results.integration_passed} | {self.test_results.integration_failed} |",
                f"| E2E | {self.test_results.e2e_passed} | {self.test_results.e2e_failed} |",
                "",
                f"**Coverage**: {self.test_results.coverage_percentage:.1f}%",
                "",
            ]
        )

        if self.test_results.all_passed:
            lines.append("✅ All tests passing")
        else:
            lines.append(f"❌ {self.test_results.total_failed} test(s) failing")
        lines.append("")

        # Acceptance criteria
        if self.acceptance_criteria:
            lines.extend(["## Acceptance Criteria", ""])
            for criterion in self.acceptance_criteria:
                lines.append(f"- [x] {criterion}")
            lines.append("")

        # Manual verification checklist
        if self.verification_checklist:
            lines.extend(["## Manual Verification Checklist", ""])
            for item in self.verification_checklist:
                lines.append(f"- [ ] {item}")
            lines.append("")

        # Implementation notes
        if self.implementation_notes:
            lines.extend(["## Implementation Notes", "", self.implementation_notes, ""])

        # Known limitations
        if self.known_limitations:
            lines.extend(["## Known Limitations", ""])
            for limitation in self.known_limitations:
                lines.append(f"- {limitation}")
            lines.append("")

        lines.extend(["---", "*Generated by Conductor UAT generator*", ""])

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "task_title": self.task_title,
            "phase": self.phase,
            "generated_at": self.generated_at.isoformat(),
            "features_implemented": self.features_implemented,
            "endpoints_created": self.endpoints_created,
            "components_added": self.components_added,
            "files_changed": [f.to_dict() for f in self.files_changed],
            "total_lines_added": self.total_lines_added,
            "total_lines_removed": self.total_lines_removed,
            "test_results": self.test_results.to_dict(),
            "verification_checklist": self.verification_checklist,
            "acceptance_criteria": self.acceptance_criteria,
            "implementation_notes": self.implementation_notes,
            "known_limitations": self.known_limitations,
        }


class UATGenerator:
    """Generates UAT documents from task/phase completion data.

    Extracts information from:
    - Task definition (acceptance criteria)
    - Git diff (files changed)
    - Test output (results and coverage)
    - Implementation output (features, endpoints)
    """

    def __init__(self, project_dir: Path):
        """Initialize UAT generator.

        Args:
            project_dir: Project directory path
        """
        self.project_dir = Path(project_dir)
        self.uat_dir = self.project_dir / ".workflow" / "uat"

    def generate_from_task(
        self,
        task: dict,
        phase: int,
        test_output: Optional[str] = None,
        git_diff: Optional[str] = None,
        implementation_output: Optional[str] = None,
    ) -> UATDocument:
        """Generate UAT document from task completion data.

        Args:
            task: Task dictionary with id, title, acceptance_criteria
            phase: Current phase number
            test_output: Raw test command output
            git_diff: Git diff output for changes
            implementation_output: Worker implementation output

        Returns:
            Generated UATDocument
        """
        uat = UATDocument(
            task_id=task.get("id", "unknown"),
            task_title=task.get("title", "Untitled Task"),
            phase=phase,
        )

        # Extract acceptance criteria from task
        if "acceptance_criteria" in task:
            uat.acceptance_criteria = list(task["acceptance_criteria"])
            # Also add to verification checklist
            uat.verification_checklist = [
                f"Verify: {criterion}" for criterion in task["acceptance_criteria"]
            ]

        # Parse test output if provided
        if test_output:
            uat.test_results = self._parse_test_output(test_output)

        # Parse git diff if provided
        if git_diff:
            uat.files_changed = self._parse_git_diff(git_diff)

        # Extract features from implementation output
        if implementation_output:
            extracted = self._extract_from_implementation(implementation_output)
            uat.features_implemented = extracted.get("features", [])
            uat.endpoints_created = extracted.get("endpoints", [])
            uat.components_added = extracted.get("components", [])
            uat.implementation_notes = extracted.get("notes", "")

        return uat

    def _parse_test_output(self, output: str) -> TestResults:
        """Parse test output to extract results.

        Supports pytest, jest, and generic patterns.
        """
        results = TestResults(test_output=output[:2000])

        # Try pytest format: "X passed, Y failed"
        import re

        pytest_match = re.search(r"(\d+) passed(?:,\s*(\d+) failed)?", output, re.IGNORECASE)
        if pytest_match:
            results.unit_passed = int(pytest_match.group(1))
            if pytest_match.group(2):
                results.unit_failed = int(pytest_match.group(2))

        # Try jest format: "Tests: X passed, Y failed, Z total"
        jest_match = re.search(r"Tests:\s*(\d+)\s*passed,\s*(\d+)\s*failed", output, re.IGNORECASE)
        if jest_match:
            results.unit_passed = int(jest_match.group(1))
            results.unit_failed = int(jest_match.group(2))

        # Try coverage percentage
        coverage_match = re.search(
            r"(\d+(?:\.\d+)?)\s*%\s*(?:coverage|covered)", output, re.IGNORECASE
        )
        if coverage_match:
            results.coverage_percentage = float(coverage_match.group(1))

        return results

    def _parse_git_diff(self, diff_output: str) -> list[FileChange]:
        """Parse git diff to extract file changes."""
        import re

        changes = []
        current_file = None
        lines_added = 0
        lines_removed = 0

        for line in diff_output.split("\n"):
            # New file header
            if line.startswith("diff --git"):
                # Save previous file
                if current_file:
                    changes.append(
                        FileChange(
                            path=current_file,
                            lines_added=lines_added,
                            lines_removed=lines_removed,
                        )
                    )

                # Extract filename
                match = re.search(r"b/(.+)$", line)
                if match:
                    current_file = match.group(1)
                lines_added = 0
                lines_removed = 0

            # Count additions/removals
            elif line.startswith("+") and not line.startswith("+++"):
                lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                lines_removed += 1

            # Detect new file
            elif line.startswith("new file mode"):
                if changes and changes[-1].path == current_file:
                    pass  # Will update later
                # Mark as created when we save

        # Save last file
        if current_file:
            changes.append(
                FileChange(
                    path=current_file,
                    lines_added=lines_added,
                    lines_removed=lines_removed,
                )
            )

        return changes

    def _extract_from_implementation(self, output: str) -> dict[str, Any]:
        """Extract features, endpoints, components from implementation output."""
        extracted: dict[str, Any] = {
            "features": [],
            "endpoints": [],
            "components": [],
            "notes": "",
        }

        # Look for structured output markers
        import re

        # Features: "Implemented: ..." or "Added: ..."
        for match in re.finditer(
            r"(?:Implemented|Added|Created):\s*(.+?)(?:\n|$)", output, re.IGNORECASE
        ):
            extracted["features"].append(match.group(1).strip())

        # Endpoints: "GET /api/..." or "POST /api/..."
        for match in re.finditer(r"(GET|POST|PUT|DELETE|PATCH)\s+(/[^\s]+)", output):
            extracted["endpoints"].append(f"{match.group(1)} {match.group(2)}")

        # Components: "Component: ..." or React component patterns
        for match in re.finditer(
            r"(?:Component|function|const)\s+([A-Z][a-zA-Z]+)(?:\s*[=:(])", output
        ):
            extracted["components"].append(match.group(1))

        # Extract any notes section
        notes_match = re.search(
            r"(?:Notes?|Implementation Notes?):\s*(.+?)(?:\n\n|$)",
            output,
            re.IGNORECASE | re.DOTALL,
        )
        if notes_match:
            extracted["notes"] = notes_match.group(1).strip()

        return extracted

    def save_uat(self, uat: UATDocument, format: str = "both") -> dict[str, Path]:
        """Save UAT document to files.

        Args:
            uat: UAT document to save
            format: "markdown", "json", or "both"

        Returns:
            Dict of format to file path
        """
        self.uat_dir.mkdir(parents=True, exist_ok=True)

        saved = {}
        base_name = f"UAT-{uat.task_id}-{uat.generated_at.strftime('%Y%m%d-%H%M%S')}"

        if format in ("markdown", "both"):
            md_path = self.uat_dir / f"{base_name}.md"
            md_path.write_text(uat.to_markdown())
            saved["markdown"] = md_path
            logger.info(f"Saved UAT markdown: {md_path}")

        if format in ("json", "both"):
            json_path = self.uat_dir / f"{base_name}.json"
            json_path.write_text(json.dumps(uat.to_dict(), indent=2))
            saved["json"] = json_path
            logger.info(f"Saved UAT JSON: {json_path}")

        return saved

    def list_uats(self) -> list[Path]:
        """List all UAT documents in the project."""
        if not self.uat_dir.exists():
            return []

        return sorted(self.uat_dir.glob("UAT-*.md"))

    def get_latest_uat(self, task_id: Optional[str] = None) -> Optional[Path]:
        """Get the most recent UAT document.

        Args:
            task_id: Optional task ID to filter by

        Returns:
            Path to latest UAT or None
        """
        uats = self.list_uats()

        if task_id:
            uats = [u for u in uats if task_id in u.name]

        return uats[-1] if uats else None


def create_uat_generator(project_dir: Path) -> UATGenerator:
    """Create a UAT generator for a project.

    Args:
        project_dir: Project directory

    Returns:
        Configured UATGenerator
    """
    return UATGenerator(project_dir)


def generate_uat_from_verification(
    project_dir: Path,
    task: dict,
    phase: int,
    verification_result: dict,
) -> UATDocument:
    """Convenience function to generate UAT from verification node output.

    Args:
        project_dir: Project directory
        task: Task dictionary
        phase: Phase number
        verification_result: Result from verify_task node

    Returns:
        Generated UAT document
    """
    generator = create_uat_generator(project_dir)

    return generator.generate_from_task(
        task=task,
        phase=phase,
        test_output=verification_result.get("test_output"),
        git_diff=verification_result.get("git_diff"),
        implementation_output=verification_result.get("implementation_output"),
    )
