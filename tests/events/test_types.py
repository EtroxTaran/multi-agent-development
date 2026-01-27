"""Tests for event type definitions and factory functions."""


from orchestrator.events.types import (
    EventPriority,
    EventType,
    WorkflowEvent,
    node_end_event,
    node_start_event,
    phase_change_event,
    phase_end_event,
    phase_start_event,
    task_complete_event,
    task_start_event,
    tasks_created_event,
    workflow_complete_event,
    workflow_start_event,
)


class TestEventType:
    """Tests for EventType enum."""

    def test_event_types_exist(self):
        """Test that all expected event types exist."""
        assert EventType.NODE_START == "node_start"
        assert EventType.NODE_END == "node_end"
        assert EventType.PHASE_START == "phase_start"
        assert EventType.PHASE_END == "phase_end"
        assert EventType.PHASE_CHANGE == "phase_change"
        assert EventType.TASK_START == "task_start"
        assert EventType.TASK_COMPLETE == "task_complete"
        assert EventType.TASK_FAILED == "task_failed"
        assert EventType.TASKS_CREATED == "tasks_created"

    def test_tasks_created_event_type(self):
        """Test that TASKS_CREATED event type exists."""
        assert hasattr(EventType, "TASKS_CREATED")
        assert EventType.TASKS_CREATED.value == "tasks_created"


class TestWorkflowEvent:
    """Tests for WorkflowEvent dataclass."""

    def test_create_event(self):
        """Test creating a basic event."""
        event = WorkflowEvent(
            event_type=EventType.NODE_START,
            project_name="test-project",
        )
        assert event.event_type == EventType.NODE_START
        assert event.project_name == "test-project"
        assert event.priority == EventPriority.MEDIUM

    def test_to_dict(self):
        """Test converting event to dictionary."""
        event = WorkflowEvent(
            event_type=EventType.NODE_START,
            project_name="test-project",
            phase=1,
            node_name="planning",
            data={"key": "value"},
        )
        d = event.to_dict()
        assert d["event_type"] == "node_start"
        assert d["project_name"] == "test-project"
        assert d["phase"] == 1
        assert d["node_name"] == "planning"
        assert d["data"]["key"] == "value"

    def test_from_dict(self):
        """Test creating event from dictionary."""
        data = {
            "event_type": "node_start",
            "project_name": "test-project",
            "phase": 2,
            "priority": "high",
            "data": {"status": "running"},
        }
        event = WorkflowEvent.from_dict(data)
        assert event.event_type == EventType.NODE_START
        assert event.project_name == "test-project"
        assert event.phase == 2
        assert event.priority == EventPriority.HIGH


class TestPhaseStartEvent:
    """Tests for phase_start_event factory function."""

    def test_creates_correct_structure(self):
        """Test phase_start_event creates proper WorkflowEvent."""
        event = phase_start_event(
            project_name="test-project",
            phase=2,
            node_name="planning",
        )

        assert event.event_type == EventType.PHASE_START
        assert event.project_name == "test-project"
        assert event.phase == 2
        assert event.node_name == "planning"
        assert event.priority == EventPriority.HIGH
        assert event.data["phase"] == 2
        assert event.data["status"] == "in_progress"

    def test_without_node_name(self):
        """Test phase_start_event works without node_name."""
        event = phase_start_event(project_name="test", phase=1)

        assert event.node_name is None
        assert event.phase == 1
        assert event.priority == EventPriority.HIGH


class TestPhaseEndEvent:
    """Tests for phase_end_event factory function."""

    def test_success(self):
        """Test phase_end_event with success=True."""
        event = phase_end_event(
            project_name="test-project",
            phase=1,
            success=True,
            node_name="planning",
        )

        assert event.event_type == EventType.PHASE_END
        assert event.priority == EventPriority.HIGH
        assert event.data["phase"] == 1
        assert event.data["success"] is True
        assert event.data["status"] == "completed"
        assert event.data.get("error") is None

    def test_failure(self):
        """Test phase_end_event with success=False."""
        event = phase_end_event(
            project_name="test-project",
            phase=2,
            success=False,
            error="Validation failed",
        )

        assert event.data["success"] is False
        assert event.data["status"] == "failed"
        assert event.data["error"] == "Validation failed"


class TestPhaseChangeEvent:
    """Tests for phase_change_event factory function."""

    def test_creates_correct_structure(self):
        """Test phase_change_event creates proper WorkflowEvent."""
        event = phase_change_event(
            project_name="test-project",
            from_phase=1,
            to_phase=2,
            status="in_progress",
        )

        assert event.event_type == EventType.PHASE_CHANGE
        assert event.project_name == "test-project"
        assert event.phase == 2
        assert event.priority == EventPriority.HIGH
        assert event.data["from_phase"] == 1
        assert event.data["to_phase"] == 2
        assert event.data["status"] == "in_progress"


class TestTasksCreatedEvent:
    """Tests for tasks_created_event factory function."""

    def test_creates_correct_structure(self):
        """Test tasks_created_event creates proper WorkflowEvent."""
        event = tasks_created_event(
            project_name="test-project",
            task_count=5,
            milestone_count=2,
            phase=1,
        )

        assert event.event_type == EventType.TASKS_CREATED
        assert event.project_name == "test-project"
        assert event.phase == 1
        assert event.priority == EventPriority.HIGH
        assert event.data["task_count"] == 5
        assert event.data["milestone_count"] == 2

    def test_default_phase(self):
        """Test tasks_created_event defaults to phase 1."""
        event = tasks_created_event(
            project_name="test",
            task_count=3,
            milestone_count=1,
        )

        assert event.phase == 1


class TestExistingEventFactories:
    """Tests for existing event factory functions (regression tests)."""

    def test_node_start_event(self):
        """Test node_start_event creates proper event."""
        event = node_start_event(
            project_name="test",
            node_name="planning",
            phase=1,
            state_summary={"key": "value"},
        )
        assert event.event_type == EventType.NODE_START
        assert event.priority == EventPriority.LOW

    def test_node_end_event(self):
        """Test node_end_event creates proper event."""
        event = node_end_event(
            project_name="test",
            node_name="planning",
            phase=1,
            success=True,
            duration_seconds=5.5,
        )
        assert event.event_type == EventType.NODE_END
        assert event.data["success"] is True
        assert event.data["duration_seconds"] == 5.5

    def test_task_start_event(self):
        """Test task_start_event creates proper event."""
        event = task_start_event(
            project_name="test",
            task_id="T1",
            task_title="Implement feature",
        )
        assert event.event_type == EventType.TASK_START
        assert event.task_id == "T1"
        assert event.data["title"] == "Implement feature"

    def test_task_complete_event_success(self):
        """Test task_complete_event with success."""
        event = task_complete_event(
            project_name="test",
            task_id="T1",
            success=True,
        )
        assert event.event_type == EventType.TASK_COMPLETE

    def test_task_complete_event_failure(self):
        """Test task_complete_event with failure."""
        event = task_complete_event(
            project_name="test",
            task_id="T1",
            success=False,
            error="Test failed",
        )
        assert event.event_type == EventType.TASK_FAILED

    def test_workflow_start_event(self):
        """Test workflow_start_event creates proper event."""
        event = workflow_start_event(
            project_name="test",
            mode="langgraph",
            start_phase=1,
            autonomous=False,
        )
        assert event.event_type == EventType.WORKFLOW_START
        assert event.priority == EventPriority.HIGH

    def test_workflow_complete_event(self):
        """Test workflow_complete_event creates proper event."""
        event = workflow_complete_event(
            project_name="test",
            success=True,
            final_phase=5,
        )
        assert event.event_type == EventType.WORKFLOW_COMPLETE
        assert event.priority == EventPriority.HIGH
