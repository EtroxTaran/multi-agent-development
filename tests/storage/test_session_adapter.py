"""Tests for session storage adapter."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from orchestrator.storage.session_adapter import (
    SessionStorageAdapter,
    get_session_storage,
)
from orchestrator.storage.base import SessionData


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        yield project_dir


@pytest.fixture
def mock_session_repository():
    """Create a mock session repository."""
    mock_repo = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "test-session-id"
    mock_session.task_id = "T1"
    mock_session.agent = "claude"
    mock_session.status = "active"
    mock_session.created_at = None
    mock_session.updated_at = None
    mock_session.closed_at = None
    mock_session.invocation_count = 0
    mock_session.total_cost_usd = 0.0

    # Methods called by the adapter
    mock_repo.create_session = AsyncMock(return_value=mock_session)
    mock_repo.get_session = AsyncMock(return_value=None)
    mock_repo.get_active_session = AsyncMock(return_value=None)
    mock_repo.close_task_sessions = AsyncMock(return_value=True)
    mock_repo.touch_session = AsyncMock(return_value=mock_session)
    mock_repo.record_invocation = AsyncMock(return_value=mock_session)
    mock_repo.find_all = AsyncMock(return_value=[])
    mock_repo.delete = AsyncMock(return_value=True)
    return mock_repo


class TestSessionStorageAdapter:
    """Tests for SessionStorageAdapter."""

    def test_init(self, temp_project):
        """Test adapter initialization."""
        adapter = SessionStorageAdapter(temp_project)
        assert adapter.project_dir == temp_project
        assert adapter.project_name == temp_project.name

    def test_create_session(self, temp_project, mock_session_repository):
        """Test creating a new session."""
        with patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repository,
        ):
            adapter = SessionStorageAdapter(temp_project)
            session = adapter.create_session("T1", agent="claude")

            assert isinstance(session, SessionData)
            assert session.task_id == "T1"
            assert session.agent == "claude"
            assert session.status == "active"

    def test_get_active_session_none(self, temp_project, mock_session_repository):
        """Test get_active_session returns None when no session."""
        with patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repository,
        ):
            adapter = SessionStorageAdapter(temp_project)
            session = adapter.get_active_session("nonexistent")
            assert session is None

    def test_get_active_session_exists(self, temp_project, mock_session_repository):
        """Test get_active_session returns session when exists."""
        # Set up mock to return a session
        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.task_id = "T1"
        mock_session.agent = "claude"
        mock_session.status = "active"
        mock_session.created_at = None
        mock_session.updated_at = None
        mock_session.closed_at = None
        mock_session.invocation_count = 0
        mock_session.total_cost_usd = 0.0

        mock_session_repository.get_active_session = AsyncMock(
            return_value=mock_session
        )

        with patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repository,
        ):
            adapter = SessionStorageAdapter(temp_project)
            session = adapter.get_active_session("T1")
            assert session is not None
            assert session.task_id == "T1"

    def test_get_resume_args_no_session(self, temp_project, mock_session_repository):
        """Test get_resume_args returns empty when no session."""
        with patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repository,
        ):
            adapter = SessionStorageAdapter(temp_project)
            args = adapter.get_resume_args("nonexistent")
            assert args == []

    def test_get_resume_args_with_session(self, temp_project, mock_session_repository):
        """Test get_resume_args returns args when session exists."""
        # Set up mock to return a session
        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.task_id = "T1"
        mock_session.agent = "claude"
        mock_session.status = "active"

        mock_session_repository.get_active_session = AsyncMock(
            return_value=mock_session
        )

        with patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repository,
        ):
            adapter = SessionStorageAdapter(temp_project)
            args = adapter.get_resume_args("T1")
            assert len(args) == 2
            assert args[0] == "--resume"

    def test_get_session_id_args(self, temp_project, mock_session_repository):
        """Test get_session_id_args returns session id args."""
        with patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repository,
        ):
            adapter = SessionStorageAdapter(temp_project)
            args = adapter.get_session_id_args("T1")
            assert len(args) == 2
            assert args[0] == "--session-id"

    def test_get_or_create_session_creates(self, temp_project, mock_session_repository):
        """Test get_or_create_session creates if not exists."""
        with patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repository,
        ):
            adapter = SessionStorageAdapter(temp_project)
            session = adapter.get_or_create_session("T1")
            assert session is not None
            assert session.task_id == "T1"

    def test_get_or_create_session_returns_existing(
        self, temp_project, mock_session_repository
    ):
        """Test get_or_create_session returns existing session."""
        # Set up mock to return existing session
        mock_session = MagicMock()
        mock_session.id = "existing-session-id"
        mock_session.task_id = "T1"
        mock_session.agent = "claude"
        mock_session.status = "active"
        mock_session.created_at = None
        mock_session.updated_at = None
        mock_session.closed_at = None
        mock_session.invocation_count = 0
        mock_session.total_cost_usd = 0.0

        mock_session_repository.get_active_session = AsyncMock(
            return_value=mock_session
        )

        with patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repository,
        ):
            adapter = SessionStorageAdapter(temp_project)
            session = adapter.get_or_create_session("T1")
            assert session is not None
            # SessionData has 'id', not 'session_id'
            assert session.id == "existing-session-id"

    def test_close_session(self, temp_project, mock_session_repository):
        """Test closing a session."""
        # Set up mock to return a session first
        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.task_id = "T1"
        mock_session_repository.get_active_session = AsyncMock(
            return_value=mock_session
        )

        with patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repository,
        ):
            adapter = SessionStorageAdapter(temp_project)

            # Close session
            result = adapter.close_session("T1")
            assert result is True
            mock_session_repository.close_task_sessions.assert_called_once_with("T1")

    def test_touch_session(self, temp_project, mock_session_repository):
        """Test touching a session updates timestamp."""
        # Set up mock to return a session first
        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.task_id = "T1"
        mock_session_repository.get_active_session = AsyncMock(
            return_value=mock_session
        )

        with patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repository,
        ):
            adapter = SessionStorageAdapter(temp_project)
            # Touch should not raise
            adapter.touch_session("T1")
            mock_session_repository.touch_session.assert_called_once_with(
                "test-session-id"
            )

    def test_record_invocation(self, temp_project, mock_session_repository):
        """Test recording an invocation."""
        # Set up mock to return a session first
        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.task_id = "T1"
        mock_session_repository.get_active_session = AsyncMock(
            return_value=mock_session
        )

        with patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repository,
        ):
            adapter = SessionStorageAdapter(temp_project)
            adapter.record_invocation("T1", cost_usd=0.05)
            mock_session_repository.record_invocation.assert_called_once_with(
                "test-session-id", 0.05
            )


class TestGetSessionStorage:
    """Tests for get_session_storage factory function."""

    def test_returns_adapter(self, temp_project):
        """Test factory returns an adapter."""
        adapter = get_session_storage(temp_project)
        assert isinstance(adapter, SessionStorageAdapter)

    def test_caches_adapter(self, temp_project):
        """Test factory returns same adapter for same project."""
        adapter1 = get_session_storage(temp_project)
        adapter2 = get_session_storage(temp_project)
        assert adapter1 is adapter2
