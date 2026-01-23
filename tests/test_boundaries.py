"""Tests for file boundary enforcement."""

import tempfile
from pathlib import Path

import pytest

from orchestrator.utils.boundaries import (
    ORCHESTRATOR_FORBIDDEN_PATTERNS,
    ORCHESTRATOR_WRITABLE_PATTERNS,
    OrchestratorBoundaryError,
    ensure_orchestrator_can_write,
    get_writable_paths_info,
    is_project_config,
    is_workflow_path,
    validate_orchestrator_write,
)


@pytest.fixture
def project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        # Create some subdirectories
        (project / ".workflow").mkdir()
        (project / ".workflow" / "phases").mkdir()
        (project / "src").mkdir()
        (project / "tests").mkdir()
        yield project


class TestValidateOrchestratorWrite:
    """Tests for validate_orchestrator_write function."""

    def test_allows_workflow_directory(self, project_dir):
        """Orchestrator can write to .workflow/ directory."""
        target = project_dir / ".workflow" / "state.json"
        assert validate_orchestrator_write(project_dir, target) is True

    def test_allows_workflow_phases(self, project_dir):
        """Orchestrator can write to .workflow/phases/ subdirectory."""
        target = project_dir / ".workflow" / "phases" / "planning" / "plan.json"
        assert validate_orchestrator_write(project_dir, target) is True

    def test_allows_project_config(self, project_dir):
        """Orchestrator can write to .project-config.json."""
        target = project_dir / ".project-config.json"
        assert validate_orchestrator_write(project_dir, target) is True

    def test_denies_src_directory(self, project_dir):
        """Orchestrator cannot write to src/ directory."""
        target = project_dir / "src" / "main.py"
        assert validate_orchestrator_write(project_dir, target) is False

    def test_denies_tests_directory(self, project_dir):
        """Orchestrator cannot write to tests/ directory."""
        target = project_dir / "tests" / "test_main.py"
        assert validate_orchestrator_write(project_dir, target) is False

    def test_denies_claude_md(self, project_dir):
        """Orchestrator cannot write to CLAUDE.md."""
        target = project_dir / "CLAUDE.md"
        assert validate_orchestrator_write(project_dir, target) is False

    def test_denies_product_md(self, project_dir):
        """Orchestrator cannot write to PRODUCT.md."""
        target = project_dir / "PRODUCT.md"
        assert validate_orchestrator_write(project_dir, target) is False

    def test_denies_gemini_md(self, project_dir):
        """Orchestrator cannot write to GEMINI.md."""
        target = project_dir / "GEMINI.md"
        assert validate_orchestrator_write(project_dir, target) is False

    def test_denies_cursor_rules(self, project_dir):
        """Orchestrator cannot write to .cursor/ directory."""
        target = project_dir / ".cursor" / "rules"
        assert validate_orchestrator_write(project_dir, target) is False

    def test_denies_python_files_at_root(self, project_dir):
        """Orchestrator cannot write to Python files at project root."""
        target = project_dir / "script.py"
        assert validate_orchestrator_write(project_dir, target) is False

    def test_denies_typescript_files(self, project_dir):
        """Orchestrator cannot write to TypeScript files."""
        target = project_dir / "app.ts"
        assert validate_orchestrator_write(project_dir, target) is False

    def test_denies_path_outside_project(self, project_dir):
        """Orchestrator cannot write outside project directory."""
        target = project_dir.parent / "outside.txt"
        assert validate_orchestrator_write(project_dir, target) is False

    def test_handles_relative_paths(self, project_dir):
        """Function handles relative path resolution."""
        # This should still work with paths that need resolution
        target = project_dir / ".workflow" / ".." / ".workflow" / "state.json"
        assert validate_orchestrator_write(project_dir, target) is True

    def test_denies_lib_directory(self, project_dir):
        """Orchestrator cannot write to lib/ directory."""
        target = project_dir / "lib" / "utils.py"
        assert validate_orchestrator_write(project_dir, target) is False

    def test_denies_app_directory(self, project_dir):
        """Orchestrator cannot write to app/ directory."""
        target = project_dir / "app" / "components" / "button.tsx"
        assert validate_orchestrator_write(project_dir, target) is False


class TestEnsureOrchestratorCanWrite:
    """Tests for ensure_orchestrator_can_write function."""

    def test_allows_valid_paths(self, project_dir):
        """No exception for valid paths."""
        target = project_dir / ".workflow" / "state.json"
        ensure_orchestrator_can_write(project_dir, target)  # Should not raise

    def test_raises_for_invalid_paths(self, project_dir):
        """Raises OrchestratorBoundaryError for invalid paths."""
        target = project_dir / "src" / "main.py"
        with pytest.raises(OrchestratorBoundaryError) as exc_info:
            ensure_orchestrator_can_write(project_dir, target)
        assert "src/main.py" in str(exc_info.value)

    def test_error_contains_path_info(self, project_dir):
        """Error message contains relevant path information."""
        target = project_dir / "CLAUDE.md"
        with pytest.raises(OrchestratorBoundaryError) as exc_info:
            ensure_orchestrator_can_write(project_dir, target)
        error = exc_info.value
        assert error.path == target.resolve()
        assert error.project_dir == project_dir.resolve()


class TestOrchestratorBoundaryError:
    """Tests for OrchestratorBoundaryError exception."""

    def test_default_message(self, project_dir):
        """Default error message is informative."""
        target = project_dir / "bad.py"
        error = OrchestratorBoundaryError(target, project_dir)
        assert "bad.py" in str(error)
        assert ".workflow/" in str(error)

    def test_custom_message(self, project_dir):
        """Custom message can be provided."""
        target = project_dir / "bad.py"
        error = OrchestratorBoundaryError(target, project_dir, "Custom error")
        assert str(error) == "Custom error"


class TestIsWorkflowPath:
    """Tests for is_workflow_path function."""

    def test_workflow_root(self, project_dir):
        """Detects .workflow directory itself."""
        target = project_dir / ".workflow"
        assert is_workflow_path(project_dir, target) is True

    def test_workflow_file(self, project_dir):
        """Detects files in .workflow/."""
        target = project_dir / ".workflow" / "state.json"
        assert is_workflow_path(project_dir, target) is True

    def test_workflow_nested(self, project_dir):
        """Detects nested paths in .workflow/."""
        target = project_dir / ".workflow" / "phases" / "planning" / "plan.json"
        assert is_workflow_path(project_dir, target) is True

    def test_non_workflow_path(self, project_dir):
        """Returns False for non-workflow paths."""
        target = project_dir / "src" / "main.py"
        assert is_workflow_path(project_dir, target) is False


class TestIsProjectConfig:
    """Tests for is_project_config function."""

    def test_project_config(self, project_dir):
        """Detects .project-config.json."""
        target = project_dir / ".project-config.json"
        assert is_project_config(project_dir, target) is True

    def test_not_project_config(self, project_dir):
        """Returns False for other paths."""
        target = project_dir / "config.json"
        assert is_project_config(project_dir, target) is False

    def test_nested_project_config(self, project_dir):
        """Returns False for nested config files."""
        target = project_dir / "subdir" / ".project-config.json"
        assert is_project_config(project_dir, target) is False


class TestGetWritablePathsInfo:
    """Tests for get_writable_paths_info function."""

    def test_returns_patterns(self):
        """Returns information about writable patterns."""
        info = get_writable_paths_info()
        assert "writable_patterns" in info
        assert "forbidden_patterns" in info
        assert "description" in info

    def test_patterns_match_constants(self):
        """Returned patterns match module constants."""
        info = get_writable_paths_info()
        assert info["writable_patterns"] == ORCHESTRATOR_WRITABLE_PATTERNS
        assert info["forbidden_patterns"] == ORCHESTRATOR_FORBIDDEN_PATTERNS

    def test_returns_copies(self):
        """Returns copies to prevent mutation."""
        info = get_writable_paths_info()
        info["writable_patterns"].append("new/**")
        # Original should be unchanged
        assert "new/**" not in ORCHESTRATOR_WRITABLE_PATTERNS


class TestPatternMatching:
    """Tests for pattern matching edge cases."""

    def test_deep_workflow_paths(self, project_dir):
        """Handles deeply nested .workflow paths."""
        target = project_dir / ".workflow" / "a" / "b" / "c" / "d" / "file.json"
        assert validate_orchestrator_write(project_dir, target) is True

    def test_workflow_like_name_outside(self, project_dir):
        """Doesn't match workflow-like names outside .workflow/."""
        target = project_dir / "src" / ".workflow" / "state.json"
        # This is inside src/, which is forbidden
        assert validate_orchestrator_write(project_dir, target) is False

    def test_various_code_extensions(self, project_dir):
        """Blocks various code file extensions."""
        extensions = [".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs"]
        for ext in extensions:
            target = project_dir / f"file{ext}"
            assert validate_orchestrator_write(project_dir, target) is False, f"Should block {ext}"

    def test_test_directory_variations(self, project_dir):
        """Blocks both 'test' and 'tests' directories."""
        test_dirs = ["test", "tests"]
        for test_dir in test_dirs:
            target = project_dir / test_dir / "test_main.py"
            assert (
                validate_orchestrator_write(project_dir, target) is False
            ), f"Should block {test_dir}/"
