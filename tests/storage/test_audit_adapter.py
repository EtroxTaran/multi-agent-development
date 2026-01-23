"""Tests for audit storage adapter."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.storage.audit_adapter import (
    AuditRecordContext,
    AuditStorageAdapter,
    get_audit_storage,
)
from orchestrator.storage.base import AuditStatisticsData


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        yield project_dir


@pytest.fixture
def mock_audit_repository():
    """Create a mock audit repository."""
    mock_repo = MagicMock()
    mock_entry = MagicMock()
    mock_entry.id = "test-entry-id"
    mock_entry.agent = "claude"
    mock_entry.task_id = "T1"
    mock_entry.session_id = None
    mock_entry.prompt_hash = "abc123"
    mock_entry.prompt_length = 100
    mock_entry.command_args = []
    mock_entry.exit_code = 0
    mock_entry.status = "success"
    mock_entry.duration_seconds = 1.5
    mock_entry.output_length = 500
    mock_entry.error_length = 0
    mock_entry.parsed_output_type = None
    mock_entry.cost_usd = 0.05
    mock_entry.model = "sonnet"
    mock_entry.metadata = {}
    mock_entry.timestamp = None

    mock_repo.create_entry = AsyncMock(return_value=mock_entry)
    mock_repo.update_result = AsyncMock(return_value=mock_entry)
    mock_repo.find_by_task = AsyncMock(return_value=[])
    mock_repo.find_by_agent = AsyncMock(return_value=[])
    mock_repo.find_by_status = AsyncMock(return_value=[])
    mock_repo.find_since = AsyncMock(return_value=[])
    mock_repo.find_all = AsyncMock(return_value=[])
    mock_repo.get_statistics = AsyncMock(
        return_value=MagicMock(
            total=0,
            success_count=0,
            failed_count=0,
            timeout_count=0,
            success_rate=0.0,
            total_cost_usd=0.0,
            total_duration_seconds=0.0,
            avg_duration_seconds=0.0,
            by_agent={},
            by_status={},
        )
    )
    return mock_repo


class TestAuditStorageAdapter:
    """Tests for AuditStorageAdapter."""

    def test_init(self, temp_project):
        """Test adapter initialization."""
        adapter = AuditStorageAdapter(temp_project)
        assert adapter.project_dir == temp_project
        assert adapter.project_name == temp_project.name
        assert adapter._db_backend is None

    def test_init_with_project_name(self, temp_project):
        """Test adapter initialization with custom project name."""
        adapter = AuditStorageAdapter(temp_project, project_name="custom-name")
        assert adapter.project_name == "custom-name"

    def test_record_context_manager_with_mock_db(self, temp_project, mock_audit_repository):
        """Test record context manager uses DB backend."""
        with patch(
            "orchestrator.db.repositories.audit.get_audit_repository",
            return_value=mock_audit_repository,
        ):
            adapter = AuditStorageAdapter(temp_project)

            with adapter.record("claude", "T1", "test prompt") as ctx:
                assert ctx is not None
                ctx.set_result(success=True, exit_code=0)

            # Verify DB methods were called
            mock_audit_repository.create_entry.assert_called_once()
            mock_audit_repository.update_result.assert_called_once()

    def test_get_task_history_empty(self, temp_project, mock_audit_repository):
        """Test get_task_history returns empty list for new task."""
        with patch(
            "orchestrator.db.repositories.audit.get_audit_repository",
            return_value=mock_audit_repository,
        ):
            adapter = AuditStorageAdapter(temp_project)
            history = adapter.get_task_history("T1")
            assert history == []

    def test_get_statistics_empty(self, temp_project, mock_audit_repository):
        """Test get_statistics returns zero stats for empty audit."""
        with patch(
            "orchestrator.db.repositories.audit.get_audit_repository",
            return_value=mock_audit_repository,
        ):
            adapter = AuditStorageAdapter(temp_project)
            stats = adapter.get_statistics()

            assert isinstance(stats, AuditStatisticsData)
            assert stats.total == 0
            assert stats.success_count == 0

    def test_query_empty(self, temp_project, mock_audit_repository):
        """Test query returns empty list for empty audit."""
        with patch(
            "orchestrator.db.repositories.audit.get_audit_repository",
            return_value=mock_audit_repository,
        ):
            adapter = AuditStorageAdapter(temp_project)
            results = adapter.query()
            assert results == []


class TestAuditRecordContext:
    """Tests for AuditRecordContext."""

    def test_context_init(self):
        """Test context initialization."""
        mock_adapter = MagicMock()
        ctx = AuditRecordContext(
            adapter=mock_adapter,
            agent="claude",
            task_id="T1",
            prompt="test prompt",
        )
        # Context stores values in private attributes
        assert ctx._agent == "claude"
        assert ctx._task_id == "T1"
        assert ctx._prompt == "test prompt"

    def test_set_result(self):
        """Test setting result updates context."""
        mock_adapter = MagicMock()
        ctx = AuditRecordContext(
            adapter=mock_adapter,
            agent="claude",
            task_id="T1",
            prompt="test prompt",
        )

        ctx.set_result(
            success=True,
            exit_code=0,
            output_length=100,
            cost_usd=0.05,
        )

        # Result values stored in private attributes
        assert ctx._success is True
        assert ctx._exit_code == 0
        assert ctx._output_length == 100
        assert ctx._cost_usd == 0.05


class TestGetAuditStorage:
    """Tests for get_audit_storage factory function."""

    def test_returns_adapter(self, temp_project):
        """Test factory returns an adapter."""
        adapter = get_audit_storage(temp_project)
        assert isinstance(adapter, AuditStorageAdapter)

    def test_caches_adapter(self, temp_project):
        """Test factory returns same adapter for same project."""
        adapter1 = get_audit_storage(temp_project)
        adapter2 = get_audit_storage(temp_project)
        assert adapter1 is adapter2

    def test_different_projects_different_adapters(self):
        """Test different projects get different adapters."""
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            adapter1 = get_audit_storage(Path(tmp1))
            adapter2 = get_audit_storage(Path(tmp2))
            assert adapter1 is not adapter2
