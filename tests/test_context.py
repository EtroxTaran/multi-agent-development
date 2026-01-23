"""Tests for context management and drift detection."""

import tempfile
from pathlib import Path

import pytest

from orchestrator.utils.context import ContextManager, ContextState, DriftResult, FileChecksum


@pytest.fixture
def temp_project():
    """Create a temporary project with context files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Create AGENTS.md
        (project_dir / "AGENTS.md").write_text("# Agent Rules\nVersion 1.0")

        # Create PRODUCT.md
        (project_dir / "PRODUCT.md").write_text("# Product Spec\nFeature X")

        # Create GEMINI.md
        (project_dir / "GEMINI.md").write_text("# Gemini Context")

        # Create .cursor/rules
        cursor_dir = project_dir / ".cursor"
        cursor_dir.mkdir()
        (cursor_dir / "rules").write_text("Cursor rules here")

        yield project_dir


class TestContextManager:
    """Tests for ContextManager."""

    def test_init(self, temp_project):
        """Test initialization."""
        manager = ContextManager(temp_project)
        assert manager.project_dir == temp_project
        assert len(manager._tracked_files) == 5  # Default tracked files

    def test_compute_checksum(self, temp_project):
        """Test checksum computation."""
        manager = ContextManager(temp_project)
        file_path = temp_project / "AGENTS.md"

        checksum = manager.compute_checksum(file_path)
        assert len(checksum) == 64  # SHA-256 is 64 hex chars
        assert checksum.isalnum()

    def test_compute_checksum_nonexistent_file(self, temp_project):
        """Test checksum for non-existent file returns empty string."""
        manager = ContextManager(temp_project)
        checksum = manager.compute_checksum(temp_project / "nonexistent.md")
        assert checksum == ""

    def test_get_file_info(self, temp_project):
        """Test getting file information."""
        manager = ContextManager(temp_project)
        file_path = temp_project / "AGENTS.md"

        info = manager.get_file_info(file_path)

        assert info is not None
        assert info.path == "AGENTS.md"
        assert len(info.checksum) == 64
        assert info.size > 0
        assert info.last_modified is not None

    def test_get_file_info_nonexistent(self, temp_project):
        """Test getting info for non-existent file."""
        manager = ContextManager(temp_project)
        info = manager.get_file_info(temp_project / "nonexistent.md")
        assert info is None

    def test_capture_context(self, temp_project):
        """Test capturing context state."""
        manager = ContextManager(temp_project)
        context = manager.capture_context()

        assert isinstance(context, ContextState)
        assert "agents" in context.files
        assert "product" in context.files
        assert context.version == "1.0"
        assert context.captured_at is not None

    def test_add_tracked_file(self, temp_project):
        """Test adding a tracked file."""
        manager = ContextManager(temp_project)

        # Create a new file to track
        custom_file = temp_project / "custom.md"
        custom_file.write_text("Custom content")

        manager.add_tracked_file("custom", "custom.md")
        context = manager.capture_context()

        assert "custom" in context.files
        assert context.files["custom"].path == "custom.md"

    def test_remove_tracked_file(self, temp_project):
        """Test removing a tracked file."""
        manager = ContextManager(temp_project)
        manager.remove_tracked_file("gemini")

        context = manager.capture_context()
        assert "gemini" not in context.files

    def test_validate_context_no_drift(self, temp_project):
        """Test validation when no drift."""
        manager = ContextManager(temp_project)
        stored = manager.capture_context()

        result = manager.validate_context(stored)

        assert not result.has_drift
        assert len(result.changed_files) == 0
        assert len(result.added_files) == 0
        assert len(result.removed_files) == 0

    def test_validate_context_with_drift(self, temp_project):
        """Test validation when files change."""
        manager = ContextManager(temp_project)
        stored = manager.capture_context()

        # Modify a file
        (temp_project / "AGENTS.md").write_text("# Modified content")

        result = manager.validate_context(stored)

        assert result.has_drift
        assert "agents" in result.changed_files
        assert "agents" in result.details

    def test_validate_context_added_file(self, temp_project):
        """Test validation when file is added."""
        manager = ContextManager(temp_project)

        # Remove CLAUDE.md from tracking for this test
        manager.remove_tracked_file("claude")
        stored = manager.capture_context()

        # Create CLAUDE.md and add back to tracking
        (temp_project / "CLAUDE.md").write_text("# Claude")
        manager.add_tracked_file("claude", "CLAUDE.md")

        result = manager.validate_context(stored)

        assert result.has_drift
        assert "claude" in result.added_files

    def test_validate_context_removed_file(self, temp_project):
        """Test validation when file is removed."""
        manager = ContextManager(temp_project)
        stored = manager.capture_context()

        # Delete a file
        (temp_project / "GEMINI.md").unlink()

        result = manager.validate_context(stored)

        assert result.has_drift
        assert "gemini" in result.removed_files

    def test_get_drift_summary(self, temp_project):
        """Test generating drift summary."""
        manager = ContextManager(temp_project)
        stored = manager.capture_context()

        # Modify a file
        (temp_project / "AGENTS.md").write_text("# Modified content here")

        result = manager.validate_context(stored)
        summary = manager.get_drift_summary(result)

        assert "Context drift detected" in summary
        assert "Modified" in summary
        assert "agents" in summary

    def test_get_drift_summary_no_drift(self, temp_project):
        """Test drift summary when no drift."""
        manager = ContextManager(temp_project)
        result = DriftResult(has_drift=False)

        summary = manager.get_drift_summary(result)
        assert "No context drift detected" in summary

    def test_save_and_load_snapshot(self, temp_project):
        """Test saving and loading context snapshot."""
        manager = ContextManager(temp_project)
        snapshot_path = temp_project / ".workflow" / "context-snapshot.json"

        # Save snapshot
        saved = manager.save_context_snapshot(snapshot_path)

        assert snapshot_path.exists()
        assert isinstance(saved, ContextState)

        # Load snapshot
        loaded = manager.load_context_snapshot(snapshot_path)

        assert loaded is not None
        assert loaded.files.keys() == saved.files.keys()

    def test_load_snapshot_nonexistent(self, temp_project):
        """Test loading non-existent snapshot."""
        manager = ContextManager(temp_project)
        result = manager.load_context_snapshot(temp_project / "nonexistent.json")
        assert result is None


class TestContextState:
    """Tests for ContextState dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        state = ContextState()
        state.files["test"] = FileChecksum(
            path="test.md",
            checksum="abc123",
            last_modified="2024-01-01T00:00:00",
            size=100,
        )

        data = state.to_dict()

        assert "files" in data
        assert "captured_at" in data
        assert "version" in data
        assert data["files"]["test"]["path"] == "test.md"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "files": {
                "test": {
                    "path": "test.md",
                    "checksum": "abc123",
                    "last_modified": "2024-01-01T00:00:00",
                    "size": 100,
                }
            },
            "captured_at": "2024-01-01T00:00:00",
            "version": "1.0",
        }

        state = ContextState.from_dict(data)

        assert "test" in state.files
        assert state.files["test"].path == "test.md"
        assert state.version == "1.0"


class TestFileChecksum:
    """Tests for FileChecksum dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        checksum = FileChecksum(
            path="test.md",
            checksum="abc123",
            last_modified="2024-01-01T00:00:00",
            size=100,
        )

        data = checksum.to_dict()

        assert data["path"] == "test.md"
        assert data["checksum"] == "abc123"
        assert data["size"] == 100

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "path": "test.md",
            "checksum": "abc123",
            "last_modified": "2024-01-01T00:00:00",
            "size": 100,
        }

        checksum = FileChecksum.from_dict(data)

        assert checksum.path == "test.md"
        assert checksum.checksum == "abc123"


class TestDriftResult:
    """Tests for DriftResult dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = DriftResult(
            has_drift=True,
            changed_files=["agents"],
            added_files=["custom"],
            removed_files=[],
            details={"agents": {"old_checksum": "abc", "new_checksum": "def"}},
        )

        data = result.to_dict()

        assert data["has_drift"] is True
        assert "agents" in data["changed_files"]
        assert "custom" in data["added_files"]
