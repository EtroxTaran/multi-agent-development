"""Tests for DashboardCallback."""

from unittest.mock import MagicMock

from orchestrator.events.callback import DashboardCallback, create_dashboard_callback
from orchestrator.events.emitter import EventEmitter


class TestDashboardCallback:
    """Tests for DashboardCallback class."""

    def test_create_dashboard_callback(self):
        """Test factory function."""
        callback = create_dashboard_callback("test-project")
        assert callback.emitter.project_name == "test-project"
        assert callback.emitter.enabled is True
        assert callback.current_phase == 1

    def test_create_dashboard_callback_with_options(self):
        """Test factory function with options."""
        callback = create_dashboard_callback(
            project_name="test-project",
            enabled=False,
            current_phase=3,
        )
        assert callback.emitter.enabled is False
        assert callback.current_phase == 3

    def test_set_phase(self):
        """Test setting current phase."""
        callback = create_dashboard_callback("test-project")
        callback.set_phase(3)
        assert callback.current_phase == 3

    def test_on_node_start_tracks_time(self):
        """Test that on_node_start records start time."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_node_start("planning", {"current_phase": 1})

        assert "planning" in callback._node_start_times
        emitter.emit.assert_called()

    def test_on_node_end_calculates_duration(self):
        """Test that on_node_end calculates duration."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        # Simulate node start
        import time

        callback._node_start_times["planning"] = time.time() - 1.5

        callback.on_node_end("planning", {"errors": []})

        # Start time should be removed
        assert "planning" not in callback._node_start_times
        # Emit should be called with calculated duration
        emitter.emit.assert_called()

    def test_on_task_start_emits_event(self):
        """Test that on_task_start emits event."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_task_start("T1", "Implement feature")

        emitter.emit.assert_called()

    def test_on_task_complete_emits_event(self):
        """Test that on_task_complete emits event."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_task_complete("T1", success=True)

        emitter.emit.assert_called()

    def test_on_error_emits_immediately(self):
        """Test that errors are emitted immediately."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_error(
            error_message="Test error",
            error_type="TestError",
            node_name="planning",
        )

        # Should use emit_now for immediate delivery
        emitter.emit_now.assert_called()

    def test_on_escalation_emits_immediately(self):
        """Test that escalations are emitted immediately."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_escalation(
            question="Need clarification",
            options=["option1", "option2"],
        )

        # Should use emit_now for immediate delivery
        emitter.emit_now.assert_called()

    def test_on_workflow_start_emits_event(self):
        """Test that workflow start emits event."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_workflow_start(mode="langgraph", start_phase=1)

        emitter.emit_now.assert_called()

    def test_on_workflow_complete_emits_event(self):
        """Test that workflow complete emits event."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_workflow_complete(success=True, final_phase=5)

        emitter.emit_now.assert_called()

    def test_on_workflow_paused_emits_event(self):
        """Test that workflow paused emits event."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_workflow_paused(reason="User requested")

        emitter.emit_now.assert_called()

    def test_on_agent_start_emits_event(self):
        """Test that agent start emits event."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_agent_start(
            agent_name="claude",
            node_name="planning",
            task_id="T1",
        )

        emitter.emit.assert_called()

    def test_on_agent_complete_emits_event(self):
        """Test that agent complete emits event."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_agent_complete(
            agent_name="claude",
            node_name="planning",
            success=True,
            duration_seconds=5.5,
        )

        emitter.emit.assert_called()

    def test_on_ralph_iteration_emits_event(self):
        """Test that Ralph iteration emits event."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_ralph_iteration(
            task_id="T1",
            iteration=2,
            max_iter=5,
            tests_passed=3,
            tests_total=5,
        )

        emitter.emit.assert_called()

    def test_on_metrics_update_emits_event(self):
        """Test that metrics update emits event."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_metrics_update(
            tokens=1000,
            cost=0.05,
            files_created=2,
        )

        emitter.emit.assert_called()

    # ==================== Phase Event Tests ====================

    def test_on_phase_start_emits_immediately(self):
        """Test that phase start emits immediately via emit_now."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_phase_start(phase=2, node_name="planning")

        # Should use emit_now for immediate delivery
        emitter.emit_now.assert_called()
        # Should update current_phase
        assert callback.current_phase == 2

    def test_on_phase_start_without_node_name(self):
        """Test phase_start without node_name."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_phase_start(phase=1)

        emitter.emit_now.assert_called()
        assert callback.current_phase == 1

    def test_on_phase_end_success(self):
        """Test that phase end emits immediately with success."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_phase_end(phase=1, success=True, node_name="planning")

        emitter.emit_now.assert_called()

    def test_on_phase_end_with_error(self):
        """Test phase end with error message."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_phase_end(
            phase=2,
            success=False,
            error="Validation failed",
        )

        emitter.emit_now.assert_called()

    def test_on_phase_change_emits_immediately(self):
        """Test that phase change emits immediately via emit_now."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_phase_change(from_phase=1, to_phase=2, status="in_progress")

        emitter.emit_now.assert_called()
        # Should update current_phase
        assert callback.current_phase == 2

    def test_on_tasks_created_emits_immediately(self):
        """Test that tasks_created emits immediately via emit_now."""
        emitter = MagicMock(spec=EventEmitter)
        emitter.project_name = "test-project"
        callback = DashboardCallback(emitter)

        callback.on_tasks_created(task_count=5, milestone_count=2)

        emitter.emit_now.assert_called()
