"""Unit tests for SessionManager."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.agents.session_manager import (
    SessionInfo,
    SessionManager,
    extract_session_from_cli_response,
)


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project = tmp_path / "test-project"
    project.mkdir()
    return project


def create_mock_session_storage():
    """Create a mock SessionStorageAdapter with in-memory tracking."""
    mock_storage = MagicMock()

    # In-memory session store
    mock_storage._sessions = {}

    def create_session(task_id, agent, session_id=None):
        session_data = MagicMock()
        session_data.id = session_id or f"{task_id}-mock-session"
        session_data.task_id = task_id
        session_data.agent = agent
        session_data.status = "active"
        session_data.created_at = datetime.now()
        session_data.updated_at = datetime.now()
        session_data.invocation_count = 1
        mock_storage._sessions[task_id] = session_data
        return session_data

    def get_active_session(task_id):
        session = mock_storage._sessions.get(task_id)
        if session and session.status == "active":
            return session
        return None

    def close_session(task_id):
        if task_id in mock_storage._sessions:
            mock_storage._sessions[task_id].status = "closed"
            return True
        return False

    def touch_session(task_id):
        if task_id in mock_storage._sessions:
            session = mock_storage._sessions[task_id]
            session.updated_at = datetime.now()
            session.invocation_count += 1
            return session
        return None

    def delete_session(task_id):
        if task_id in mock_storage._sessions:
            del mock_storage._sessions[task_id]
            return True
        return False

    def get_resume_args(task_id):
        session = mock_storage._sessions.get(task_id)
        if session and session.status == "active":
            return ["--resume", session.id]
        return []

    mock_storage.create_session = MagicMock(side_effect=create_session)
    mock_storage.get_active_session = MagicMock(side_effect=get_active_session)
    mock_storage.close_session = MagicMock(side_effect=close_session)
    mock_storage.touch_session = MagicMock(side_effect=touch_session)
    mock_storage.delete_session = MagicMock(side_effect=delete_session)
    mock_storage.get_resume_args = MagicMock(side_effect=get_resume_args)

    return mock_storage


@pytest.fixture
def session_manager(temp_project: Path) -> SessionManager:
    """Create a session manager for testing with mocked storage."""
    manager = SessionManager(temp_project, session_ttl_hours=1)
    # Replace storage with mock
    mock_storage = create_mock_session_storage()
    manager._storage = mock_storage
    return manager


class TestSessionInfo:
    """Tests for SessionInfo dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        session = SessionInfo(
            session_id="test-123",
            task_id="T1",
            project_dir="/test/project",
        )
        data = session.to_dict()

        assert data["session_id"] == "test-123"
        assert data["task_id"] == "T1"
        assert data["project_dir"] == "/test/project"
        assert data["is_active"] is True
        assert data["iteration"] == 1

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "session_id": "test-456",
            "task_id": "T2",
            "project_dir": "/test/project",
            "created_at": "2024-01-15T10:00:00",
            "last_used_at": "2024-01-15T11:00:00",
            "iteration": 3,
            "is_active": True,
            "metadata": {"key": "value"},
        }
        session = SessionInfo.from_dict(data)

        assert session.session_id == "test-456"
        assert session.task_id == "T2"
        assert session.iteration == 3
        assert session.metadata == {"key": "value"}

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = SessionInfo(
            session_id="round-trip",
            task_id="T3",
            project_dir="/test",
            iteration=5,
            metadata={"test": True},
        )
        data = original.to_dict()
        restored = SessionInfo.from_dict(data)

        assert restored.session_id == original.session_id
        assert restored.task_id == original.task_id
        assert restored.iteration == original.iteration


class TestSessionManager:
    """Tests for SessionManager."""

    def test_create_session(self, session_manager: SessionManager):
        """Test creating a new session."""
        session = session_manager.create_session("T1")

        assert session.task_id == "T1"
        assert session.is_active is True
        assert session.iteration == 1
        assert session.session_id.startswith("T1-")

    def test_create_session_with_explicit_id(self, session_manager: SessionManager):
        """Test creating session with explicit ID."""
        session = session_manager.create_session("T1", session_id="my-custom-id")

        assert session.session_id == "my-custom-id"
        assert session.task_id == "T1"

    def test_get_session(self, session_manager: SessionManager):
        """Test getting an existing session."""
        created = session_manager.create_session("T1")
        retrieved = session_manager.get_session("T1")

        assert retrieved is not None
        assert retrieved.session_id == created.session_id

    def test_get_session_nonexistent(self, session_manager: SessionManager):
        """Test getting a nonexistent session."""
        result = session_manager.get_session("nonexistent")
        assert result is None

    def test_get_or_create_session_existing(self, session_manager: SessionManager):
        """Test get_or_create with existing session."""
        created = session_manager.create_session("T1")
        retrieved = session_manager.get_or_create_session("T1")

        assert retrieved.session_id == created.session_id

    def test_get_or_create_session_new(self, session_manager: SessionManager):
        """Test get_or_create with new session."""
        session = session_manager.get_or_create_session("T2")

        assert session.task_id == "T2"
        assert session.is_active is True

    def test_touch_session(self, session_manager: SessionManager):
        """Test updating session timestamp."""
        session_manager.create_session("T1")
        original_iteration = 1

        result = session_manager.touch_session("T1")

        assert result is True
        session = session_manager.get_session("T1")
        assert session.iteration == original_iteration + 1

    def test_close_session(self, session_manager: SessionManager):
        """Test closing a session."""
        session_manager.create_session("T1")

        result = session_manager.close_session("T1")

        assert result is True
        # Closed sessions are not active
        assert session_manager.get_session("T1") is None

    def test_delete_session(self, session_manager: SessionManager):
        """Test deleting a session."""
        session_manager.create_session("T1")

        result = session_manager.delete_session("T1")

        assert result is True
        assert session_manager.get_session("T1") is None

    def test_get_resume_args_existing(self, session_manager: SessionManager):
        """Test getting resume args for existing session."""
        session_manager.create_session("T1", session_id="abc123")

        args = session_manager.get_resume_args("T1")

        assert args == ["--resume", "abc123"]

    def test_get_resume_args_nonexistent(self, session_manager: SessionManager):
        """Test getting resume args for nonexistent session."""
        args = session_manager.get_resume_args("nonexistent")
        assert args == []

    def test_get_session_id_args(self, session_manager: SessionManager):
        """Test getting session ID args."""
        args = session_manager.get_session_id_args("T1")

        assert len(args) == 2
        assert args[0] == "--session-id"
        assert args[1].startswith("T1-")

    def test_list_sessions(self, session_manager: SessionManager):
        """Test listing sessions.

        Note: list_sessions uses in-memory _sessions cache for backwards
        compatibility. The storage adapter is the primary source of truth.
        """
        # Manually populate the in-memory cache to test list functionality

        session1 = SessionInfo(session_id="s1", task_id="T1", project_dir="/tmp", is_active=True)
        session2 = SessionInfo(session_id="s2", task_id="T2", project_dir="/tmp", is_active=True)
        session3 = SessionInfo(session_id="s3", task_id="T3", project_dir="/tmp", is_active=False)
        session_manager._sessions["T1"] = session1
        session_manager._sessions["T2"] = session2
        session_manager._sessions["T3"] = session3

        active = session_manager.list_sessions(include_inactive=False)
        all_sessions = session_manager.list_sessions(include_inactive=True)

        assert len(active) == 2
        assert len(all_sessions) == 3

    @pytest.mark.db_integration
    def test_session_persistence(self, temp_project: Path):
        """Test that sessions persist across manager instances.

        This test requires a real SurrealDB connection.
        """
        pytest.skip("Integration test - requires SurrealDB")
        manager1 = SessionManager(temp_project)
        manager1.create_session("T1", session_id="persistent-session")

        # Create new manager instance
        manager2 = SessionManager(temp_project)
        session = manager2.get_session("T1")

        assert session is not None
        assert session.session_id == "persistent-session"

    def test_capture_session_id_from_output(self, session_manager: SessionManager):
        """Test capturing session ID from CLI output.

        Note: This updates the in-memory _sessions cache, not storage.
        """
        # First add to in-memory cache

        session = SessionInfo(session_id="old-id", task_id="T1", project_dir="/tmp", is_active=True)
        session_manager._sessions["T1"] = session

        # Simulate CLI output with session ID
        output = 'Some output...\n"session_id": "new-captured-id"\nMore output...'
        captured = session_manager.capture_session_id_from_output("T1", output)

        assert captured == "new-captured-id"
        # Check the in-memory session was updated
        assert session_manager._sessions["T1"].session_id == "new-captured-id"


class TestExtractSessionFromCliResponse:
    """Tests for extract_session_from_cli_response function."""

    def test_extract_from_top_level(self):
        """Test extracting from top-level session_id."""
        response = {"session_id": "abc123", "result": "success"}
        assert extract_session_from_cli_response(response) == "abc123"

    def test_extract_from_metadata(self):
        """Test extracting from metadata.session_id."""
        response = {
            "result": "success",
            "metadata": {"session_id": "meta-123"},
        }
        assert extract_session_from_cli_response(response) == "meta-123"

    def test_extract_not_found(self):
        """Test when session_id is not present."""
        response = {"result": "success"}
        assert extract_session_from_cli_response(response) is None
