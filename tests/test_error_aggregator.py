"""Tests for ErrorAggregator component."""

import json
import tempfile
from pathlib import Path

import pytest

from orchestrator.utils.error_aggregator import (
    AggregatedError,
    ErrorAggregator,
    ErrorSeverity,
    ErrorSource,
    get_error_aggregator,
    reset_error_aggregator,
)


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary workflow directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_dir = Path(tmpdir) / ".workflow"
        workflow_dir.mkdir()
        yield workflow_dir


@pytest.fixture
def error_aggregator(temp_workflow_dir):
    """Create an error aggregator instance."""
    return ErrorAggregator(temp_workflow_dir)


class TestAggregatedError:
    """Tests for AggregatedError dataclass."""

    def test_to_dict(self):
        error = AggregatedError(
            id="test-id",
            timestamp="2024-01-15T10:00:00",
            source=ErrorSource.ACTION_LOG,
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
            message="Test error message",
            phase=2,
            agent="cursor",
        )
        result = error.to_dict()

        assert result["id"] == "test-id"
        assert result["source"] == "action_log"
        assert result["severity"] == "error"
        assert result["phase"] == 2

    def test_from_dict(self):
        data = {
            "id": "test-id",
            "timestamp": "2024-01-15T10:00:00",
            "source": "action_log",
            "error_type": "TestError",
            "severity": "error",
            "message": "Test error message",
        }
        error = AggregatedError.from_dict(data)

        assert error.id == "test-id"
        assert error.source == ErrorSource.ACTION_LOG
        assert error.severity == ErrorSeverity.ERROR

    def test_is_resolved(self):
        error = AggregatedError(
            id="test-id",
            timestamp="2024-01-15T10:00:00",
            source=ErrorSource.EXCEPTION,
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
            message="Test",
        )
        assert not error.is_resolved

        error.resolution = "Fixed by restarting"
        assert error.is_resolved

    def test_fingerprint(self):
        error1 = AggregatedError(
            id="1",
            timestamp="2024-01-15T10:00:00",
            source=ErrorSource.ACTION_LOG,
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
            message="Same message",
            phase=2,
        )
        error2 = AggregatedError(
            id="2",
            timestamp="2024-01-15T11:00:00",
            source=ErrorSource.STATE,  # Different source
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
            message="Same message",
            phase=2,
        )
        # Same fingerprint because key fields match
        assert error1.fingerprint() == error2.fingerprint()


class TestErrorAggregator:
    """Tests for ErrorAggregator class."""

    def test_add_error(self, error_aggregator, temp_workflow_dir):
        """Test adding a new error."""
        error = error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="TestError",
            message="Test error message",
            phase=2,
            agent="cursor",
        )

        assert error.source == ErrorSource.EXCEPTION
        assert error.message == "Test error message"
        assert error.phase == 2

        # Check persistence
        unresolved_file = temp_workflow_dir / "errors" / "unresolved.json"
        assert unresolved_file.exists()

    def test_add_duplicate_error(self, error_aggregator):
        """Test that duplicate errors are deduplicated."""
        error1 = error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="TestError",
            message="Same error",
            phase=2,
        )
        error2 = error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="TestError",
            message="Same error",
            phase=2,
        )

        # Should return the same error with increased count
        assert error1.id == error2.id
        assert error2.occurrence_count == 2

        # Only one unresolved error
        unresolved = error_aggregator.get_unresolved()
        assert len(unresolved) == 1

    def test_auto_severity_detection(self, error_aggregator):
        """Test automatic severity detection."""
        # Critical for security issues
        error1 = error_aggregator.add_error(
            source=ErrorSource.VALIDATION,
            error_type="security_vulnerability",
            message="XSS detected",
        )
        assert error1.severity == ErrorSeverity.CRITICAL

        # Error for test failures
        error2 = error_aggregator.add_error(
            source=ErrorSource.AGENT_OUTPUT,
            error_type="test_failure",
            message="Tests failed",
        )
        assert error2.severity == ErrorSeverity.ERROR

        # Warning for rate limits
        error3 = error_aggregator.add_error(
            source=ErrorSource.AGENT_OUTPUT,
            error_type="rate_limit",
            message="Rate limited",
        )
        assert error3.severity == ErrorSeverity.WARNING

    def test_resolve_error(self, error_aggregator):
        """Test resolving an error."""
        error = error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="TestError",
            message="Test error",
        )
        error_id = error.id

        resolved = error_aggregator.resolve_error(error_id, "Fixed by patch")

        assert resolved is not None
        assert resolved.resolution == "Fixed by patch"
        assert resolved.resolved_at is not None

        # Should not be in unresolved list
        unresolved = error_aggregator.get_unresolved()
        assert len(unresolved) == 0

    def test_resolve_nonexistent_error(self, error_aggregator):
        """Test resolving a non-existent error."""
        result = error_aggregator.resolve_error("nonexistent-id", "Fix")
        assert result is None

    def test_get_unresolved_filter_severity(self, error_aggregator):
        """Test filtering unresolved errors by severity."""
        error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="critical_error",
            message="Critical",
            severity=ErrorSeverity.CRITICAL,
        )
        error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="normal_error",
            message="Normal",
            severity=ErrorSeverity.ERROR,
        )

        critical = error_aggregator.get_unresolved(severity=ErrorSeverity.CRITICAL)
        assert len(critical) == 1
        assert critical[0].message == "Critical"

    def test_get_unresolved_filter_phase(self, error_aggregator):
        """Test filtering unresolved errors by phase."""
        error_aggregator.add_error(
            source=ErrorSource.STATE,
            error_type="error",
            message="Phase 1 error",
            phase=1,
        )
        error_aggregator.add_error(
            source=ErrorSource.STATE,
            error_type="error",
            message="Phase 2 error",
            phase=2,
        )

        phase2_errors = error_aggregator.get_unresolved(phase=2)
        assert len(phase2_errors) == 1
        assert phase2_errors[0].message == "Phase 2 error"

    def test_get_unresolved_filter_agent(self, error_aggregator):
        """Test filtering unresolved errors by agent."""
        error_aggregator.add_error(
            source=ErrorSource.AGENT_OUTPUT,
            error_type="error",
            message="Claude error",
            agent="claude",
        )
        error_aggregator.add_error(
            source=ErrorSource.AGENT_OUTPUT,
            error_type="error",
            message="Cursor error",
            agent="cursor",
        )

        cursor_errors = error_aggregator.get_unresolved(agent="cursor")
        assert len(cursor_errors) == 1
        assert cursor_errors[0].message == "Cursor error"

    def test_get_all_errors(self, error_aggregator):
        """Test getting all errors including resolved."""
        error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="error1",
            message="Error 1",
        )
        error2 = error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="error2",
            message="Error 2",
        )
        error_aggregator.resolve_error(error2.id, "Fixed")
        error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="error3",
            message="Error 3",
        )

        all_errors = error_aggregator.get_all_errors()
        assert len(all_errors) >= 2  # At least 2 unique errors

    def test_collect_from_action_log(self, error_aggregator, temp_workflow_dir):
        """Test collecting errors from action log."""
        action_log_file = temp_workflow_dir / "action_log.jsonl"

        # Create mock action log entries
        entries = [
            {"id": "1", "action_type": "info", "message": "Normal action", "status": "completed"},
            {
                "id": "2",
                "action_type": "error",
                "message": "Error action",
                "status": "failed",
                "error": {"error_type": "TestError", "message": "Something failed"},
            },
            {"id": "3", "action_type": "phase_failed", "message": "Phase failed", "phase": 2},
        ]
        with open(action_log_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        collected = error_aggregator.collect_from_action_log(action_log_file)

        assert collected == 2  # Two error entries
        unresolved = error_aggregator.get_unresolved()
        assert len(unresolved) == 2

    def test_collect_from_state(self, error_aggregator, temp_workflow_dir):
        """Test collecting errors from state.json."""
        state_file = temp_workflow_dir / "state.json"

        state = {
            "phases": {
                "planning": {"status": "completed"},
                "validation": {
                    "status": "failed",
                    "error": "Validation score too low",
                    "attempts": 3,
                },
                "implementation": {
                    "status": "blocked",
                    "blockers": ["Missing API key", "Database not running"],
                },
            }
        }
        with open(state_file, "w") as f:
            json.dump(state, f)

        collected = error_aggregator.collect_from_state(state_file)

        assert collected == 3  # 1 failed + 2 blockers
        unresolved = error_aggregator.get_unresolved()
        assert len(unresolved) == 3

    def test_get_summary(self, error_aggregator):
        """Test summary generation."""
        error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="critical",
            message="Critical error",
            severity=ErrorSeverity.CRITICAL,
            phase=2,
            agent="cursor",
        )
        error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="error",
            message="Normal error",
            severity=ErrorSeverity.ERROR,
            phase=3,
        )

        summary = error_aggregator.get_summary()

        assert summary["unresolved_count"] == 2
        assert summary["has_critical"] is True
        assert summary["critical_count"] == 1
        assert "critical" in summary["by_severity"]
        assert "2" in summary["by_phase"]
        assert "cursor" in summary["by_agent"]

    def test_clear(self, error_aggregator, temp_workflow_dir):
        """Test clearing all errors."""
        error_aggregator.add_error(
            source=ErrorSource.EXCEPTION,
            error_type="error",
            message="Test error",
        )
        error_aggregator.clear()

        unresolved = error_aggregator.get_unresolved()
        assert len(unresolved) == 0

        all_errors_file = temp_workflow_dir / "errors" / "aggregated.jsonl"
        assert not all_errors_file.exists()


class TestGlobalErrorAggregator:
    """Tests for global error aggregator instance."""

    def test_get_error_aggregator(self, temp_workflow_dir):
        """Test getting global instance."""
        reset_error_aggregator()

        agg1 = get_error_aggregator(temp_workflow_dir)
        agg2 = get_error_aggregator(temp_workflow_dir)

        assert agg1 is agg2

        reset_error_aggregator()

    def test_reset_error_aggregator(self, temp_workflow_dir):
        """Test resetting global instance."""
        agg1 = get_error_aggregator(temp_workflow_dir)
        reset_error_aggregator()
        agg2 = get_error_aggregator(temp_workflow_dir)

        assert agg1 is not agg2

        reset_error_aggregator()
