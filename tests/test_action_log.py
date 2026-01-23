"""Tests for ActionLog component."""

import json
import tempfile
from pathlib import Path

import pytest

from orchestrator.utils.action_log import (
    ActionEntry,
    ActionLog,
    ActionStatus,
    ActionType,
    ErrorInfo,
    get_action_log,
    reset_action_log,
)


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary workflow directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_dir = Path(tmpdir) / ".workflow"
        workflow_dir.mkdir()
        yield workflow_dir


@pytest.fixture
def action_log(temp_workflow_dir):
    """Create an action log instance."""
    return ActionLog(temp_workflow_dir, console_output=False)


class TestActionEntry:
    """Tests for ActionEntry dataclass."""

    def test_to_dict(self):
        entry = ActionEntry(
            id="test-id",
            timestamp="2024-01-15T10:00:00",
            action_type=ActionType.PHASE_START,
            message="Starting phase 1",
            status=ActionStatus.STARTED,
            phase=1,
        )
        result = entry.to_dict()

        assert result["id"] == "test-id"
        assert result["action_type"] == "phase_start"
        assert result["status"] == "started"
        assert result["phase"] == 1

    def test_from_dict(self):
        data = {
            "id": "test-id",
            "timestamp": "2024-01-15T10:00:00",
            "action_type": "phase_start",
            "message": "Starting phase 1",
            "status": "started",
            "phase": 1,
        }
        entry = ActionEntry.from_dict(data)

        assert entry.id == "test-id"
        assert entry.action_type == ActionType.PHASE_START
        assert entry.status == ActionStatus.STARTED


class TestErrorInfo:
    """Tests for ErrorInfo dataclass."""

    def test_from_exception(self):
        try:
            raise ValueError("Test error")
        except ValueError as e:
            error = ErrorInfo.from_exception(e, context={"key": "value"})

        assert error.error_type == "ValueError"
        assert error.message == "Test error"
        assert error.stack_trace is not None
        assert error.context == {"key": "value"}

    def test_to_dict(self):
        error = ErrorInfo(
            error_type="ValueError",
            message="Test error",
            context={"key": "value"},
        )
        result = error.to_dict()

        assert result["error_type"] == "ValueError"
        assert result["message"] == "Test error"


class TestActionLog:
    """Tests for ActionLog class."""

    def test_log_action(self, action_log, temp_workflow_dir):
        """Test basic action logging."""
        entry = action_log.log(
            ActionType.PHASE_START,
            "Starting phase 1",
            phase=1,
        )

        assert entry.action_type == ActionType.PHASE_START
        assert entry.message == "Starting phase 1"
        assert entry.phase == 1

        # Check file was written
        log_file = temp_workflow_dir / "action_log.jsonl"
        assert log_file.exists()

        with open(log_file) as f:
            data = json.loads(f.read().strip())
            assert data["message"] == "Starting phase 1"

    def test_log_with_agent(self, action_log):
        """Test logging with agent info."""
        entry = action_log.log(
            ActionType.AGENT_INVOKE,
            "Invoking Cursor",
            phase=2,
            agent="cursor",
        )

        assert entry.agent == "cursor"
        assert entry.phase == 2

    def test_log_with_error(self, action_log):
        """Test logging with error info."""
        error = ErrorInfo(
            error_type="TestError",
            message="Something went wrong",
        )
        entry = action_log.log(
            ActionType.ERROR,
            "Test error occurred",
            status=ActionStatus.FAILED,
            error=error,
        )

        assert entry.error is not None
        assert entry.error.error_type == "TestError"

    def test_log_with_task(self, action_log):
        """Test logging with task info."""
        entry = action_log.log(
            ActionType.TASK_START,
            "Starting task T1",
            phase=3,
            task_id="T1",
        )

        assert entry.task_id == "T1"

    def test_get_recent(self, action_log):
        """Test retrieving recent actions."""
        # Log multiple actions
        for i in range(10):
            action_log.log(ActionType.INFO, f"Action {i}")

        recent = action_log.get_recent(5)

        assert len(recent) == 5
        # Most recent first
        assert "Action 9" in recent[0].message

    def test_get_errors(self, action_log):
        """Test retrieving error actions."""
        action_log.log(ActionType.INFO, "Normal action")
        action_log.log(
            ActionType.ERROR,
            "Error action",
            status=ActionStatus.FAILED,
        )
        action_log.log(ActionType.INFO, "Another normal action")

        errors = action_log.get_errors()

        assert len(errors) == 1
        assert errors[0].message == "Error action"

    def test_get_by_phase(self, action_log):
        """Test filtering by phase."""
        action_log.log(ActionType.PHASE_START, "Phase 1", phase=1)
        action_log.log(ActionType.PHASE_START, "Phase 2", phase=2)
        action_log.log(ActionType.AGENT_INVOKE, "Agent in phase 2", phase=2)

        phase2_actions = action_log.get_by_phase(2)

        assert len(phase2_actions) == 2

    def test_get_by_agent(self, action_log):
        """Test filtering by agent."""
        action_log.log(ActionType.AGENT_INVOKE, "Claude action", agent="claude")
        action_log.log(ActionType.AGENT_INVOKE, "Cursor action", agent="cursor")
        action_log.log(ActionType.AGENT_COMPLETE, "Claude done", agent="claude")

        claude_actions = action_log.get_by_agent("claude")

        assert len(claude_actions) == 2

    def test_get_by_task(self, action_log):
        """Test filtering by task."""
        action_log.log(ActionType.TASK_START, "Task 1", task_id="T1")
        action_log.log(ActionType.TASK_START, "Task 2", task_id="T2")
        action_log.log(ActionType.TASK_COMPLETE, "Task 1 done", task_id="T1")

        t1_actions = action_log.get_by_task("T1")

        assert len(t1_actions) == 2

    def test_get_summary(self, action_log):
        """Test summary generation."""
        action_log.log(ActionType.PHASE_START, "Phase 1", phase=1)
        action_log.log(ActionType.AGENT_INVOKE, "Claude", agent="claude", phase=1)
        action_log.log(ActionType.ERROR, "Error", status=ActionStatus.FAILED)

        summary = action_log.get_summary()

        assert summary["total_actions"] == 3
        assert summary["error_count"] == 1
        assert "1" in summary["actions_by_phase"]
        assert "claude" in summary["actions_by_agent"]

    def test_clear(self, action_log, temp_workflow_dir):
        """Test clearing the log."""
        action_log.log(ActionType.INFO, "Test action")
        action_log.clear()

        log_file = temp_workflow_dir / "action_log.jsonl"
        assert not log_file.exists()

        summary = action_log.get_summary()
        assert summary["total_actions"] == 0

    def test_index_persistence(self, temp_workflow_dir):
        """Test that index is persisted between instances."""
        log1 = ActionLog(temp_workflow_dir, console_output=False)
        log1.log(ActionType.PHASE_START, "Phase 1", phase=1)
        log1.log(ActionType.AGENT_INVOKE, "Claude", agent="claude")

        # Create new instance
        log2 = ActionLog(temp_workflow_dir, console_output=False)
        summary = log2.get_summary()

        assert summary["total_actions"] == 2


class TestGlobalActionLog:
    """Tests for global action log instance."""

    def test_get_action_log(self, temp_workflow_dir):
        """Test getting global instance."""
        reset_action_log()

        log1 = get_action_log(temp_workflow_dir)
        log2 = get_action_log(temp_workflow_dir)

        assert log1 is log2

        reset_action_log()

    def test_reset_action_log(self, temp_workflow_dir):
        """Test resetting global instance."""
        log1 = get_action_log(temp_workflow_dir)
        reset_action_log()
        log2 = get_action_log(temp_workflow_dir)

        assert log1 is not log2

        reset_action_log()
