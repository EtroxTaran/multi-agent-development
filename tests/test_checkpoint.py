"""Tests for checkpoint utility."""

import json
from datetime import datetime

import pytest

from orchestrator.utils.checkpoint import (
    Checkpoint,
    CheckpointManager,
    create_checkpoint_manager,
    quick_checkpoint,
)


class TestCheckpoint:
    """Tests for Checkpoint dataclass."""

    def test_creation(self):
        """Test basic creation."""
        checkpoint = Checkpoint(
            id="abc123",
            name="Before refactoring",
            notes="Save state before major changes",
            created_at=datetime.now(),
            phase=3,
            task_progress={"total": 10, "completed": 5, "in_progress": 1, "pending": 4},
            state_snapshot={},
        )
        assert checkpoint.id == "abc123"
        assert checkpoint.name == "Before refactoring"
        assert checkpoint.phase == 3

    def test_to_dict(self):
        """Test dictionary conversion."""
        now = datetime.now()
        checkpoint = Checkpoint(
            id="abc123",
            name="Test",
            notes="Notes",
            created_at=now,
            phase=2,
            task_progress={"total": 5},
            state_snapshot={"key": "value"},
        )
        d = checkpoint.to_dict()
        assert d["id"] == "abc123"
        assert d["created_at"] == now.isoformat()
        assert d["state_snapshot"] == {"key": "value"}

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "id": "abc123",
            "name": "Test",
            "notes": "Notes",
            "created_at": "2026-01-22T10:00:00",
            "phase": 3,
            "task_progress": {"total": 5},
            "state_snapshot": {},
            "files_snapshot": ["file1.py", "file2.py"],
        }
        checkpoint = Checkpoint.from_dict(data)
        assert checkpoint.id == "abc123"
        assert checkpoint.files_snapshot == ["file1.py", "file2.py"]

    def test_summary(self):
        """Test summary string generation."""
        checkpoint = Checkpoint(
            id="abc123456789",
            name="Before auth changes",
            notes="",
            created_at=datetime(2026, 1, 22, 10, 30),
            phase=3,
            task_progress={"total": 10, "completed": 5},
            state_snapshot={},
        )
        summary = checkpoint.summary()
        assert "[abc12345]" in summary
        assert "Before auth changes" in summary
        assert "Phase 3" in summary
        assert "5/10" in summary


class TestCheckpointManager:
    """Tests for CheckpointManager class."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create temporary project directory with workflow state."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        workflow_dir = project_dir / ".workflow"
        workflow_dir.mkdir()

        # Create a mock state file
        state = {
            "project_name": "test-project",
            "current_phase": 3,
            "phases": {
                "planning": {"status": "completed"},
                "validation": {"status": "completed"},
                "implementation": {"status": "in_progress"},
            },
            "tasks": [
                {"id": "T001", "status": "completed"},
                {"id": "T002", "status": "in_progress"},
                {"id": "T003", "status": "pending"},
            ],
        }
        (workflow_dir / "state.json").write_text(json.dumps(state))
        return project_dir

    def test_init(self, temp_project):
        """Test manager initialization."""
        manager = CheckpointManager(temp_project)
        assert manager.project_dir == temp_project
        assert manager.checkpoints_dir == temp_project / ".workflow" / "checkpoints"

    def test_create_checkpoint(self, temp_project):
        """Test creating a checkpoint."""
        manager = CheckpointManager(temp_project)
        checkpoint = manager.create_checkpoint(
            name="Before refactoring",
            notes="Save state before auth module changes",
        )

        assert checkpoint.name == "Before refactoring"
        assert checkpoint.notes == "Save state before auth module changes"
        assert checkpoint.phase == 3
        assert checkpoint.task_progress["total"] == 3
        assert checkpoint.task_progress["completed"] == 1

        # Check files were created
        checkpoint_dir = manager.checkpoints_dir / checkpoint.id
        assert checkpoint_dir.exists()
        assert (checkpoint_dir / "checkpoint.json").exists()
        assert (checkpoint_dir / "state.json").exists()

    def test_list_checkpoints_empty(self, temp_project):
        """Test listing checkpoints when none exist."""
        manager = CheckpointManager(temp_project)
        checkpoints = manager.list_checkpoints()
        assert checkpoints == []

    def test_list_checkpoints_with_items(self, temp_project):
        """Test listing checkpoints."""
        manager = CheckpointManager(temp_project)

        # Create some checkpoints
        manager.create_checkpoint("First", "First checkpoint")
        manager.create_checkpoint("Second", "Second checkpoint")

        checkpoints = manager.list_checkpoints()
        assert len(checkpoints) == 2
        assert checkpoints[0].name == "First"
        assert checkpoints[1].name == "Second"

    def test_get_checkpoint_by_full_id(self, temp_project):
        """Test getting checkpoint by full ID."""
        manager = CheckpointManager(temp_project)
        created = manager.create_checkpoint("Test", "Test notes")

        fetched = manager.get_checkpoint(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "Test"

    def test_get_checkpoint_by_partial_id(self, temp_project):
        """Test getting checkpoint by partial ID."""
        manager = CheckpointManager(temp_project)
        created = manager.create_checkpoint("Test", "")

        # Use first 4 characters
        fetched = manager.get_checkpoint(created.id[:4])
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_checkpoint_not_found(self, temp_project):
        """Test getting non-existent checkpoint."""
        manager = CheckpointManager(temp_project)
        fetched = manager.get_checkpoint("nonexistent")
        assert fetched is None

    def test_rollback_without_confirm(self, temp_project):
        """Test rollback without confirmation fails."""
        manager = CheckpointManager(temp_project)
        checkpoint = manager.create_checkpoint("Test", "")

        result = manager.rollback_to_checkpoint(checkpoint.id, confirm=False)
        assert result is False

    def test_rollback_with_confirm(self, temp_project):
        """Test rollback with confirmation succeeds."""
        manager = CheckpointManager(temp_project)

        # Create checkpoint
        checkpoint = manager.create_checkpoint("Before changes", "")

        # Modify state
        state_file = temp_project / ".workflow" / "state.json"
        state = json.loads(state_file.read_text())
        state["current_phase"] = 5  # Change phase
        state_file.write_text(json.dumps(state))

        # Rollback
        result = manager.rollback_to_checkpoint(checkpoint.id, confirm=True)
        assert result is True

        # Verify state was restored
        restored_state = json.loads(state_file.read_text())
        assert restored_state["current_phase"] == 3  # Back to original

    def test_delete_checkpoint(self, temp_project):
        """Test deleting a checkpoint."""
        manager = CheckpointManager(temp_project)
        checkpoint = manager.create_checkpoint("Test", "")

        # Delete
        result = manager.delete_checkpoint(checkpoint.id)
        assert result is True

        # Verify it's gone
        assert manager.get_checkpoint(checkpoint.id) is None
        assert checkpoint.id not in manager._load_index()

    def test_prune_old_checkpoints(self, temp_project):
        """Test pruning old checkpoints."""
        manager = CheckpointManager(temp_project)

        # Create 5 checkpoints
        for i in range(5):
            manager.create_checkpoint(f"Checkpoint {i}", "")

        assert len(manager.list_checkpoints()) == 5

        # Prune keeping only 2
        deleted = manager.prune_old_checkpoints(keep_count=2)
        assert deleted == 3
        assert len(manager.list_checkpoints()) == 2

    def test_include_files_snapshot(self, temp_project):
        """Test checkpoint with file snapshot."""
        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=temp_project, capture_output=True)

        # Create and add a file
        (temp_project / "test.py").write_text("# test")
        subprocess.run(["git", "add", "."], cwd=temp_project, capture_output=True)

        manager = CheckpointManager(temp_project)
        checkpoint = manager.create_checkpoint(
            "With files",
            "",
            include_files=True,
        )

        # Should have file list
        assert len(checkpoint.files_snapshot) > 0


class TestHelperFunctions:
    """Tests for module helper functions."""

    def test_create_checkpoint_manager(self, tmp_path):
        """Test factory function."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        manager = create_checkpoint_manager(project_dir)
        assert isinstance(manager, CheckpointManager)
        assert manager.project_dir == project_dir

    def test_quick_checkpoint(self, tmp_path):
        """Test convenience function."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        workflow_dir = project_dir / ".workflow"
        workflow_dir.mkdir()
        (workflow_dir / "state.json").write_text(json.dumps({"current_phase": 1}))

        checkpoint = quick_checkpoint(
            project_dir,
            name="Quick save",
            notes="Quick note",
        )

        assert checkpoint.name == "Quick save"
        assert checkpoint.notes == "Quick note"
