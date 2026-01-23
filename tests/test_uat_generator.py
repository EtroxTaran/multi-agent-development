"""Tests for UAT generator utility."""

import json
from datetime import datetime

import pytest

from orchestrator.utils.uat_generator import (
    FileChange,
    TestResults,
    UATDocument,
    UATGenerator,
    create_uat_generator,
    generate_uat_from_verification,
)


class TestTestResults:
    """Tests for TestResults dataclass."""

    def test_default_values(self):
        """Test default values are zero."""
        results = TestResults()
        assert results.unit_passed == 0
        assert results.unit_failed == 0
        assert results.total_passed == 0
        assert results.total_failed == 0
        assert results.all_passed

    def test_total_calculations(self):
        """Test total passed/failed calculations."""
        results = TestResults(
            unit_passed=5,
            unit_failed=1,
            integration_passed=3,
            integration_failed=2,
            e2e_passed=1,
            e2e_failed=0,
        )
        assert results.total_passed == 9
        assert results.total_failed == 3
        assert not results.all_passed

    def test_all_passed_true(self):
        """Test all_passed when no failures."""
        results = TestResults(
            unit_passed=10,
            integration_passed=5,
            e2e_passed=2,
        )
        assert results.all_passed

    def test_to_dict(self):
        """Test dictionary conversion."""
        results = TestResults(unit_passed=5, unit_failed=1, coverage_percentage=85.5)
        d = results.to_dict()
        assert d["unit"]["passed"] == 5
        assert d["unit"]["failed"] == 1
        assert d["coverage_percentage"] == 85.5
        assert d["all_passed"] is False


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_default_values(self):
        """Test default values."""
        fc = FileChange(path="src/main.py")
        assert fc.lines_added == 0
        assert fc.lines_removed == 0
        assert fc.change_type == "modified"

    def test_to_dict(self):
        """Test dictionary conversion."""
        fc = FileChange(
            path="src/new.py",
            lines_added=50,
            lines_removed=0,
            change_type="created",
        )
        d = fc.to_dict()
        assert d["path"] == "src/new.py"
        assert d["lines_added"] == 50
        assert d["change_type"] == "created"


class TestUATDocument:
    """Tests for UATDocument dataclass."""

    def test_creation(self):
        """Test basic creation."""
        uat = UATDocument(
            task_id="T001",
            task_title="Implement login",
            phase=3,
        )
        assert uat.task_id == "T001"
        assert uat.phase == 3
        assert isinstance(uat.generated_at, datetime)

    def test_total_lines(self):
        """Test total lines calculations."""
        uat = UATDocument(
            task_id="T001",
            task_title="Test",
            phase=3,
            files_changed=[
                FileChange(path="a.py", lines_added=10, lines_removed=5),
                FileChange(path="b.py", lines_added=20, lines_removed=3),
            ],
        )
        assert uat.total_lines_added == 30
        assert uat.total_lines_removed == 8

    def test_to_markdown(self):
        """Test markdown generation."""
        uat = UATDocument(
            task_id="T001",
            task_title="Implement feature",
            phase=3,
            features_implemented=["Login form", "Password validation"],
            endpoints_created=["POST /api/login"],
            test_results=TestResults(unit_passed=5, coverage_percentage=80.0),
            verification_checklist=["Test login flow"],
        )
        md = uat.to_markdown()
        assert "# UAT Document - T001" in md
        assert "Login form" in md
        assert "POST /api/login" in md
        assert "80.0%" in md

    def test_to_dict(self):
        """Test dictionary conversion."""
        uat = UATDocument(
            task_id="T001",
            task_title="Test",
            phase=3,
            features_implemented=["Feature 1"],
        )
        d = uat.to_dict()
        assert d["task_id"] == "T001"
        assert d["features_implemented"] == ["Feature 1"]
        assert "generated_at" in d


class TestUATGenerator:
    """Tests for UATGenerator class."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create temporary project directory."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        (project_dir / ".workflow").mkdir()
        return project_dir

    def test_init(self, temp_project):
        """Test generator initialization."""
        generator = UATGenerator(temp_project)
        assert generator.project_dir == temp_project
        assert generator.uat_dir == temp_project / ".workflow" / "uat"

    def test_generate_from_task_basic(self, temp_project):
        """Test basic task UAT generation."""
        generator = UATGenerator(temp_project)
        task = {
            "id": "T001",
            "title": "Implement login",
            "acceptance_criteria": [
                "User can enter email",
                "User can enter password",
            ],
        }
        uat = generator.generate_from_task(task, phase=3)
        assert uat.task_id == "T001"
        assert uat.task_title == "Implement login"
        assert len(uat.acceptance_criteria) == 2
        assert len(uat.verification_checklist) == 2

    def test_parse_test_output_pytest(self, temp_project):
        """Test parsing pytest output."""
        generator = UATGenerator(temp_project)
        output = "collected 10 items\n\n10 passed, 2 failed\n"
        results = generator._parse_test_output(output)
        assert results.unit_passed == 10
        assert results.unit_failed == 2

    def test_parse_test_output_coverage(self, temp_project):
        """Test parsing coverage percentage."""
        generator = UATGenerator(temp_project)
        output = "Total coverage: 85.5% covered"
        results = generator._parse_test_output(output)
        assert results.coverage_percentage == 85.5

    def test_parse_git_diff(self, temp_project):
        """Test parsing git diff output."""
        generator = UATGenerator(temp_project)
        diff = """diff --git a/src/main.py b/src/main.py
--- a/src/main.py
+++ b/src/main.py
+line1
+line2
-oldline
diff --git a/src/new.py b/src/new.py
new file mode 100644
+newfile
"""
        changes = generator._parse_git_diff(diff)
        assert len(changes) == 2
        assert changes[0].path == "src/main.py"
        assert changes[0].lines_added == 2
        assert changes[0].lines_removed == 1

    def test_save_uat_markdown(self, temp_project):
        """Test saving UAT as markdown."""
        generator = UATGenerator(temp_project)
        uat = UATDocument(
            task_id="T001",
            task_title="Test",
            phase=3,
        )
        saved = generator.save_uat(uat, format="markdown")
        assert "markdown" in saved
        assert saved["markdown"].exists()
        assert saved["markdown"].suffix == ".md"

    def test_save_uat_json(self, temp_project):
        """Test saving UAT as JSON."""
        generator = UATGenerator(temp_project)
        uat = UATDocument(
            task_id="T001",
            task_title="Test",
            phase=3,
        )
        saved = generator.save_uat(uat, format="json")
        assert "json" in saved
        assert saved["json"].exists()
        content = json.loads(saved["json"].read_text())
        assert content["task_id"] == "T001"

    def test_save_uat_both(self, temp_project):
        """Test saving UAT in both formats."""
        generator = UATGenerator(temp_project)
        uat = UATDocument(
            task_id="T001",
            task_title="Test",
            phase=3,
        )
        saved = generator.save_uat(uat, format="both")
        assert "markdown" in saved
        assert "json" in saved
        assert saved["markdown"].exists()
        assert saved["json"].exists()

    def test_list_uats_empty(self, temp_project):
        """Test listing UATs when none exist."""
        generator = UATGenerator(temp_project)
        uats = generator.list_uats()
        assert uats == []

    def test_list_uats_with_files(self, temp_project):
        """Test listing UATs with saved files."""
        generator = UATGenerator(temp_project)
        # Create some UAT files
        uat1 = UATDocument(task_id="T001", task_title="Test1", phase=3)
        uat2 = UATDocument(task_id="T002", task_title="Test2", phase=3)
        generator.save_uat(uat1, format="markdown")
        generator.save_uat(uat2, format="markdown")

        uats = generator.list_uats()
        assert len(uats) == 2

    def test_get_latest_uat(self, temp_project):
        """Test getting latest UAT."""
        generator = UATGenerator(temp_project)
        uat = UATDocument(task_id="T001", task_title="Test", phase=3)
        generator.save_uat(uat, format="markdown")

        latest = generator.get_latest_uat()
        assert latest is not None
        assert "T001" in latest.name


class TestHelperFunctions:
    """Tests for module helper functions."""

    def test_create_uat_generator(self, tmp_path):
        """Test factory function."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        generator = create_uat_generator(project_dir)
        assert isinstance(generator, UATGenerator)
        assert generator.project_dir == project_dir

    def test_generate_uat_from_verification(self, tmp_path):
        """Test convenience function."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".workflow").mkdir()

        task = {"id": "T001", "title": "Test"}
        verification_result = {
            "test_output": "5 passed",
        }

        uat = generate_uat_from_verification(
            project_dir, task, phase=3, verification_result=verification_result
        )
        assert uat.task_id == "T001"
        assert uat.test_results.unit_passed == 5
