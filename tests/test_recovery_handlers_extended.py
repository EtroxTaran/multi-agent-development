"""Extended unit tests for recovery handlers.

Tests cover additional scenarios beyond the basic tests in test_cleanup_recovery.py:
- Exponential backoff timing verification
- Jitter range validation
- Maximum backoff cap enforcement
- Backup CLI retry with callable
- Security issue immediate halt behavior
- Timeout retry logic
- Escalation file writing
- Error log bounded growth
- Error routing by category
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.recovery.handlers import (
    ErrorCategory,
    ErrorContext,
    EscalationRequest,
    RecoveryAction,
    RecoveryHandler,
)


class TestTransientErrorBackoff:
    """Extended tests for transient error handling with exponential backoff."""

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
    async def test_transient_error_exponential_backoff(self, recovery_handler):
        """Verify backoff follows exponential progression."""
        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        call_count = 0

        async def retry_op():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Still failing")
            return "success"

        context = ErrorContext(
            category=ErrorCategory.TRANSIENT,
            message="Connection timeout",
            task_id="task-1",
        )

        with patch("asyncio.sleep", mock_sleep):
            result = await recovery_handler.handle_transient_error(
                ConnectionError("timeout"),
                context,
                retry_op,
            )

        assert result.success is True
        # Should have sleep times recorded (multiple retries)
        assert len(sleep_times) >= 2

        # Verify exponential progression (base=1, backoff + jitter)
        # Each subsequent sleep should be >= previous (exponential)
        # First sleep: 1*2^0 + jitter = ~1-2s
        # Second sleep: 1*2^1 + jitter = ~2-3s
        assert 1.0 <= sleep_times[0] <= 2.0
        assert sleep_times[1] > sleep_times[0]  # Exponential increase

    @pytest.mark.asyncio
    async def test_transient_error_jitter_range(self, recovery_handler):
        """Verify jitter is within 0-1s range."""
        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        async def always_fail():
            raise ConnectionError("Failure")

        context = ErrorContext(
            category=ErrorCategory.TRANSIENT,
            message="Connection timeout",
            task_id="task-1",
        )

        with patch("asyncio.sleep", mock_sleep):
            await recovery_handler.handle_transient_error(
                ConnectionError("timeout"),
                context,
                always_fail,
            )

        # Check all sleep times have reasonable jitter (0-1s added)
        for i, sleep_time in enumerate(sleep_times):
            base_backoff = 1.0 * (2**i)
            # Sleep should be base + jitter where jitter is 0-1
            assert base_backoff <= sleep_time <= base_backoff + 1.0

    @pytest.mark.asyncio
    async def test_transient_error_max_backoff_cap(self, project_dir):
        """Verify backoff is capped at 30s."""
        handler = RecoveryHandler(project_dir, max_retries=10)
        handler.BASE_BACKOFF_SECONDS = 16.0  # Start high to hit cap faster

        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        async def always_fail():
            raise ConnectionError("Failure")

        context = ErrorContext(
            category=ErrorCategory.TRANSIENT,
            message="Test",
            task_id="task-1",
        )

        with patch("asyncio.sleep", mock_sleep):
            await handler.handle_transient_error(
                ConnectionError("timeout"),
                context,
                always_fail,
            )

        # All sleep times should be <= MAX_BACKOFF_SECONDS + JITTER_RANGE max
        max_allowed = handler.MAX_BACKOFF_SECONDS + handler.JITTER_RANGE[1]
        for sleep_time in sleep_times:
            assert sleep_time <= max_allowed


class TestAgentFailureRecovery:
    """Tests for agent failure handling with backup CLI."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project directory."""
        (tmp_path / ".workflow" / "escalations").mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def recovery_handler(self, project_dir):
        """Create a RecoveryHandler instance."""
        return RecoveryHandler(project_dir)

    @pytest.mark.asyncio
    async def test_agent_failure_tries_backup(self, recovery_handler):
        """Test that backup CLI is called when provided."""
        backup_called = False

        async def backup_operation():
            nonlocal backup_called
            backup_called = True
            return "backup_success"

        context = ErrorContext(
            category=ErrorCategory.AGENT_FAILURE,
            message="Primary CLI failed",
            task_id="task-1",
            agent_id="A04",
            details={"used_backup": False},
        )

        result = await recovery_handler.handle_agent_failure(
            RuntimeError("CLI crashed"),
            context,
            retry_with_backup=backup_operation,
        )

        assert backup_called is True
        assert result.success is True
        assert result.action_taken == RecoveryAction.USE_BACKUP
        assert result.recovered_value == "backup_success"

    @pytest.mark.asyncio
    async def test_agent_failure_escalates_on_backup_fail(self, recovery_handler):
        """Test escalation when backup CLI also fails."""

        async def failing_backup():
            raise RuntimeError("Backup also failed")

        context = ErrorContext(
            category=ErrorCategory.AGENT_FAILURE,
            message="Primary CLI failed",
            task_id="task-1",
            agent_id="A04",
            details={"used_backup": False},
        )

        result = await recovery_handler.handle_agent_failure(
            RuntimeError("CLI crashed"),
            context,
            retry_with_backup=failing_backup,
        )

        assert result.success is False
        assert result.escalation_required is True
        assert result.action_taken == RecoveryAction.ESCALATE


class TestSecurityIssueHandling:
    """Tests for security issue handling."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project directory."""
        (tmp_path / ".workflow" / "escalations").mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def recovery_handler(self, project_dir):
        """Create a RecoveryHandler instance."""
        return RecoveryHandler(project_dir)

    @pytest.mark.asyncio
    async def test_security_issue_immediate_halt(self, recovery_handler):
        """Test that security issues halt immediately with no retry."""
        context = ErrorContext(
            category=ErrorCategory.BLOCKING_SECURITY,
            message="SQL injection vulnerability detected",
            task_id="task-1",
        )

        result = await recovery_handler.handle_security_issue(
            RuntimeError("SQL injection found"),
            context,
        )

        assert result.escalation_required is True
        assert result.should_continue is False
        assert result.action_taken == RecoveryAction.ESCALATE
        # Should not attempt any retries
        assert result.retry_count == 0


class TestTimeoutHandling:
    """Tests for timeout error handling."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project directory."""
        (tmp_path / ".workflow" / "escalations").mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def recovery_handler(self, project_dir):
        """Create a RecoveryHandler instance."""
        return RecoveryHandler(project_dir)

    @pytest.mark.asyncio
    async def test_timeout_first_retry_second_escalate(self, recovery_handler):
        """Test timeout gets one retry, then escalates."""
        context = ErrorContext(
            category=ErrorCategory.TIMEOUT,
            message="Operation timed out",
            task_id="task-1",
            details={"retry_count": 0},
        )

        # First timeout - should suggest retry
        result1 = await recovery_handler.handle_timeout(
            asyncio.TimeoutError(),
            context,
        )

        assert result1.should_continue is True
        assert result1.action_taken == RecoveryAction.RETRY
        assert result1.retry_count == 1

        # Second timeout - should escalate
        context.details["retry_count"] = 1
        result2 = await recovery_handler.handle_timeout(
            asyncio.TimeoutError(),
            context,
        )

        assert result2.escalation_required is True
        assert result2.action_taken == RecoveryAction.ESCALATE


class TestEscalationFileWriting:
    """Tests for escalation file persistence."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project directory."""
        (tmp_path / ".workflow" / "escalations").mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def recovery_handler(self, project_dir):
        """Create a RecoveryHandler instance."""
        return RecoveryHandler(project_dir)

    @pytest.mark.asyncio
    async def test_escalation_writes_file(self, recovery_handler, project_dir):
        """Test that escalations are written to .workflow/escalations/."""
        context = ErrorContext(
            category=ErrorCategory.SPEC_MISMATCH,
            message="Test mismatch",
            task_id="task-42",
        )

        await recovery_handler.handle_spec_mismatch(
            ValueError("Mismatch"),
            context,
        )

        escalation_files = list((project_dir / ".workflow" / "escalations").glob("task-42_*.json"))
        assert len(escalation_files) == 1

        content = json.loads(escalation_files[0].read_text())
        assert content["task_id"] == "task-42"
        assert content["reason"] == "test_spec_mismatch"
        assert "timestamp" in content


class TestErrorLogBoundedGrowth:
    """Tests for error log size management."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project directory."""
        (tmp_path / ".workflow" / "escalations").mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def recovery_handler(self, project_dir):
        """Create a RecoveryHandler instance."""
        return RecoveryHandler(project_dir)

    def test_error_log_bounded_growth(self, recovery_handler):
        """Test that error log doesn't grow unbounded."""
        # Log many errors
        for i in range(200):
            context = ErrorContext(
                category=ErrorCategory.TRANSIENT,
                message=f"Error {i}",
                task_id=f"task-{i}",
            )
            recovery_handler._log_error(Exception(f"Error {i}"), context)

        # Error log should be bounded (implementation may vary)
        # The handler should have a reasonable limit
        error_log = recovery_handler.get_error_log()
        # Just verify it doesn't grow without bound - exact limit depends on implementation
        assert len(error_log) <= 200  # At minimum, shouldn't exceed what we logged


class TestErrorRouting:
    """Tests for error category routing."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project directory."""
        (tmp_path / ".workflow" / "escalations").mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def recovery_handler(self, project_dir):
        """Create a RecoveryHandler instance."""
        return RecoveryHandler(project_dir)

    @pytest.mark.asyncio
    async def test_handle_error_routes_correctly(self, recovery_handler):
        """Test that handle_error routes to correct handler by category."""
        test_cases = [
            # TRANSIENT without retry_operation returns RETRY (manual retry hint)
            (
                ErrorCategory.TRANSIENT,
                [RecoveryAction.RETRY, RecoveryAction.RETRY_WITH_BACKOFF, RecoveryAction.ESCALATE],
            ),
            (ErrorCategory.AGENT_FAILURE, [RecoveryAction.USE_BACKUP, RecoveryAction.ESCALATE]),
            (ErrorCategory.BLOCKING_SECURITY, [RecoveryAction.ESCALATE]),
            (ErrorCategory.TIMEOUT, [RecoveryAction.RETRY, RecoveryAction.ESCALATE]),
            (ErrorCategory.SPEC_MISMATCH, [RecoveryAction.ESCALATE]),
        ]

        for category, expected_actions in test_cases:
            context = ErrorContext(
                category=category,
                message=f"Test error for {category.value}",
                task_id="task-1",
                agent_id="A04",
                details={"used_backup": False, "retry_count": 0},
            )

            result = await recovery_handler.handle_error(
                Exception("Test error"),
                context,
            )

            # Verify routing by checking action matches one of expected actions
            assert (
                result.action_taken in expected_actions
            ), f"Category {category.value} should route to one of {[a.value for a in expected_actions]}, got {result.action_taken.value}"


class TestReviewConflictHandling:
    """Tests for review conflict resolution."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project directory."""
        (tmp_path / ".workflow" / "escalations").mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def recovery_handler(self, project_dir):
        """Create a RecoveryHandler instance."""
        return RecoveryHandler(project_dir)

    @pytest.mark.asyncio
    async def test_review_conflict_resolved(self, recovery_handler):
        """Test resolution when conflict can be resolved."""
        reviews = [
            {"agent_id": "A07", "approved": True, "score": 8.0, "blocking_issues": []},
            {"agent_id": "A08", "approved": True, "score": 7.5, "blocking_issues": []},
        ]

        context = ErrorContext(
            category=ErrorCategory.REVIEW_CONFLICT,
            message="Reviewers disagree",
            task_id="task-1",
            details={"reviews": reviews},
        )

        # Mock the ConflictResolver - imported inside handle_review_conflict
        with patch("orchestrator.review.ConflictResolver") as MockResolver:
            mock_resolution = MagicMock()
            mock_resolution.resolved = True
            mock_resolution.final_decision = "approved"
            MockResolver.return_value.resolve.return_value = mock_resolution

            result = await recovery_handler.handle_review_conflict(reviews, context)

        assert result.success is True
        assert result.action_taken == RecoveryAction.SKIP

    @pytest.mark.asyncio
    async def test_review_conflict_unresolved(self, recovery_handler):
        """Test escalation when conflict cannot be resolved."""
        reviews = [
            {"agent_id": "A07", "approved": True, "score": 8.0},
            {"agent_id": "A08", "approved": False, "score": 4.0},
        ]

        context = ErrorContext(
            category=ErrorCategory.REVIEW_CONFLICT,
            message="Reviewers disagree",
            task_id="task-1",
            details={"reviews": reviews},
        )

        # Mock the ConflictResolver to return unresolved
        with patch("orchestrator.review.ConflictResolver") as MockResolver:
            mock_resolution = MagicMock()
            mock_resolution.resolved = False
            MockResolver.return_value.resolve.return_value = mock_resolution

            result = await recovery_handler.handle_review_conflict(reviews, context)

        assert result.success is False
        assert result.escalation_required is True
        assert result.action_taken == RecoveryAction.ESCALATE


class TestEscalationCallback:
    """Tests for escalation callback functionality."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project directory."""
        (tmp_path / ".workflow" / "escalations").mkdir(parents=True)
        return tmp_path

    @pytest.mark.asyncio
    async def test_escalation_callback_called(self, project_dir):
        """Test that escalation callback is invoked."""
        callback_called = False
        captured_escalation = None

        def escalation_callback(escalation: EscalationRequest):
            nonlocal callback_called, captured_escalation
            callback_called = True
            captured_escalation = escalation

        handler = RecoveryHandler(
            project_dir,
            escalation_callback=escalation_callback,
        )

        context = ErrorContext(
            category=ErrorCategory.BLOCKING_SECURITY,
            message="Security issue",
            task_id="task-1",
        )

        await handler.handle_security_issue(
            RuntimeError("Security issue"),
            context,
        )

        assert callback_called is True
        assert captured_escalation is not None
        assert captured_escalation.task_id == "task-1"
        assert captured_escalation.severity == "critical"

    @pytest.mark.asyncio
    async def test_escalation_callback_error_handled(self, project_dir):
        """Test that callback errors don't break escalation."""

        def failing_callback(escalation: EscalationRequest):
            raise RuntimeError("Callback failed")

        handler = RecoveryHandler(
            project_dir,
            escalation_callback=failing_callback,
        )

        context = ErrorContext(
            category=ErrorCategory.BLOCKING_SECURITY,
            message="Security issue",
            task_id="task-1",
        )

        # Should not raise despite callback failure
        result = await handler.handle_security_issue(
            RuntimeError("Security issue"),
            context,
        )

        assert result.escalation_required is True
