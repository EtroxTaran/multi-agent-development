"""Tests for workflow storage adapter."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from orchestrator.storage.workflow_adapter import (
    WorkflowStorageAdapter,
    get_workflow_storage,
)
from orchestrator.storage.surreal_store import SurrealWorkflowRepository
from orchestrator.storage.base import WorkflowStateData


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        yield project_dir


@pytest.fixture
def mock_workflow_repository():
    """Create a mock workflow repository."""
    mock_repo = MagicMock()
    mock_state = MagicMock()
    mock_state.project_dir = "/tmp/test"
    mock_state.current_phase = 1
    mock_state.phase_status = {
        "planning": {"status": "pending", "attempts": 0},
        "validation": {"status": "pending", "attempts": 0},
        "implementation": {"status": "pending", "attempts": 0},
        "verification": {"status": "pending", "attempts": 0},
        "completion": {"status": "pending", "attempts": 0},
    }
    mock_state.iteration_count = 0
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
    mock_repo.initialize_state = AsyncMock(return_value=mock_state)
    mock_repo.update_state = AsyncMock(return_value=mock_state)
    mock_repo.set_phase = AsyncMock(return_value=mock_state)
    # reset_state returns None in the new implementation
    mock_repo.reset_state = AsyncMock(return_value=None)
    mock_repo.get_summary = AsyncMock(
        return_value={"current_phase": 1, "project": "test"}
    )
    mock_repo.increment_iteration = AsyncMock(return_value=mock_state)
    mock_repo.set_plan = AsyncMock(return_value=mock_state)
    mock_repo.set_validation_feedback = AsyncMock(return_value=mock_state)
    mock_repo.set_verification_feedback = AsyncMock(return_value=mock_state)
    mock_repo.set_implementation_result = AsyncMock(return_value=mock_state)
    mock_repo.record_git_commit = AsyncMock(return_value={})
    mock_repo.get_git_commits = AsyncMock(return_value=[])
    mock_repo.reset_to_phase = AsyncMock(return_value=mock_state)
    return mock_repo


class TestWorkflowStorageAdapter:
    """Tests for WorkflowStorageAdapter."""

    def test_init(self, temp_project):
        """Test adapter initialization."""
        adapter = WorkflowStorageAdapter(temp_project)
        assert adapter.project_dir == temp_project
        assert adapter.project_name == temp_project.name

    def test_get_state_none(self, temp_project):
        """Test get_state returns None when no state exists."""
        mock_repo = MagicMock()
        mock_repo.get_state = AsyncMock(return_value=None)

        # Patch _get_db_backend directly to bypass conftest autouse fixture logic
        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_repo):
            adapter = WorkflowStorageAdapter(temp_project)
            state = adapter.get_state()
            assert state is None

    def test_get_state_exists(self, temp_project, mock_workflow_repository):
        """Test get_state returns state when exists."""
        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)
            state = adapter.get_state()

            assert state is not None
            # The repository returns whatever the DB returns. We mocked it to return a MagicMock.
            # In real usage it returns a Pydantic model. 
            # We just verify it returns the mock object.
            assert state.current_phase == 1

    def test_initialize_state(self, temp_project, mock_workflow_repository):
        """Test initializing workflow state."""
        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            state = adapter.initialize_state(
                project_dir=str(temp_project),
                execution_mode="hitl",
            )

            assert state is not None
            mock_workflow_repository.initialize_state.assert_called_once()

    def test_update_state(self, temp_project, mock_workflow_repository):
        """Test updating workflow state."""
        # Create updated state mock
        updated_state = MagicMock()
        updated_state.project_dir = str(temp_project)
        updated_state.current_phase = 2
        updated_state.iteration_count = 1
        
        mock_workflow_repository.update_state = AsyncMock(return_value=updated_state)

        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            state = adapter.update_state(
                current_phase=2,
                iteration_count=1,
            )

            assert state is not None
            assert state.current_phase == 2
            assert state.iteration_count == 1

    def test_set_phase_in_progress(self, temp_project, mock_workflow_repository):
        """Test setting phase to in_progress."""
        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            state = adapter.set_phase(1, status="in_progress")

            assert state is not None
            mock_workflow_repository.set_phase.assert_called_once_with(1, "in_progress")

    def test_set_phase_completed(self, temp_project, mock_workflow_repository):
        """Test setting phase to completed."""
        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            # Complete it
            state = adapter.set_phase(1, status="completed")
            assert state is not None

    def test_reset_state(self, temp_project, mock_workflow_repository):
        """Test resetting workflow state."""
        # reset_state returns None in new implementation
        mock_workflow_repository.reset_state = AsyncMock(return_value=None)

        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            state = adapter.reset_state()

            # Should return None
            assert state is None
            mock_workflow_repository.reset_state.assert_called_once()

    def test_get_summary(self, temp_project, mock_workflow_repository):
        """Test getting workflow summary."""
        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            summary = adapter.get_summary()

            assert isinstance(summary, dict)
            assert "current_phase" in summary

    def test_increment_iteration(self, temp_project, mock_workflow_repository):
        """Test incrementing iteration counter."""
        # Create updated state mocks
        state_count_1 = MagicMock()
        state_count_1.iteration_count = 1

        state_count_2 = MagicMock()
        state_count_2.iteration_count = 2

        mock_workflow_repository.increment_iteration = AsyncMock(
            side_effect=[state_count_1, state_count_2]
        )

        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            count = adapter.increment_iteration()
            assert count == 1

            count = adapter.increment_iteration()
            assert count == 2

    def test_set_plan(self, temp_project, mock_workflow_repository):
        """Test setting implementation plan."""
        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            plan = {
                "name": "Test Plan",
                "tasks": [{"id": "T1", "title": "Task 1"}],
            }

            state = adapter.set_plan(plan)
            assert state is not None
            mock_workflow_repository.set_plan.assert_called_once_with(plan)

    def test_set_validation_feedback(self, temp_project, mock_workflow_repository):
        """Test setting validation feedback."""
        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            feedback = {
                "score": 8,
                "approved": True,
                "comments": "Looks good",
            }

            state = adapter.set_validation_feedback("cursor", feedback)
            assert state is not None
            mock_workflow_repository.set_validation_feedback.assert_called_once_with(
                "cursor", feedback
            )

    def test_set_verification_feedback(self, temp_project, mock_workflow_repository):
        """Test setting verification feedback."""
        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            feedback = {
                "score": 9,
                "approved": True,
                "comments": "Code is solid",
            }

            state = adapter.set_verification_feedback("gemini", feedback)
            assert state is not None
            mock_workflow_repository.set_verification_feedback.assert_called_once_with(
                "gemini", feedback
            )

    def test_set_implementation_result(self, temp_project, mock_workflow_repository):
        """Test setting implementation result."""
        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            result = {
                "success": True,
                "files_created": ["src/main.py"],
                "tests_passed": True,
            }

            state = adapter.set_implementation_result(result)
            assert state is not None
            mock_workflow_repository.set_implementation_result.assert_called_once_with(
                result
            )

    def test_set_decision(self, temp_project, mock_workflow_repository):
        """Test setting next routing decision."""
        with patch.object(SurrealWorkflowRepository, "_get_db_backend", return_value=mock_workflow_repository):
            adapter = WorkflowStorageAdapter(temp_project)

            state = adapter.set_decision("continue")
            assert state is not None
            mock_workflow_repository.update_state.assert_called_once_with(
                next_decision="continue"
            )


class TestGetWorkflowStorage:
    """Tests for get_workflow_storage factory function."""

    def test_returns_adapter(self, temp_project):
        """Test factory returns an adapter."""
        adapter = get_workflow_storage(temp_project)
        assert isinstance(adapter, WorkflowStorageAdapter)

    def test_caches_adapter(self, temp_project):
        """Test factory returns same adapter for same project."""
        adapter1 = get_workflow_storage(temp_project)
        adapter2 = get_workflow_storage(temp_project)
        assert adapter1 is adapter2
