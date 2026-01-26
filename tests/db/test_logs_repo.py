"""Tests for logs repository.

Tests the LogsRepository class and LogEntry dataclass
from orchestrator.db.repositories.logs module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.db.repositories.logs import LogEntry, LogsRepository, LogType, get_logs_repository


class TestLogEntry:
    """Tests for the LogEntry dataclass."""

    def test_log_entry_defaults(self):
        """Test LogEntry default values."""
        entry = LogEntry(log_type="debug")
        assert entry.log_type == "debug"
        assert entry.content == {}
        assert entry.task_id is None
        assert entry.metadata == {}
        assert entry.id is None

    def test_log_entry_with_content(self):
        """Test LogEntry with content."""
        content = {"message": "Test log"}
        entry = LogEntry(
            log_type=LogType.DEBUG,
            content=content,
            task_id="T1",
        )
        assert entry.content == content
        assert entry.task_id == "T1"

    def test_log_entry_to_dict(self):
        """Test converting LogEntry to dictionary."""
        entry = LogEntry(
            log_type=LogType.ERROR,
            content={"message": "Error occurred"},
            task_id="T1",
            metadata={"source": "test"},
        )
        data = entry.to_dict()

        assert data["log_type"] == "error"
        assert data["content"] == {"message": "Error occurred"}
        assert data["task_id"] == "T1"
        assert data["metadata"] == {"source": "test"}
        assert "id" not in data  # id should be excluded


class TestLogType:
    """Tests for LogType constants."""

    def test_log_type_uat(self):
        """Test UAT document log type."""
        assert LogType.UAT_DOCUMENT == "uat_document"

    def test_log_type_handoff(self):
        """Test handoff brief log type."""
        assert LogType.HANDOFF_BRIEF == "handoff_brief"

    def test_log_type_discussion(self):
        """Test discussion log type."""
        assert LogType.DISCUSSION == "discussion"

    def test_log_type_research(self):
        """Test research log type."""
        assert LogType.RESEARCH == "research"

    def test_log_type_error(self):
        """Test error log type."""
        assert LogType.ERROR == "error"

    def test_log_type_debug(self):
        """Test debug log type."""
        assert LogType.DEBUG == "debug"


class TestLogsRepository:
    """Tests for the LogsRepository class."""

    @pytest.fixture
    def repo(self):
        """Create a LogsRepository for testing."""
        return LogsRepository("test-project")

    @pytest.fixture
    def mock_conn(self):
        """Create a mock database connection."""
        conn = MagicMock()
        conn.query = AsyncMock(return_value=[])
        conn.create = AsyncMock(return_value={"id": "logs:123"})
        return conn

    def test_repository_init(self, repo):
        """Test repository initialization."""
        assert repo.project_name == "test-project"
        assert repo.table_name == "logs"

    def test_to_record_with_dict(self, repo):
        """Test _to_record with a dictionary."""
        data = {
            "id": "logs:123",
            "log_type": "error",
            "content": {"message": "Test error"},
            "task_id": "T1",
            "metadata": {"source": "test"},
        }
        result = repo._to_record(data)

        assert isinstance(result, LogEntry)
        assert result.log_type == "error"
        assert result.content == {"message": "Test error"}
        assert result.task_id == "T1"

    def test_to_record_with_string(self, repo):
        """Test _to_record with a string ID."""
        result = repo._to_record("logs:123")

        assert isinstance(result, LogEntry)
        assert result.id == "logs:123"
        assert result.log_type == ""

    @pytest.mark.asyncio
    async def test_create_log(self, repo, mock_conn):
        """Test creating a new log entry."""
        mock_conn.create = AsyncMock(
            return_value={
                "id": "logs:new",
                "log_type": "debug",
                "content": {"message": "Test"},
            }
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.create_log("debug", {"message": "Test"})

            assert result is not None
            mock_conn.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_log_with_task_id(self, repo, mock_conn):
        """Test creating a log entry with task ID."""
        mock_conn.create = AsyncMock(
            return_value={
                "id": "logs:new",
                "log_type": "error",
                "content": {"message": "Error"},
                "task_id": "T1",
            }
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.create_log("error", {"message": "Error"}, task_id="T1")

            assert result is not None

    @pytest.mark.asyncio
    async def test_create_log_with_metadata(self, repo, mock_conn):
        """Test creating a log entry with metadata."""
        mock_conn.create = AsyncMock(
            return_value={
                "id": "logs:new",
                "log_type": "debug",
                "content": {},
                "metadata": {"source": "test"},
            }
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.create_log("debug", {}, metadata={"source": "test"})

            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_type(self, repo, mock_conn):
        """Test getting logs by type."""
        mock_conn.query = AsyncMock(
            return_value=[
                {"id": "1", "log_type": "error", "content": {"message": "Error 1"}},
                {"id": "2", "log_type": "error", "content": {"message": "Error 2"}},
            ]
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            results = await repo.get_by_type("error")

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_by_type_with_pagination(self, repo, mock_conn):
        """Test getting logs by type with pagination."""
        mock_conn.query = AsyncMock(return_value=[])

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            await repo.get_by_type("error", limit=50, offset=10)

            # Verify pagination params were passed (as positional dict arg)
            call_args = mock_conn.query.call_args
            # query(sql, params_dict) - params is the second positional arg
            params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
            assert params["limit"] == 50
            assert params["offset"] == 10

    @pytest.mark.asyncio
    async def test_get_by_task(self, repo, mock_conn):
        """Test getting logs by task."""
        mock_conn.query = AsyncMock(
            return_value=[
                {"id": "1", "log_type": "debug", "content": {}, "task_id": "T1"},
            ]
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            results = await repo.get_by_task("T1")

            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_by_task_with_type_filter(self, repo, mock_conn):
        """Test getting logs by task with type filter."""
        mock_conn.query = AsyncMock(return_value=[])

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            await repo.get_by_task("T1", log_type="error")

            # Verify log_type was included in query params
            call_args = mock_conn.query.call_args
            # query(sql, params_dict) - params is the second positional arg
            params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
            assert "log_type" in params

    @pytest.mark.asyncio
    async def test_get_latest(self, repo, mock_conn):
        """Test getting latest log of a type."""
        mock_conn.query = AsyncMock(
            return_value=[{"id": "1", "log_type": "debug", "content": {"latest": True}}]
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_latest("debug")

            assert result is not None
            assert result.content == {"latest": True}

    @pytest.mark.asyncio
    async def test_get_latest_not_found(self, repo, mock_conn):
        """Test get_latest when no log exists."""
        mock_conn.query = AsyncMock(return_value=[])

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_latest("debug")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_with_task_id(self, repo, mock_conn):
        """Test getting latest log with task filter."""
        mock_conn.query = AsyncMock(
            return_value=[{"id": "1", "log_type": "error", "content": {}, "task_id": "T1"}]
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_latest("error", task_id="T1")

            assert result is not None

    @pytest.mark.asyncio
    async def test_save_uat_document(self, repo, mock_conn):
        """Test save_uat_document convenience method."""
        mock_conn.create = AsyncMock(
            return_value={
                "id": "new",
                "log_type": "uat_document",
                "content": {"tests": []},
                "task_id": "T1",
            }
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_uat_document("T1", {"tests": []})

            assert result is not None

    @pytest.mark.asyncio
    async def test_get_uat_document(self, repo, mock_conn):
        """Test get_uat_document convenience method."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "id": "1",
                    "log_type": "uat_document",
                    "content": {"tests": ["test1"]},
                    "task_id": "T1",
                }
            ]
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_uat_document("T1")

            assert result == {"tests": ["test1"]}

    @pytest.mark.asyncio
    async def test_get_uat_document_not_found(self, repo, mock_conn):
        """Test get_uat_document when none exists."""
        mock_conn.query = AsyncMock(return_value=[])

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_uat_document("T1")

            assert result is None

    @pytest.mark.asyncio
    async def test_save_handoff_brief(self, repo, mock_conn):
        """Test save_handoff_brief convenience method."""
        mock_conn.create = AsyncMock(
            return_value={
                "id": "new",
                "log_type": "handoff_brief",
                "content": {"summary": "Test"},
            }
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_handoff_brief({"summary": "Test"})

            assert result is not None

    @pytest.mark.asyncio
    async def test_get_latest_handoff_brief(self, repo, mock_conn):
        """Test get_latest_handoff_brief convenience method."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "id": "1",
                    "log_type": "handoff_brief",
                    "content": {"summary": "Latest"},
                }
            ]
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_latest_handoff_brief()

            assert result == {"summary": "Latest"}

    @pytest.mark.asyncio
    async def test_save_discussion(self, repo, mock_conn):
        """Test save_discussion convenience method."""
        mock_conn.create = AsyncMock(
            return_value={
                "id": "new",
                "log_type": "discussion",
                "content": {"notes": "Test"},
            }
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_discussion({"notes": "Test"})

            assert result is not None

    @pytest.mark.asyncio
    async def test_save_research(self, repo, mock_conn):
        """Test save_research convenience method."""
        mock_conn.create = AsyncMock(
            return_value={
                "id": "new",
                "log_type": "research",
                "content": {"findings": []},
            }
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_research({"findings": []})

            assert result is not None

    @pytest.mark.asyncio
    async def test_log_error(self, repo, mock_conn):
        """Test log_error convenience method."""
        mock_conn.create = AsyncMock(
            return_value={
                "id": "new",
                "log_type": "error",
                "content": {"message": "Test error", "context": {}},
            }
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.log_error("Test error", task_id="T1")

            assert result is not None

    @pytest.mark.asyncio
    async def test_log_error_with_context(self, repo, mock_conn):
        """Test log_error with context."""
        mock_conn.create = AsyncMock(
            return_value={
                "id": "new",
                "log_type": "error",
                "content": {"message": "Error", "context": {"phase": 2}},
            }
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.log_error("Error", context={"phase": 2})

            assert result is not None

    @pytest.mark.asyncio
    async def test_log_debug(self, repo, mock_conn):
        """Test log_debug convenience method."""
        mock_conn.create = AsyncMock(
            return_value={
                "id": "new",
                "log_type": "debug",
                "content": {"message": "Debug info", "data": {}},
            }
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.log_debug("Debug info", data={"key": "value"})

            assert result is not None

    @pytest.mark.asyncio
    async def test_clear_by_type(self, repo, mock_conn):
        """Test clearing logs by type."""
        mock_conn.query = AsyncMock(return_value=[{"id": "1"}, {"id": "2"}])  # 2 deleted

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            deleted = await repo.clear_by_type("debug")

            assert deleted == 2

    @pytest.mark.asyncio
    async def test_clear_by_task(self, repo, mock_conn):
        """Test clearing logs by task."""
        mock_conn.query = AsyncMock(
            return_value=[{"id": "1"}, {"id": "2"}, {"id": "3"}]  # 3 deleted
        )

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            deleted = await repo.clear_by_task("T1")

            assert deleted == 3

    @pytest.mark.asyncio
    async def test_prune_old_logs(self, repo, mock_conn):
        """Test pruning old logs."""
        mock_conn.query = AsyncMock(return_value=[{"id": "1"}, {"id": "2"}])  # 2 deleted

        with patch("orchestrator.db.repositories.logs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            deleted = await repo.prune_old_logs(days=30)

            assert deleted == 2


class TestGetLogsRepository:
    """Tests for get_logs_repository function."""

    def test_creates_new_repository(self):
        """Test creating a new repository."""
        with patch("orchestrator.db.repositories.logs._repos", {}):
            repo = get_logs_repository("test-project")
            assert repo is not None
            assert repo.project_name == "test-project"

    def test_reuses_existing_repository(self):
        """Test reusing an existing repository."""
        with patch("orchestrator.db.repositories.logs._repos", {}):
            repo1 = get_logs_repository("test-project")
            repo2 = get_logs_repository("test-project")
            assert repo1 is repo2

    def test_different_projects_different_repos(self):
        """Test different projects get different repositories."""
        with patch("orchestrator.db.repositories.logs._repos", {}):
            repo1 = get_logs_repository("project-a")
            repo2 = get_logs_repository("project-b")
            assert repo1 is not repo2
