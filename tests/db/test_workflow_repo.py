"""Tests for workflow repository.

Tests the WorkflowRepository class and WorkflowState dataclass
from orchestrator.db.repositories.workflow module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.db.repositories.workflow import (
    WorkflowRepository,
    WorkflowState,
    get_workflow_repository,
)


class TestWorkflowState:
    """Tests for the WorkflowState dataclass."""

    def test_workflow_state_defaults(self):
        """Test WorkflowState default values."""
        state = WorkflowState()
        assert state.project_dir == ""
        assert state.current_phase == 1
        assert state.phase_status == {}
        assert state.iteration_count == 0
        assert state.plan is None
        assert state.execution_mode == "afk"

    def test_workflow_state_from_dict(self):
        """Test creating WorkflowState from dictionary."""
        data = {
            "project_dir": "/test/project",
            "current_phase": 2,
            "phase_status": {"1": {"status": "completed"}},
            "iteration_count": 5,
            "execution_mode": "hitl",
        }
        state = WorkflowState.from_dict(data)

        assert state.project_dir == "/test/project"
        assert state.current_phase == 2
        assert state.phase_status == {"1": {"status": "completed"}}
        assert state.iteration_count == 5
        assert state.execution_mode == "hitl"

    def test_workflow_state_from_dict_with_datetime(self):
        """Test creating WorkflowState with datetime strings."""
        data = {
            "created_at": "2024-01-15T10:30:00",
            "updated_at": "2024-01-15T11:00:00+00:00",
        }
        state = WorkflowState.from_dict(data)

        assert state.created_at is not None
        assert state.updated_at is not None

    def test_workflow_state_to_dict(self, sample_workflow_state):
        """Test converting WorkflowState to dictionary."""
        data = sample_workflow_state.to_dict()

        assert "project_dir" in data
        assert "current_phase" in data
        assert "phase_status" in data
        assert "created_at" not in data  # Default excludes timestamps

    def test_workflow_state_to_dict_with_timestamps(self, sample_workflow_state):
        """Test converting WorkflowState to dictionary with timestamps."""
        data = sample_workflow_state.to_dict(include_timestamps=True)

        assert "created_at" in data
        assert "updated_at" in data


class TestWorkflowRepository:
    """Tests for the WorkflowRepository class."""

    @pytest.fixture
    def workflow_repo(self):
        """Create a WorkflowRepository for testing."""
        return WorkflowRepository("test-project")

    @pytest.fixture
    def mock_conn(self):
        """Create a mock database connection."""
        conn = MagicMock()
        conn.query = AsyncMock(return_value=[])
        conn.create = AsyncMock(return_value={"id": "workflow_state:state"})
        conn.update = AsyncMock(return_value={"id": "workflow_state:state"})
        conn.delete = AsyncMock(return_value=True)
        conn.live = AsyncMock(return_value="live-uuid")
        return conn

    def test_repository_init(self, workflow_repo):
        """Test repository initialization."""
        assert workflow_repo.project_name == "test-project"
        assert workflow_repo.table_name == "workflow_state"

    @pytest.mark.asyncio
    async def test_get_state_returns_none_when_empty(self, workflow_repo, mock_conn):
        """Test get_state returns None when no state exists."""
        mock_conn.query = AsyncMock(return_value=[])

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.get_state()

            assert result is None

    @pytest.mark.asyncio
    async def test_get_state_returns_state(self, workflow_repo, mock_conn):
        """Test get_state returns WorkflowState when exists."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 2,
                    "phase_status": {},
                    "iteration_count": 1,
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.get_state()

            assert result is not None
            assert isinstance(result, WorkflowState)
            assert result.current_phase == 2

    @pytest.mark.asyncio
    async def test_initialize_state(self, workflow_repo, mock_conn):
        """Test initializing workflow state."""
        mock_conn.query = AsyncMock(return_value=[])  # No existing state

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.initialize_state("/test/project", execution_mode="hitl")

            assert result is not None
            assert result.project_dir == "/test/project"
            assert result.execution_mode == "hitl"
            assert result.current_phase == 1
            mock_conn.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_state_returns_existing(self, workflow_repo, mock_conn):
        """Test initialize_state returns existing state if present."""
        existing_state = {
            "project_dir": "/existing",
            "current_phase": 3,
            "phase_status": {},
            "iteration_count": 5,
        }
        mock_conn.query = AsyncMock(return_value=[existing_state])

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.initialize_state("/new/project")

            # Should return existing state
            assert result.project_dir == "/existing"
            assert result.current_phase == 3
            mock_conn.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_state(self, workflow_repo, mock_conn):
        """Test updating workflow state."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 3,
                    "phase_status": {},
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.update_state(current_phase=3)

            assert result is not None
            mock_conn.query.assert_called()

    @pytest.mark.asyncio
    async def test_set_phase(self, workflow_repo, mock_conn):
        """Test setting current phase."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 1,
                    "phase_status": {"1": {"status": "pending", "attempts": 0}},
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.set_phase(2, "in_progress")

            assert result is not None

    @pytest.mark.asyncio
    async def test_set_phase_no_state(self, workflow_repo, mock_conn):
        """Test set_phase returns None when no state exists."""
        mock_conn.query = AsyncMock(return_value=[])

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.set_phase(2)

            assert result is None

    @pytest.mark.asyncio
    async def test_increment_iteration(self, workflow_repo, mock_conn):
        """Test incrementing iteration counter."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 1,
                    "phase_status": {},
                    "iteration_count": 6,  # After increment
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.increment_iteration()

            assert result is not None
            assert result.iteration_count == 6

    @pytest.mark.asyncio
    async def test_set_plan(self, workflow_repo, mock_conn):
        """Test setting implementation plan."""
        plan = {"plan_name": "Test", "tasks": []}
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 1,
                    "phase_status": {},
                    "plan": plan,
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.set_plan(plan)

            assert result is not None
            assert result.plan == plan

    @pytest.mark.asyncio
    async def test_set_validation_feedback(self, workflow_repo, mock_conn):
        """Test setting validation feedback."""
        feedback = {"score": 8.0, "approved": True}
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 2,
                    "phase_status": {},
                    "validation_feedback": {"cursor": feedback},
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.set_validation_feedback("cursor", feedback)

            assert result is not None

    @pytest.mark.asyncio
    async def test_set_verification_feedback(self, workflow_repo, mock_conn):
        """Test setting verification feedback."""
        feedback = {"score": 9.0, "approved": True}
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 4,
                    "phase_status": {},
                    "verification_feedback": {"gemini": feedback},
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.set_verification_feedback("gemini", feedback)

            assert result is not None

    @pytest.mark.asyncio
    async def test_set_implementation_result(self, workflow_repo, mock_conn):
        """Test setting implementation result."""
        impl_result = {"success": True, "files_created": ["main.py"]}
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 3,
                    "phase_status": {},
                    "implementation_result": impl_result,
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.set_implementation_result(impl_result)

            assert result is not None

    @pytest.mark.asyncio
    async def test_add_token_usage(self, workflow_repo, mock_conn):
        """Test adding token usage metrics."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 1,
                    "phase_status": {},
                    "token_usage": {"total_input": 100, "total_output": 50},
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.add_token_usage(100, 50, 0.01)

            assert result is not None

    @pytest.mark.asyncio
    async def test_reset_state(self, workflow_repo, mock_conn):
        """Test resetting workflow state."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 1,
                    "phase_status": {
                        "1": {"status": "pending", "attempts": 0},
                    },
                    "iteration_count": 0,
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.reset_state()

            assert result is not None

    @pytest.mark.asyncio
    async def test_reset_state_no_state(self, workflow_repo, mock_conn):
        """Test reset_state returns None when no state exists."""
        mock_conn.query = AsyncMock(return_value=[])

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.reset_state()

            assert result is None

    @pytest.mark.asyncio
    async def test_reset_to_phase(self, workflow_repo, mock_conn):
        """Test resetting to a specific phase."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 2,
                    "phase_status": {
                        "1": {"status": "completed"},
                        "2": {"status": "pending", "attempts": 0},
                        "3": {"status": "pending", "attempts": 0},
                    },
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.reset_to_phase(2)

            assert result is not None

    @pytest.mark.asyncio
    async def test_get_summary(self, workflow_repo, mock_conn):
        """Test getting workflow summary."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "project_dir": "/test",
                    "current_phase": 2,
                    "phase_status": {
                        "1": {"status": "completed"},
                        "2": {"status": "in_progress"},
                    },
                    "iteration_count": 3,
                    "plan": {"name": "Test"},
                }
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            summary = await workflow_repo.get_summary()

            assert summary["project_name"] == "test-project"
            assert summary["current_phase"] == 2
            assert summary["has_plan"] is True

    @pytest.mark.asyncio
    async def test_get_summary_no_state(self, workflow_repo, mock_conn):
        """Test get_summary when no state exists."""
        mock_conn.query = AsyncMock(return_value=[])

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            summary = await workflow_repo.get_summary()

            assert summary == {"status": "not_initialized"}

    @pytest.mark.asyncio
    async def test_record_git_commit(self, workflow_repo, mock_conn):
        """Test recording a git commit."""
        mock_conn.create = AsyncMock(
            return_value={"id": "git_commits:123", "commit_hash": "abc123"}
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await workflow_repo.record_git_commit(
                phase=3,
                commit_hash="abc123",
                message="Test commit",
                task_id="T1",
                files_changed=["main.py"],
            )

            assert result is not None
            mock_conn.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_git_commits(self, workflow_repo, mock_conn):
        """Test getting git commits."""
        mock_conn.query = AsyncMock(
            return_value=[
                {"commit_hash": "abc123", "message": "Commit 1"},
                {"commit_hash": "def456", "message": "Commit 2"},
            ]
        )

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            commits = await workflow_repo.get_git_commits()

            assert len(commits) == 2

    @pytest.mark.asyncio
    async def test_get_git_commits_by_phase(self, workflow_repo, mock_conn):
        """Test getting git commits filtered by phase."""
        mock_conn.query = AsyncMock(return_value=[{"commit_hash": "abc123", "phase": 3}])

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            commits = await workflow_repo.get_git_commits(phase=3)

            assert len(commits) == 1

    @pytest.mark.asyncio
    async def test_get_git_commits_by_task(self, workflow_repo, mock_conn):
        """Test getting git commits filtered by task."""
        mock_conn.query = AsyncMock(return_value=[{"commit_hash": "abc123", "task_id": "T1"}])

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            commits = await workflow_repo.get_git_commits(task_id="T1")

            assert len(commits) == 1

    @pytest.mark.asyncio
    async def test_watch_state(self, workflow_repo, mock_conn):
        """Test subscribing to state changes."""
        mock_conn.live = AsyncMock(return_value="live-uuid")

        with patch("orchestrator.db.repositories.workflow.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            def callback(data):
                pass

            live_id = await workflow_repo.watch_state(callback)

            assert live_id == "live-uuid"
            mock_conn.live.assert_called_once()


class TestGetWorkflowRepository:
    """Tests for get_workflow_repository function."""

    def test_get_workflow_repository_creates_new(self):
        """Test getting a new repository."""
        with patch("orchestrator.db.repositories.workflow._workflow_repos", {}):
            repo = get_workflow_repository("test-project")
            assert repo is not None
            assert repo.project_name == "test-project"

    def test_get_workflow_repository_reuses_existing(self):
        """Test reusing an existing repository."""
        with patch("orchestrator.db.repositories.workflow._workflow_repos", {}):
            repo1 = get_workflow_repository("test-project")
            repo2 = get_workflow_repository("test-project")
            assert repo1 is repo2

    def test_get_workflow_repository_different_projects(self):
        """Test getting repositories for different projects."""
        with patch("orchestrator.db.repositories.workflow._workflow_repos", {}):
            repo1 = get_workflow_repository("project-a")
            repo2 = get_workflow_repository("project-b")
            assert repo1 is not repo2
