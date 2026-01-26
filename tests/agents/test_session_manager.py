"""Tests for session manager.

Tests session creation, retrieval, persistence, and CLI integration.
"""

from datetime import datetime, timedelta

from orchestrator.agents.session_manager import (
    DEFAULT_SESSIONS_DIR,
    SESSION_TTL_HOURS,
    SessionInfo,
    SessionManager,
    extract_session_from_cli_response,
)


class TestSessionInfo:
    """Tests for SessionInfo dataclass."""

    def test_session_info_defaults(self):
        """Test default values."""
        session = SessionInfo(
            session_id="test-123",
            task_id="T1",
            project_dir="/tmp/test",
        )
        assert session.session_id == "test-123"
        assert session.task_id == "T1"
        assert session.project_dir == "/tmp/test"
        assert session.iteration == 1
        assert session.is_active is True
        assert session.metadata == {}
        assert session.created_at is not None
        assert session.last_used_at is not None

    def test_session_info_to_dict(self, sample_session_info):
        """Test serialization to dictionary."""
        d = sample_session_info.to_dict()
        assert d["session_id"] == "T1-abc123def456"
        assert d["task_id"] == "T1"
        assert d["project_dir"] == "/tmp/test-project"
        assert d["iteration"] == 1
        assert d["is_active"] is True
        assert d["metadata"] == {"test": "value"}
        assert "created_at" in d
        assert "last_used_at" in d

    def test_session_info_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "session_id": "test-456",
            "task_id": "T2",
            "project_dir": "/tmp/project",
            "created_at": "2026-01-26T12:00:00",
            "last_used_at": "2026-01-26T13:00:00",
            "iteration": 3,
            "is_active": True,
            "metadata": {"key": "value"},
        }
        session = SessionInfo.from_dict(data)
        assert session.session_id == "test-456"
        assert session.task_id == "T2"
        assert session.iteration == 3
        assert session.metadata == {"key": "value"}

    def test_session_info_roundtrip(self, sample_session_info):
        """Test serialization roundtrip."""
        d = sample_session_info.to_dict()
        restored = SessionInfo.from_dict(d)
        assert restored.session_id == sample_session_info.session_id
        assert restored.task_id == sample_session_info.task_id
        assert restored.iteration == sample_session_info.iteration


class TestSessionManager:
    """Tests for SessionManager class."""

    def test_initialization(self, temp_project_dir):
        """Test manager initialization."""
        manager = SessionManager(temp_project_dir)
        assert manager.project_dir == temp_project_dir
        assert manager.sessions_dir == temp_project_dir / DEFAULT_SESSIONS_DIR
        assert manager.session_ttl_hours == SESSION_TTL_HOURS

    def test_initialization_custom_dir(self, temp_project_dir):
        """Test manager with custom sessions directory."""
        manager = SessionManager(temp_project_dir, sessions_dir="custom/sessions")
        assert manager.sessions_dir == temp_project_dir / "custom/sessions"

    def test_initialization_custom_ttl(self, temp_project_dir):
        """Test manager with custom TTL."""
        manager = SessionManager(temp_project_dir, session_ttl_hours=12)
        assert manager.session_ttl_hours == 12

    def test_create_session(self, session_manager):
        """Test creating a new session."""
        session = session_manager.create_session("T1")
        assert session.task_id == "T1"
        assert session.session_id is not None
        assert session.is_active is True
        assert session.iteration == 1

    def test_create_session_with_custom_id(self, session_manager):
        """Test creating session with explicit ID."""
        session = session_manager.create_session("T1", session_id="custom-session-id")
        assert session.session_id == "custom-session-id"

    def test_create_session_with_metadata(self, session_manager):
        """Test creating session with metadata."""
        session = session_manager.create_session("T1", metadata={"phase": "implementation"})
        assert session.metadata == {"phase": "implementation"}

    def test_create_session_closes_existing(self, session_manager):
        """Test creating new session closes existing one."""
        session1 = session_manager.create_session("T1")
        session2 = session_manager.create_session("T1")

        assert session1.session_id != session2.session_id

        # The old session should be marked inactive
        # The new session should be the only active one
        retrieved = session_manager.get_session("T1")
        assert retrieved.session_id == session2.session_id

    def test_get_session_existing(self, session_manager):
        """Test getting an existing session."""
        created = session_manager.create_session("T1")
        retrieved = session_manager.get_session("T1")

        assert retrieved is not None
        assert retrieved.session_id == created.session_id

    def test_get_session_nonexistent(self, session_manager):
        """Test getting a nonexistent session."""
        session = session_manager.get_session("T-NONEXISTENT")
        assert session is None

    def test_get_session_inactive(self, session_manager):
        """Test getting an inactive session returns None."""
        _session = session_manager.create_session("T1")
        session_manager.close_session("T1")

        retrieved = session_manager.get_session("T1")
        assert retrieved is None

    def test_get_session_expired(self, session_manager):
        """Test getting an expired session returns None."""
        session = session_manager.create_session("T1")

        # Manually expire the session
        session.last_used_at = datetime.now() - timedelta(hours=48)
        session_manager._sessions["T1"] = session

        retrieved = session_manager.get_session("T1")
        assert retrieved is None

    def test_get_or_create_session_creates_new(self, session_manager):
        """Test get_or_create creates new session if none exists."""
        session = session_manager.get_or_create_session("T1")
        assert session is not None
        assert session.task_id == "T1"

    def test_get_or_create_session_returns_existing(self, session_manager):
        """Test get_or_create returns existing session."""
        created = session_manager.create_session("T1")
        retrieved = session_manager.get_or_create_session("T1")
        assert retrieved.session_id == created.session_id

    def test_touch_session(self, session_manager):
        """Test updating session's last used time."""
        session = session_manager.create_session("T1")
        original_time = session.last_used_at
        original_iteration = session.iteration

        result = session_manager.touch_session("T1")

        assert result is True
        updated = session_manager.get_session("T1")
        assert updated.last_used_at >= original_time
        assert updated.iteration == original_iteration + 1

    def test_touch_session_nonexistent(self, session_manager):
        """Test touching a nonexistent session returns False."""
        result = session_manager.touch_session("T-NONEXISTENT")
        assert result is False

    def test_close_session(self, session_manager):
        """Test closing a session."""
        session_manager.create_session("T1")
        result = session_manager.close_session("T1")

        assert result is True
        assert session_manager.get_session("T1") is None

    def test_close_session_nonexistent(self, session_manager):
        """Test closing a nonexistent session returns False."""
        result = session_manager.close_session("T-NONEXISTENT")
        assert result is False

    def test_delete_session(self, session_manager):
        """Test deleting a session completely."""
        session_manager.create_session("T1")
        result = session_manager.delete_session("T1")

        assert result is True
        # Session file should be removed
        session_file = session_manager.sessions_dir / "T1.json"
        assert not session_file.exists()

    def test_delete_session_nonexistent(self, session_manager):
        """Test deleting a nonexistent session returns False."""
        result = session_manager.delete_session("T-NONEXISTENT")
        assert result is False

    def test_get_resume_args_with_session(self, session_manager):
        """Test getting resume args when session exists."""
        session = session_manager.create_session("T1")
        args = session_manager.get_resume_args("T1")

        assert args == ["--resume", session.session_id]

    def test_get_resume_args_without_session(self, session_manager):
        """Test getting resume args when no session exists."""
        args = session_manager.get_resume_args("T-NONEXISTENT")
        assert args == []

    def test_get_session_id_args(self, session_manager):
        """Test getting session ID args for new session."""
        args = session_manager.get_session_id_args("T1")

        assert "--session-id" in args
        assert len(args) == 2

    def test_capture_session_id_from_output(self, session_manager):
        """Test extracting session ID from CLI output."""
        session_manager.create_session("T1")

        output = "Session: abc123-def456\nOther output"
        captured = session_manager.capture_session_id_from_output("T1", output)

        assert captured == "abc123-def456"

    def test_capture_session_id_json_format(self, session_manager):
        """Test extracting session ID from JSON output."""
        session_manager.create_session("T1")

        output = '{"session_id": "json-session-id", "result": "success"}'
        captured = session_manager.capture_session_id_from_output("T1", output)

        assert captured == "json-session-id"

    def test_capture_session_id_no_match(self, session_manager):
        """Test extraction when no session ID in output."""
        session_manager.create_session("T1")

        output = "No session ID here"
        captured = session_manager.capture_session_id_from_output("T1", output)

        assert captured is None

    def test_cleanup_expired_sessions(self, session_manager):
        """Test cleanup of expired sessions."""
        # Create two sessions
        session_manager.create_session("T1")
        session_manager.create_session("T2")

        # Expire T2
        session_manager._sessions["T2"].last_used_at = datetime.now() - timedelta(hours=48)

        count = session_manager.cleanup_expired_sessions()

        assert count == 1
        assert session_manager.get_session("T1") is not None
        # T2 should be deleted
        assert "T2" not in session_manager._sessions

    def test_list_sessions(self, session_manager):
        """Test listing all sessions."""
        session_manager.create_session("T1")
        session_manager.create_session("T2")

        sessions = session_manager.list_sessions()

        assert len(sessions) == 2
        task_ids = [s.task_id for s in sessions]
        assert "T1" in task_ids
        assert "T2" in task_ids

    def test_list_sessions_excludes_inactive(self, session_manager):
        """Test listing excludes inactive sessions by default."""
        session_manager.create_session("T1")
        session_manager.create_session("T2")
        session_manager.close_session("T2")

        sessions = session_manager.list_sessions()

        assert len(sessions) == 1
        assert sessions[0].task_id == "T1"

    def test_list_sessions_include_inactive(self, session_manager):
        """Test listing can include inactive sessions."""
        session_manager.create_session("T1")
        session_manager.create_session("T2")
        session_manager.close_session("T2")

        sessions = session_manager.list_sessions(include_inactive=True)

        assert len(sessions) == 2

    def test_persistence_save_and_load(self, temp_project_dir):
        """Test that sessions persist across manager instances."""
        manager1 = SessionManager(temp_project_dir)
        session = manager1.create_session("T1", metadata={"test": "data"})

        # Create new manager instance
        manager2 = SessionManager(temp_project_dir)
        loaded = manager2.get_session("T1")

        assert loaded is not None
        assert loaded.session_id == session.session_id
        assert loaded.metadata == {"test": "data"}

    def test_generate_session_id_format(self, session_manager):
        """Test that generated session IDs have correct format."""
        session_id = session_manager._generate_session_id("T1")

        assert session_id.startswith("T1-")
        assert len(session_id) > len("T1-")

    def test_generate_session_id_unique(self, session_manager):
        """Test that generated session IDs are unique."""
        ids = [session_manager._generate_session_id("T1") for _ in range(10)]
        assert len(set(ids)) == 10


class TestExtractSessionFromCliResponse:
    """Tests for extract_session_from_cli_response helper."""

    def test_extract_from_root_level(self):
        """Test extraction from root level."""
        response = {"session_id": "root-session-id", "result": "success"}
        session_id = extract_session_from_cli_response(response)
        assert session_id == "root-session-id"

    def test_extract_from_metadata(self):
        """Test extraction from metadata field."""
        response = {
            "result": "success",
            "metadata": {"session_id": "metadata-session-id"},
        }
        session_id = extract_session_from_cli_response(response)
        assert session_id == "metadata-session-id"

    def test_extract_not_found(self):
        """Test extraction when not present."""
        response = {"result": "success", "data": "value"}
        session_id = extract_session_from_cli_response(response)
        assert session_id is None

    def test_extract_prefers_root_level(self):
        """Test that root level is preferred over metadata."""
        response = {
            "session_id": "root-id",
            "metadata": {"session_id": "metadata-id"},
        }
        session_id = extract_session_from_cli_response(response)
        assert session_id == "root-id"
