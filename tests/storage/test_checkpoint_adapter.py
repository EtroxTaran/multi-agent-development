"""Tests for checkpoint storage adapter."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.storage.base import CheckpointData
from orchestrator.storage.checkpoint_adapter import CheckpointStorageAdapter, get_checkpoint_storage


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        yield project_dir


@pytest.fixture
def mock_checkpoint_repository():
    """Create a mock checkpoint repository."""
    mock_repo = MagicMock()
    mock_checkpoint = MagicMock()
    mock_checkpoint.id = "test-checkpoint-id"
    mock_checkpoint.name = "test-checkpoint"
    mock_checkpoint.notes = None
    mock_checkpoint.phase = 2
    mock_checkpoint.state_snapshot = {}
    mock_checkpoint.task_progress = {}
    mock_checkpoint.files_snapshot = []
    mock_checkpoint.created_at = None

    # Methods called by the adapter (correct names)
    mock_repo.create_checkpoint = AsyncMock(return_value=mock_checkpoint)
    mock_repo.list_checkpoints = AsyncMock(return_value=[])
    mock_repo.get_checkpoint = AsyncMock(return_value=None)
    mock_repo.get_latest = AsyncMock(return_value=None)
    mock_repo.delete_checkpoint = AsyncMock(return_value=True)
    mock_repo.prune_old_checkpoints = AsyncMock(return_value=0)
    return mock_repo


@pytest.fixture
def mock_task_repository():
    """Create a mock task repository."""
    mock_repo = MagicMock()
    mock_repo.get_progress = AsyncMock(
        return_value={"total": 0, "completed": 0, "in_progress": 0, "pending": 0}
    )
    return mock_repo


@pytest.fixture
def mock_workflow_repository():
    """Create a mock workflow repository."""
    mock_repo = MagicMock()
    mock_state = MagicMock()
    mock_state.project_dir = "/tmp/test"
    mock_state.current_phase = 2
    mock_state.phase_status = {}
    mock_state.iteration_count = 1
    mock_state.plan = None
    mock_state.validation_feedback = {}
    mock_state.verification_feedback = {}
    mock_state.implementation_result = None
    mock_state.next_decision = None
    mock_state.execution_mode = "afk"
    mock_state.discussion_complete = False
    mock_state.research_complete = False
    mock_state.research_findings = {}
    mock_state.token_usage = {}
    mock_state.created_at = None
    mock_state.updated_at = None

    mock_repo.get_state = AsyncMock(return_value=mock_state)
    mock_repo.update_state = AsyncMock(return_value=mock_state)
    return mock_repo


class TestCheckpointStorageAdapter:
    """Tests for CheckpointStorageAdapter."""

    def test_init(self, temp_project):
        """Test adapter initialization."""
        adapter = CheckpointStorageAdapter(temp_project)
        assert adapter.project_dir == temp_project
        assert adapter.project_name == temp_project.name

    def test_create_checkpoint(
        self,
        temp_project,
        mock_checkpoint_repository,
        mock_task_repository,
        mock_workflow_repository,
    ):
        """Test creating a checkpoint."""
        with (
            patch(
                "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
                return_value=mock_checkpoint_repository,
            ),
            patch(
                "orchestrator.db.repositories.tasks.get_task_repository",
                return_value=mock_task_repository,
            ),
            patch(
                "orchestrator.db.repositories.workflow.get_workflow_repository",
                return_value=mock_workflow_repository,
            ),
        ):
            adapter = CheckpointStorageAdapter(temp_project)

            checkpoint = adapter.create_checkpoint(
                name="pre-refactor",
                notes="Before major refactoring",
            )

            assert isinstance(checkpoint, CheckpointData)
            assert checkpoint.name == "test-checkpoint"  # From mock
            assert checkpoint.id is not None
            mock_checkpoint_repository.create_checkpoint.assert_called_once()

    def test_list_checkpoints_empty(self, temp_project, mock_checkpoint_repository):
        """Test listing checkpoints when none exist."""
        with patch(
            "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
            return_value=mock_checkpoint_repository,
        ):
            adapter = CheckpointStorageAdapter(temp_project)
            checkpoints = adapter.list_checkpoints()
            assert checkpoints == []

    def test_list_checkpoints_after_create(self, temp_project, mock_checkpoint_repository):
        """Test listing checkpoints after creating some."""
        # Set up mock to return checkpoints
        mock_checkpoint_1 = MagicMock()
        mock_checkpoint_1.id = "cp-1"
        mock_checkpoint_1.name = "checkpoint-1"
        mock_checkpoint_1.notes = None
        mock_checkpoint_1.phase = 2
        mock_checkpoint_1.state_snapshot = {}
        mock_checkpoint_1.task_progress = {}
        mock_checkpoint_1.files_snapshot = []
        mock_checkpoint_1.created_at = None

        mock_checkpoint_2 = MagicMock()
        mock_checkpoint_2.id = "cp-2"
        mock_checkpoint_2.name = "checkpoint-2"
        mock_checkpoint_2.notes = None
        mock_checkpoint_2.phase = 2
        mock_checkpoint_2.state_snapshot = {}
        mock_checkpoint_2.task_progress = {}
        mock_checkpoint_2.files_snapshot = []
        mock_checkpoint_2.created_at = None

        mock_checkpoint_repository.list_checkpoints = AsyncMock(
            return_value=[mock_checkpoint_1, mock_checkpoint_2]
        )

        with patch(
            "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
            return_value=mock_checkpoint_repository,
        ):
            adapter = CheckpointStorageAdapter(temp_project)

            checkpoints = adapter.list_checkpoints()
            assert len(checkpoints) == 2

    def test_get_checkpoint(self, temp_project, mock_checkpoint_repository):
        """Test getting a checkpoint by ID."""
        # Set up mock to return checkpoint
        mock_checkpoint = MagicMock()
        mock_checkpoint.id = "test-id"
        mock_checkpoint.name = "test-checkpoint"
        mock_checkpoint.notes = None
        mock_checkpoint.phase = 2
        mock_checkpoint.state_snapshot = {}
        mock_checkpoint.task_progress = {}
        mock_checkpoint.files_snapshot = []
        mock_checkpoint.created_at = None

        mock_checkpoint_repository.get_checkpoint = AsyncMock(return_value=mock_checkpoint)

        with patch(
            "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
            return_value=mock_checkpoint_repository,
        ):
            adapter = CheckpointStorageAdapter(temp_project)
            retrieved = adapter.get_checkpoint("test-id")

            assert retrieved is not None
            assert retrieved.name == "test-checkpoint"

    def test_get_checkpoint_not_found(self, temp_project, mock_checkpoint_repository):
        """Test getting non-existent checkpoint."""
        with patch(
            "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
            return_value=mock_checkpoint_repository,
        ):
            adapter = CheckpointStorageAdapter(temp_project)
            checkpoint = adapter.get_checkpoint("nonexistent")
            assert checkpoint is None

    def test_get_latest_none(self, temp_project, mock_checkpoint_repository):
        """Test get_latest returns None when no checkpoints."""
        with patch(
            "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
            return_value=mock_checkpoint_repository,
        ):
            adapter = CheckpointStorageAdapter(temp_project)
            latest = adapter.get_latest()
            assert latest is None

    def test_get_latest(self, temp_project, mock_checkpoint_repository):
        """Test get_latest returns most recent checkpoint."""
        # Set up mock to return checkpoint
        mock_checkpoint = MagicMock()
        mock_checkpoint.id = "latest-id"
        mock_checkpoint.name = "third"
        mock_checkpoint.notes = None
        mock_checkpoint.phase = 2
        mock_checkpoint.state_snapshot = {}
        mock_checkpoint.task_progress = {}
        mock_checkpoint.files_snapshot = []
        mock_checkpoint.created_at = None

        mock_checkpoint_repository.get_latest = AsyncMock(return_value=mock_checkpoint)

        with patch(
            "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
            return_value=mock_checkpoint_repository,
        ):
            adapter = CheckpointStorageAdapter(temp_project)

            latest = adapter.get_latest()
            assert latest is not None
            assert latest.name == "third"

    def test_delete_checkpoint(self, temp_project, mock_checkpoint_repository):
        """Test deleting a checkpoint."""
        with patch(
            "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
            return_value=mock_checkpoint_repository,
        ):
            adapter = CheckpointStorageAdapter(temp_project)

            result = adapter.delete_checkpoint("test-id")
            assert result is True
            mock_checkpoint_repository.delete_checkpoint.assert_called_once_with("test-id")

    def test_prune_old_checkpoints(self, temp_project, mock_checkpoint_repository):
        """Test pruning old checkpoints."""
        # Set up mock to return deleted count
        mock_checkpoint_repository.prune_old_checkpoints = AsyncMock(return_value=3)

        with patch(
            "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
            return_value=mock_checkpoint_repository,
        ):
            adapter = CheckpointStorageAdapter(temp_project)

            deleted = adapter.prune_old_checkpoints(keep_count=2)
            assert deleted == 3

    def test_rollback_without_confirm(
        self,
        temp_project,
        mock_checkpoint_repository,
        mock_workflow_repository,
    ):
        """Test rollback requires confirm=True."""
        # Set up mock to return checkpoint
        mock_checkpoint = MagicMock()
        mock_checkpoint.id = "test-id"
        mock_checkpoint.name = "test"
        mock_checkpoint.notes = None
        mock_checkpoint.phase = 2
        mock_checkpoint.state_snapshot = {"current_phase": 2}
        mock_checkpoint.task_progress = {}
        mock_checkpoint.files_snapshot = []
        mock_checkpoint.created_at = None

        mock_checkpoint_repository.get_checkpoint = AsyncMock(return_value=mock_checkpoint)

        with (
            patch(
                "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
                return_value=mock_checkpoint_repository,
            ),
            patch(
                "orchestrator.db.repositories.workflow.get_workflow_repository",
                return_value=mock_workflow_repository,
            ),
        ):
            adapter = CheckpointStorageAdapter(temp_project)

            result = adapter.rollback_to_checkpoint("test-id", confirm=False)
            assert result is False

    def test_rollback_with_confirm(
        self,
        temp_project,
        mock_checkpoint_repository,
        mock_workflow_repository,
    ):
        """Test rollback with confirm=True."""
        # Set up mock to return checkpoint
        mock_checkpoint = MagicMock()
        mock_checkpoint.id = "test-id"
        mock_checkpoint.name = "test"
        mock_checkpoint.notes = None
        mock_checkpoint.phase = 2
        mock_checkpoint.state_snapshot = {"current_phase": 2, "iteration_count": 1}
        mock_checkpoint.task_progress = {}
        mock_checkpoint.files_snapshot = []
        mock_checkpoint.created_at = None

        mock_checkpoint_repository.get_checkpoint = AsyncMock(return_value=mock_checkpoint)

        with (
            patch(
                "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
                return_value=mock_checkpoint_repository,
            ),
            patch(
                "orchestrator.db.repositories.workflow.get_workflow_repository",
                return_value=mock_workflow_repository,
            ),
        ):
            adapter = CheckpointStorageAdapter(temp_project)

            result = adapter.rollback_to_checkpoint("test-id", confirm=True)
            assert result is True
            mock_workflow_repository.update_state.assert_called_once()


class TestGetCheckpointStorage:
    """Tests for get_checkpoint_storage factory function."""

    def test_returns_adapter(self, temp_project):
        """Test factory returns an adapter."""
        adapter = get_checkpoint_storage(temp_project)
        assert isinstance(adapter, CheckpointStorageAdapter)

    def test_caches_adapter(self, temp_project):
        """Test factory returns same adapter for same project."""
        adapter1 = get_checkpoint_storage(temp_project)
        adapter2 = get_checkpoint_storage(temp_project)
        assert adapter1 is adapter2
