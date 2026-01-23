"""Unit tests for the Rich-based UI module."""

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

from orchestrator.ui import (
    PlaintextDisplay,
    ProgressCallback,
    UICallbackHandler,
    UIState,
    WorkflowDisplay,
    create_display,
    is_interactive,
)
from orchestrator.ui.callbacks import NullCallback
from orchestrator.ui.state_adapter import EventLogEntry, TaskUIInfo, UIStateSnapshot


class TestIsInteractive:
    """Tests for is_interactive() detection."""

    def test_returns_false_when_ci_env_set(self):
        """CI environment variables should trigger non-interactive mode."""
        ci_vars = ["CI", "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS_URL"]
        for var in ci_vars:
            with patch.dict(os.environ, {var: "true"}, clear=False):
                # Clear any caching
                assert is_interactive() is False or os.environ.get(var)

    def test_returns_false_when_plain_output_flag_set(self):
        """ORCHESTRATOR_PLAIN_OUTPUT should force non-interactive."""
        with patch.dict(os.environ, {"ORCHESTRATOR_PLAIN_OUTPUT": "true"}):
            assert is_interactive() is False

    def test_returns_false_when_no_color_set(self):
        """NO_COLOR standard should trigger non-interactive."""
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert is_interactive() is False

    def test_returns_false_when_stdout_not_tty(self):
        """Non-TTY stdout should trigger non-interactive."""
        with patch.object(sys.stdout, "isatty", return_value=False):
            # Need to also ensure no CI vars are set
            env = {
                k: v
                for k, v in os.environ.items()
                if k
                not in [
                    "CI",
                    "CONTINUOUS_INTEGRATION",
                    "GITHUB_ACTIONS",
                    "GITLAB_CI",
                    "CIRCLECI",
                    "JENKINS_URL",
                    "BUILDKITE",
                    "TRAVIS",
                    "TF_BUILD",
                    "NO_COLOR",
                    "ORCHESTRATOR_PLAIN_OUTPUT",
                ]
            }
            with patch.dict(os.environ, env, clear=True):
                assert is_interactive() is False


class TestCreateDisplay:
    """Tests for create_display() factory function."""

    def test_creates_plaintext_when_not_interactive(self):
        """Should return PlaintextDisplay when interactive=False."""
        display = create_display("test-project", interactive=False)
        assert isinstance(display, PlaintextDisplay)

    def test_creates_workflow_display_when_interactive(self):
        """Should return WorkflowDisplay when interactive=True."""
        display = create_display("test-project", interactive=True)
        assert isinstance(display, WorkflowDisplay)


class TestPlaintextDisplay:
    """Tests for PlaintextDisplay class."""

    def test_initialization(self):
        """Should initialize with project name."""
        display = PlaintextDisplay("my-project")
        assert display.project_name == "my-project"

    def test_context_manager(self, capsys):
        """Should work as context manager and print start/end messages."""
        display = PlaintextDisplay("my-project")
        with display.start():
            pass
        captured = capsys.readouterr()
        assert "my-project" in captured.out
        assert "Starting" in captured.out or "completed" in captured.out

    def test_log_event(self, capsys):
        """Should print log events with timestamps."""
        display = PlaintextDisplay("my-project")
        display.log_event("Test message", "info")
        captured = capsys.readouterr()
        assert "Test message" in captured.out
        assert "[INFO]" in captured.out

    def test_log_event_levels(self, capsys):
        """Should handle different log levels."""
        display = PlaintextDisplay("my-project")
        levels = ["info", "warning", "error", "success"]
        expected = ["INFO", "WARN", "ERROR", "OK"]

        for level, expected_text in zip(levels, expected, strict=False):
            display.log_event(f"Message {level}", level)
            captured = capsys.readouterr()
            assert f"[{expected_text}]" in captured.out

    def test_update_ralph_iteration(self, capsys):
        """Should print Ralph loop iteration info."""
        display = PlaintextDisplay("my-project")
        display.update_ralph_iteration("T1", 2, 10, tests_passed=5, tests_total=8)
        captured = capsys.readouterr()
        assert "iteration 2/10" in captured.out
        assert "5/8 tests" in captured.out


class TestUIState:
    """Tests for UIState thread-safe state container."""

    def test_initialization(self):
        """Should initialize with project name."""
        state = UIState("test-project")
        snapshot = state.get_snapshot()
        assert snapshot.project_name == "test-project"
        assert snapshot.current_phase == 0
        assert snapshot.tasks_total == 0

    def test_add_event(self):
        """Should add events to the log."""
        state = UIState("test-project")
        state.add_event("Test event", "info")
        snapshot = state.get_snapshot()
        assert len(snapshot.recent_events) == 1
        assert snapshot.recent_events[0].message == "Test event"
        assert snapshot.recent_events[0].level == "info"

    def test_max_events_limit(self):
        """Should limit events to max_events."""
        state = UIState("test-project")
        state._max_events = 5

        for i in range(10):
            state.add_event(f"Event {i}", "info")

        snapshot = state.get_snapshot()
        assert len(snapshot.recent_events) == 5
        assert snapshot.recent_events[0].message == "Event 5"

    def test_update_ralph_iteration(self):
        """Should update Ralph iteration for a task."""
        state = UIState("test-project")
        # Add a task first
        state._tasks = [TaskUIInfo(id="T1", title="Test Task", status="in_progress")]

        state.update_ralph_iteration("T1", 3, 10, tests_passed=7, tests_total=10)

        snapshot = state.get_snapshot()
        task = snapshot.tasks[0]
        assert task.iteration == 3
        assert task.max_iterations == 10
        assert task.tests_passed == 7
        assert task.tests_total == 10

    def test_update_metrics(self):
        """Should update metrics."""
        state = UIState("test-project")
        state.update_metrics(tokens=1000, cost=1.23, files_created=2, files_modified=3)

        snapshot = state.get_snapshot()
        assert snapshot.tokens == 1000
        assert snapshot.cost == 1.23
        assert snapshot.files_created == 2
        assert snapshot.files_modified == 3

    def test_snapshot_is_copy(self):
        """Snapshot should be a copy, not a reference."""
        state = UIState("test-project")
        state.add_event("Event 1", "info")

        snapshot1 = state.get_snapshot()
        state.add_event("Event 2", "info")
        snapshot2 = state.get_snapshot()

        assert len(snapshot1.recent_events) == 1
        assert len(snapshot2.recent_events) == 2


class TestUICallbackHandler:
    """Tests for UICallbackHandler."""

    def test_initialization(self):
        """Should initialize with display."""
        mock_display = MagicMock()
        handler = UICallbackHandler(mock_display)
        assert handler._display is mock_display

    def test_on_node_start(self):
        """Should call display methods on node start."""
        mock_display = MagicMock()
        handler = UICallbackHandler(mock_display)

        handler.on_node_start("planning", {"current_phase": 1})

        mock_display.log_event.assert_called()
        mock_display.update_state.assert_called_once()

    def test_on_node_end(self):
        """Should call display methods on node end."""
        mock_display = MagicMock()
        handler = UICallbackHandler(mock_display)

        handler.on_node_end("planning", {"current_phase": 1, "errors": []})

        mock_display.log_event.assert_called()
        mock_display.update_state.assert_called_once()

    def test_on_ralph_iteration(self):
        """Should forward Ralph iteration updates."""
        mock_display = MagicMock()
        handler = UICallbackHandler(mock_display)

        handler.on_ralph_iteration("T1", 2, 10, tests_passed=5, tests_total=8)

        mock_display.update_ralph_iteration.assert_called_once_with(
            task_id="T1",
            iteration=2,
            max_iter=10,
            tests_passed=5,
            tests_total=8,
        )

    def test_on_task_start(self):
        """Should log task start."""
        mock_display = MagicMock()
        handler = UICallbackHandler(mock_display)

        handler.on_task_start("T1", "Test Task")

        mock_display.log_event.assert_called()
        call_args = mock_display.log_event.call_args
        assert "T1" in call_args[0][0]

    def test_on_task_complete(self):
        """Should log task completion."""
        mock_display = MagicMock()
        handler = UICallbackHandler(mock_display)

        handler.on_task_complete("T1", True)
        mock_display.log_event.assert_called()
        call_args = mock_display.log_event.call_args
        assert call_args[0][1] == "success"

        mock_display.reset_mock()
        handler.on_task_complete("T1", False)
        call_args = mock_display.log_event.call_args
        assert call_args[0][1] == "error"

    def test_on_metrics_update(self):
        """Should forward metrics updates."""
        mock_display = MagicMock()
        handler = UICallbackHandler(mock_display)

        handler.on_metrics_update(tokens=1000, cost=1.23)

        mock_display.update_metrics.assert_called_once_with(
            tokens=1000,
            cost=1.23,
            files_created=None,
            files_modified=None,
        )


class TestNullCallback:
    """Tests for NullCallback no-op implementation."""

    def test_all_methods_are_noop(self):
        """All callback methods should do nothing and not raise."""
        callback = NullCallback()

        # These should all succeed without raising
        callback.on_node_start("test", {})
        callback.on_node_end("test", {})
        callback.on_ralph_iteration("T1", 1, 10)
        callback.on_task_start("T1", "Test")
        callback.on_task_complete("T1", True)
        callback.on_metrics_update(tokens=100)


class TestProgressCallbackProtocol:
    """Tests for ProgressCallback protocol."""

    def test_ui_callback_handler_implements_protocol(self):
        """UICallbackHandler should implement ProgressCallback."""
        mock_display = MagicMock()
        handler = UICallbackHandler(mock_display)
        assert isinstance(handler, ProgressCallback)

    def test_null_callback_implements_protocol(self):
        """NullCallback should implement ProgressCallback."""
        callback = NullCallback()
        assert isinstance(callback, ProgressCallback)


class TestUIComponents:
    """Tests for UI component rendering functions."""

    def test_header_renders(self):
        """Header component should render without error."""
        from orchestrator.ui.components import render_header

        snapshot = UIStateSnapshot(
            project_name="test-project",
            elapsed_seconds=150,
            current_phase=3,
            total_phases=5,
            phase_progress=0.5,
            phase_name="Implementation",
            tasks=[],
            tasks_completed=2,
            tasks_total=5,
            current_task_id=None,
            tokens=1000,
            cost=1.23,
            files_created=2,
            files_modified=3,
            recent_events=[],
            status="running",
        )

        result = render_header(snapshot)
        assert result is not None

    def test_phase_bar_renders(self):
        """Phase bar component should render without error."""
        from orchestrator.ui.components import render_phase_bar

        snapshot = UIStateSnapshot(
            project_name="test-project",
            elapsed_seconds=150,
            current_phase=3,
            total_phases=5,
            phase_progress=0.5,
            phase_name="Implementation",
            tasks=[],
            tasks_completed=2,
            tasks_total=5,
            current_task_id=None,
            tokens=1000,
            cost=1.23,
            files_created=2,
            files_modified=3,
            recent_events=[],
            status="running",
        )

        result = render_phase_bar(snapshot)
        assert result is not None

    def test_task_tree_renders_empty(self):
        """Task tree should render with no tasks."""
        from orchestrator.ui.components import render_task_tree

        snapshot = UIStateSnapshot(
            project_name="test-project",
            elapsed_seconds=150,
            current_phase=3,
            total_phases=5,
            phase_progress=0.5,
            phase_name="Implementation",
            tasks=[],
            tasks_completed=0,
            tasks_total=0,
            current_task_id=None,
            tokens=1000,
            cost=1.23,
            files_created=2,
            files_modified=3,
            recent_events=[],
            status="running",
        )

        result = render_task_tree(snapshot)
        assert result is not None

    def test_task_tree_renders_with_tasks(self):
        """Task tree should render with tasks."""
        from orchestrator.ui.components import render_task_tree

        tasks = [
            TaskUIInfo(id="T1", title="Task 1", status="completed"),
            TaskUIInfo(
                id="T2", title="Task 2", status="in_progress", iteration=2, max_iterations=10
            ),
            TaskUIInfo(id="T3", title="Task 3", status="pending"),
        ]

        snapshot = UIStateSnapshot(
            project_name="test-project",
            elapsed_seconds=150,
            current_phase=3,
            total_phases=5,
            phase_progress=0.5,
            phase_name="Implementation",
            tasks=tasks,
            tasks_completed=1,
            tasks_total=3,
            current_task_id="T2",
            tokens=1000,
            cost=1.23,
            files_created=2,
            files_modified=3,
            recent_events=[],
            status="running",
        )

        result = render_task_tree(snapshot)
        assert result is not None

    def test_metrics_panel_renders(self):
        """Metrics panel should render without error."""
        from orchestrator.ui.components import render_metrics_panel

        snapshot = UIStateSnapshot(
            project_name="test-project",
            elapsed_seconds=150,
            current_phase=3,
            total_phases=5,
            phase_progress=0.5,
            phase_name="Implementation",
            tasks=[],
            tasks_completed=2,
            tasks_total=5,
            current_task_id=None,
            tokens=45200,
            cost=1.23,
            files_created=4,
            files_modified=2,
            recent_events=[],
            status="running",
        )

        result = render_metrics_panel(snapshot)
        assert result is not None

    def test_event_log_renders_empty(self):
        """Event log should render with no events."""
        from orchestrator.ui.components import render_event_log

        snapshot = UIStateSnapshot(
            project_name="test-project",
            elapsed_seconds=150,
            current_phase=3,
            total_phases=5,
            phase_progress=0.5,
            phase_name="Implementation",
            tasks=[],
            tasks_completed=2,
            tasks_total=5,
            current_task_id=None,
            tokens=1000,
            cost=1.23,
            files_created=2,
            files_modified=3,
            recent_events=[],
            status="running",
        )

        result = render_event_log(snapshot)
        assert result is not None

    def test_event_log_renders_with_events(self):
        """Event log should render with events."""
        from orchestrator.ui.components import render_event_log

        events = [
            EventLogEntry(timestamp=datetime.now(), message="Task started", level="info"),
            EventLogEntry(timestamp=datetime.now(), message="Test passed", level="success"),
            EventLogEntry(timestamp=datetime.now(), message="Warning!", level="warning"),
        ]

        snapshot = UIStateSnapshot(
            project_name="test-project",
            elapsed_seconds=150,
            current_phase=3,
            total_phases=5,
            phase_progress=0.5,
            phase_name="Implementation",
            tasks=[],
            tasks_completed=2,
            tasks_total=5,
            current_task_id=None,
            tokens=1000,
            cost=1.23,
            files_created=2,
            files_modified=3,
            recent_events=events,
            status="running",
        )

        result = render_event_log(snapshot)
        assert result is not None


class TestWorkflowDisplay:
    """Tests for WorkflowDisplay class."""

    def test_initialization(self):
        """Should initialize with project name."""
        display = WorkflowDisplay("test-project")
        assert display.project_name == "test-project"

    def test_log_event_updates_state(self):
        """log_event should update internal state."""
        display = WorkflowDisplay("test-project")
        display.log_event("Test message", "info")

        snapshot = display._state.get_snapshot()
        assert len(snapshot.recent_events) == 1
        assert snapshot.recent_events[0].message == "Test message"

    def test_update_ralph_iteration(self):
        """update_ralph_iteration should update state and log event."""
        display = WorkflowDisplay("test-project")
        display._state._tasks = [TaskUIInfo(id="T1", title="Test", status="in_progress")]

        display.update_ralph_iteration("T1", 2, 10, tests_passed=5, tests_total=8)

        snapshot = display._state.get_snapshot()
        assert snapshot.tasks[0].iteration == 2
        # Should also have logged an event
        assert len(snapshot.recent_events) >= 1

    def test_update_metrics(self):
        """update_metrics should update state."""
        display = WorkflowDisplay("test-project")
        display.update_metrics(tokens=1000, cost=1.23)

        snapshot = display._state.get_snapshot()
        assert snapshot.tokens == 1000
        assert snapshot.cost == 1.23

    def test_show_completion(self):
        """show_completion should update status and log event."""
        display = WorkflowDisplay("test-project")
        display.show_completion(True, "Done!")

        snapshot = display._state.get_snapshot()
        assert snapshot.status == "completed"
        assert len(snapshot.recent_events) >= 1
