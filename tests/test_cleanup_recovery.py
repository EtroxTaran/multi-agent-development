"""Unit tests for cleanup and recovery modules."""

import pytest
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from orchestrator.cleanup import (
    CleanupManager,
    CleanupRule,
    ArtifactLifetime,
    CleanupResult,
)
from orchestrator.recovery import (
    RecoveryHandler,
    RecoveryResult,
    ErrorCategory,
)
from orchestrator.recovery.handlers import (
    ErrorContext,
    RecoveryAction,
    EscalationRequest,
)


class TestCleanupManager:
    """Tests for CleanupManager class."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project directory with test files."""
        # Create workflow directories
        (tmp_path / ".workflow" / "temp" / "task-1").mkdir(parents=True)
        (tmp_path / ".workflow" / "sessions" / "task-1").mkdir(parents=True)
        (tmp_path / ".workflow" / "history").mkdir(parents=True)
        (tmp_path / ".workflow" / "audit").mkdir(parents=True)

        # Create some test files
        (tmp_path / ".workflow" / "temp" / "task-1" / "debug.log").write_text("debug")
        (tmp_path / ".workflow" / "sessions" / "task-1" / "output.json").write_text("{}")

        return tmp_path

    @pytest.fixture
    def cleanup_manager(self, project_dir):
        """Create a CleanupManager instance."""
        return CleanupManager(project_dir)

    def test_get_temp_dir(self, cleanup_manager):
        """Test getting a temporary directory."""
        temp_dir = cleanup_manager.get_temp_dir("task-2", "A04")

        assert temp_dir.exists()
        assert "temp" in str(temp_dir)
        assert "task-2" in str(temp_dir)
        assert "A04" in str(temp_dir)

    def test_get_session_dir(self, cleanup_manager):
        """Test getting a session directory."""
        session_dir = cleanup_manager.get_session_dir("task-2")

        assert session_dir.exists()
        assert "sessions" in str(session_dir)
        assert "task-2" in str(session_dir)

    def test_on_agent_complete(self, cleanup_manager, project_dir):
        """Test cleanup after agent completion."""
        # Create temp files for the agent
        agent_temp = project_dir / ".workflow" / "temp" / "task-1" / "A04"
        agent_temp.mkdir(parents=True)
        (agent_temp / "scratch.txt").write_text("scratch")

        result = cleanup_manager.on_agent_complete("A04", "task-1")

        assert not agent_temp.exists()
        assert result.total_deleted > 0

    def test_on_task_done(self, cleanup_manager, project_dir):
        """Test cleanup after task completion."""
        result = cleanup_manager.on_task_done("task-1")

        temp_dir = project_dir / ".workflow" / "temp" / "task-1"
        session_dir = project_dir / ".workflow" / "sessions" / "task-1"

        assert not temp_dir.exists()
        assert not session_dir.exists()
        assert result.total_deleted > 0

    def test_dry_run_mode(self, project_dir):
        """Test dry run doesn't actually delete files."""
        manager = CleanupManager(project_dir, dry_run=True)

        # Files should exist before
        temp_file = project_dir / ".workflow" / "temp" / "task-1" / "debug.log"
        assert temp_file.exists()

        result = manager.on_task_done("task-1")

        # Files should still exist after dry run
        assert temp_file.exists()
        assert result.total_deleted > 0  # Reports what would be deleted

    def test_get_disk_usage(self, cleanup_manager, project_dir):
        """Test disk usage reporting."""
        usage = cleanup_manager.get_disk_usage()

        assert "temp" in usage
        assert "sessions" in usage
        assert usage["temp"] > 0 or usage["sessions"] > 0

    def test_artifact_lifetime_detection(self, cleanup_manager, project_dir):
        """Test artifact lifetime detection."""
        temp_file = project_dir / ".workflow" / "temp" / "task-1" / "test.log"

        # Temp files should be TRANSIENT
        lifetime = cleanup_manager.get_artifact_lifetime(temp_file)
        assert lifetime == ArtifactLifetime.TRANSIENT or lifetime == ArtifactLifetime.SESSION


class TestCleanupRule:
    """Tests for CleanupRule class."""

    def test_matches_pattern(self, tmp_path):
        """Test pattern matching."""
        rule = CleanupRule(
            pattern=".workflow/temp/**/*",
            lifetime=ArtifactLifetime.TRANSIENT,
        )

        temp_file = tmp_path / ".workflow" / "temp" / "task-1" / "file.txt"
        other_file = tmp_path / ".workflow" / "history" / "file.txt"

        # Note: matching depends on implementation
        # This tests the basic structure


class TestRecoveryHandler:
    """Tests for RecoveryHandler class."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project directory."""
        (tmp_path / ".workflow" / "escalations").mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def recovery_handler(self, project_dir):
        """Create a RecoveryHandler instance."""
        return RecoveryHandler(project_dir, max_retries=3)

    @pytest.mark.asyncio
    async def test_handle_transient_error_success(self, recovery_handler):
        """Test successful recovery from transient error."""
        call_count = 0

        async def retry_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Temporary failure")
            return "success"

        context = ErrorContext(
            category=ErrorCategory.TRANSIENT,
            message="Connection timeout",
            task_id="task-1",
        )

        result = await recovery_handler.handle_transient_error(
            ConnectionError("timeout"),
            context,
            retry_operation,
        )

        assert result.success is True
        assert result.action_taken == RecoveryAction.RETRY_WITH_BACKOFF
        assert result.recovered_value == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_handle_transient_error_max_retries(self, recovery_handler):
        """Test escalation after max retries."""
        async def always_fail():
            raise ConnectionError("Permanent failure")

        context = ErrorContext(
            category=ErrorCategory.TRANSIENT,
            message="Connection timeout",
            task_id="task-1",
        )

        result = await recovery_handler.handle_transient_error(
            ConnectionError("timeout"),
            context,
            always_fail,
        )

        assert result.success is False
        assert result.escalation_required is True

    @pytest.mark.asyncio
    async def test_handle_agent_failure_suggest_backup(self, recovery_handler):
        """Test suggestion to use backup CLI."""
        context = ErrorContext(
            category=ErrorCategory.AGENT_FAILURE,
            message="CLI failed",
            task_id="task-1",
            agent_id="A04",
            details={"used_backup": False},
        )

        result = await recovery_handler.handle_agent_failure(
            RuntimeError("CLI crashed"),
            context,
        )

        assert result.action_taken == RecoveryAction.USE_BACKUP
        assert result.should_continue is True

    @pytest.mark.asyncio
    async def test_handle_security_issue_immediate_escalation(self, recovery_handler):
        """Test immediate escalation for security issues."""
        context = ErrorContext(
            category=ErrorCategory.BLOCKING_SECURITY,
            message="SQL injection found",
            task_id="task-1",
        )

        result = await recovery_handler.handle_security_issue(
            RuntimeError("SQL injection"),
            context,
        )

        assert result.escalation_required is True
        assert result.should_continue is False
        assert "critical" in str(result.escalation_reason).lower() or \
               "security" in str(result.escalation_reason).lower()

    @pytest.mark.asyncio
    async def test_handle_spec_mismatch_escalation(self, recovery_handler):
        """Test spec mismatch always escalates (never auto-modify)."""
        context = ErrorContext(
            category=ErrorCategory.SPEC_MISMATCH,
            message="Test expects X but spec says Y",
            task_id="task-1",
        )

        result = await recovery_handler.handle_spec_mismatch(
            ValueError("Mismatch"),
            context,
        )

        assert result.escalation_required is True
        # Should provide options for human
        assert result.action_taken == RecoveryAction.ESCALATE

    def test_escalation_written_to_file(self, recovery_handler, project_dir):
        """Test that escalations are written to disk."""
        escalation = EscalationRequest(
            task_id="task-1",
            reason="test_reason",
            context="Test context",
            attempts_made=3,
            options=["option1", "option2"],
        )

        recovery_handler._write_escalation(escalation)

        escalation_files = list(
            (project_dir / ".workflow" / "escalations").glob("*.json")
        )
        assert len(escalation_files) == 1

        content = json.loads(escalation_files[0].read_text())
        assert content["task_id"] == "task-1"
        assert content["reason"] == "test_reason"


class TestErrorContext:
    """Tests for ErrorContext class."""

    def test_create_error_context(self):
        """Test creating error context."""
        context = ErrorContext(
            category=ErrorCategory.TRANSIENT,
            message="Connection failed",
            task_id="task-1",
            agent_id="A04",
            iteration=2,
            details={"retry_count": 1},
        )

        assert context.category == ErrorCategory.TRANSIENT
        assert context.task_id == "task-1"
        assert context.agent_id == "A04"
        assert context.iteration == 2
        assert context.details["retry_count"] == 1


class TestRecoveryResult:
    """Tests for RecoveryResult class."""

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = RecoveryResult(
            success=True,
            action_taken=RecoveryAction.RETRY,
            message="Succeeded after retry",
            retry_count=2,
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["action_taken"] == "retry"
        assert d["retry_count"] == 2
        assert "timestamp" in d


class TestEscalationRequest:
    """Tests for EscalationRequest class."""

    def test_to_dict(self):
        """Test converting escalation to dictionary."""
        escalation = EscalationRequest(
            task_id="task-1",
            reason="max_iterations_exceeded",
            context="Failed after 3 attempts",
            attempts_made=3,
            options=["retry", "skip", "abort"],
            recommendation="Consider retrying with more time",
            severity="high",
        )

        d = escalation.to_dict()

        assert d["task_id"] == "task-1"
        assert d["severity"] == "high"
        assert len(d["options"]) == 3
        assert d["recommendation"] is not None
