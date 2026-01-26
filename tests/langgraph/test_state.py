"""Tests for LangGraph workflow state.

Tests state initialization, task management, phase tracking,
reducers, and helper functions.
"""

from datetime import datetime

from orchestrator.langgraph.state import (
    AgentFeedback,
    PhaseState,
    PhaseStatus,
    WorkflowState,
    create_agent_execution,
    create_error_context,
    create_initial_state,
    create_task,
    get_available_tasks,
    get_task_by_id,
)


class TestCreateInitialState:
    """Tests for create_initial_state function."""

    def test_creates_state_with_required_fields(self, temp_project_dir):
        """Test initial state has all required fields."""
        state = create_initial_state(
            project_name="test-project",
            project_dir=str(temp_project_dir),
        )

        assert state["project_name"] == "test-project"
        assert state["project_dir"] == str(temp_project_dir)
        assert state["current_phase"] >= 0  # Initial phase can be 0 or 1
        assert isinstance(state["created_at"], str)
        assert isinstance(state["updated_at"], str)

    def test_creates_empty_collections(self, temp_project_dir):
        """Test initial state has empty collections."""
        state = create_initial_state(
            project_name="test-project",
            project_dir=str(temp_project_dir),
        )

        assert state.get("errors", []) == []
        assert state.get("tasks", []) == []
        assert state.get("execution_history", []) == []

    def test_creates_phase_status(self, temp_project_dir):
        """Test initial state has phase status initialized."""
        state = create_initial_state(
            project_name="test-project",
            project_dir=str(temp_project_dir),
        )

        phase_status = state.get("phase_status", {})
        # Should have entries for phases 1-5
        assert len(phase_status) >= 5

    def test_timestamps_are_iso_format(self, temp_project_dir):
        """Test timestamps are valid ISO format."""
        state = create_initial_state(
            project_name="test-project",
            project_dir=str(temp_project_dir),
        )

        # Should parse without error
        datetime.fromisoformat(state["created_at"])
        datetime.fromisoformat(state["updated_at"])


class TestCreateTask:
    """Tests for create_task function."""

    def test_creates_task_with_required_fields(self):
        """Test task creation with required fields."""
        task = create_task(
            task_id="T1",
            title="Test task",
        )

        assert task["id"] == "T1"
        assert task["title"] == "Test task"
        assert task["status"] == "pending"

    def test_creates_task_with_all_fields(self):
        """Test task creation with all fields."""
        task = create_task(
            task_id="T2",
            title="Full task",
            acceptance_criteria=["Criterion 1", "Criterion 2"],
            files_to_create=["file1.py", "file2.py"],
            files_to_modify=["existing.py"],
            dependencies=["T1"],
        )

        assert task["id"] == "T2"
        assert task["title"] == "Full task"
        assert task["acceptance_criteria"] == ["Criterion 1", "Criterion 2"]
        assert task["files_to_create"] == ["file1.py", "file2.py"]
        assert task["files_to_modify"] == ["existing.py"]
        assert task["dependencies"] == ["T1"]
        assert task["status"] == "pending"

    def test_default_empty_lists(self):
        """Test default empty lists for optional fields."""
        task = create_task(task_id="T1", title="Minimal")

        assert task.get("acceptance_criteria", []) == []
        assert task.get("files_to_create", []) == []
        assert task.get("files_to_modify", []) == []
        assert task.get("dependencies", []) == []


class TestGetTaskById:
    """Tests for get_task_by_id function."""

    def test_finds_existing_task(self, minimal_workflow_state):
        """Test finding an existing task."""
        minimal_workflow_state["tasks"] = [
            create_task(task_id="T1", title="Task 1"),
            create_task(task_id="T2", title="Task 2"),
        ]

        task = get_task_by_id(minimal_workflow_state, "T2")
        assert task is not None
        assert task["id"] == "T2"
        assert task["title"] == "Task 2"

    def test_returns_none_for_missing_task(self, minimal_workflow_state):
        """Test None returned for missing task."""
        minimal_workflow_state["tasks"] = [
            create_task(task_id="T1", title="Task 1"),
        ]

        task = get_task_by_id(minimal_workflow_state, "T99")
        assert task is None

    def test_returns_none_for_empty_tasks(self, minimal_workflow_state):
        """Test None returned when no tasks exist."""
        minimal_workflow_state["tasks"] = []

        task = get_task_by_id(minimal_workflow_state, "T1")
        assert task is None


class TestGetAvailableTasks:
    """Tests for get_available_tasks function."""

    def test_returns_pending_tasks_without_dependencies(self, minimal_workflow_state):
        """Test returning pending tasks with no dependencies."""
        minimal_workflow_state["tasks"] = [
            create_task(task_id="T1", title="Task 1"),
            create_task(task_id="T2", title="Task 2"),
        ]

        available = get_available_tasks(minimal_workflow_state)
        assert len(available) == 2

    def test_excludes_completed_tasks(self, minimal_workflow_state):
        """Test excluding completed tasks."""
        task1 = create_task(task_id="T1", title="Task 1")
        task1["status"] = "completed"
        task2 = create_task(task_id="T2", title="Task 2")

        minimal_workflow_state["tasks"] = [task1, task2]
        minimal_workflow_state["completed_task_ids"] = ["T1"]

        available = get_available_tasks(minimal_workflow_state)
        assert len(available) == 1
        assert available[0]["id"] == "T2"

    def test_excludes_tasks_with_unmet_dependencies(self, minimal_workflow_state):
        """Test excluding tasks with unmet dependencies."""
        task1 = create_task(task_id="T1", title="Task 1")
        task2 = create_task(task_id="T2", title="Task 2", dependencies=["T1"])

        minimal_workflow_state["tasks"] = [task1, task2]

        available = get_available_tasks(minimal_workflow_state)
        assert len(available) == 1
        assert available[0]["id"] == "T1"

    def test_includes_tasks_with_met_dependencies(self, minimal_workflow_state):
        """Test including tasks whose dependencies are complete."""
        task1 = create_task(task_id="T1", title="Task 1")
        task1["status"] = "completed"
        task2 = create_task(task_id="T2", title="Task 2", dependencies=["T1"])

        minimal_workflow_state["tasks"] = [task1, task2]
        minimal_workflow_state["completed_task_ids"] = ["T1"]

        available = get_available_tasks(minimal_workflow_state)
        assert len(available) == 1
        assert available[0]["id"] == "T2"

    def test_returns_empty_when_all_complete(self, minimal_workflow_state):
        """Test returning empty when all tasks complete."""
        task1 = create_task(task_id="T1", title="Task 1")
        task1["status"] = "completed"

        minimal_workflow_state["tasks"] = [task1]
        minimal_workflow_state["completed_task_ids"] = ["T1"]

        available = get_available_tasks(minimal_workflow_state)
        assert len(available) == 0


class TestPhaseState:
    """Tests for PhaseState dataclass."""

    def test_default_values(self):
        """Test default values for PhaseState."""
        phase = PhaseState()

        assert phase.status == PhaseStatus.PENDING
        assert phase.attempts == 0
        assert phase.max_attempts == 3
        assert phase.started_at is None
        assert phase.completed_at is None
        assert phase.error is None
        assert phase.blockers == []
        assert phase.output is None

    def test_custom_values(self):
        """Test PhaseState with custom values."""
        phase = PhaseState(
            status=PhaseStatus.IN_PROGRESS,
            attempts=2,
            max_attempts=5,
            started_at="2026-01-01T00:00:00",
            blockers=["Issue 1"],
        )

        assert phase.status == PhaseStatus.IN_PROGRESS
        assert phase.attempts == 2
        assert phase.max_attempts == 5
        assert phase.started_at == "2026-01-01T00:00:00"
        assert phase.blockers == ["Issue 1"]


class TestPhaseStatus:
    """Tests for PhaseStatus enum."""

    def test_all_statuses_defined(self):
        """Test all expected statuses exist."""
        assert PhaseStatus.PENDING
        assert PhaseStatus.IN_PROGRESS
        assert PhaseStatus.COMPLETED
        assert PhaseStatus.FAILED
        assert PhaseStatus.SKIPPED

    def test_status_values(self):
        """Test status string values."""
        assert PhaseStatus.PENDING.value == "pending"
        assert PhaseStatus.IN_PROGRESS.value == "in_progress"
        assert PhaseStatus.COMPLETED.value == "completed"
        assert PhaseStatus.FAILED.value == "failed"
        assert PhaseStatus.SKIPPED.value == "skipped"


class TestAgentFeedback:
    """Tests for AgentFeedback dataclass."""

    def test_required_fields(self):
        """Test AgentFeedback with required fields."""
        feedback = AgentFeedback(
            agent="cursor",
            approved=True,
            score=8.5,
            assessment="approved",
        )

        assert feedback.agent == "cursor"
        assert feedback.approved is True
        assert feedback.score == 8.5
        assert feedback.assessment == "approved"

    def test_optional_fields_default(self):
        """Test AgentFeedback optional fields have defaults."""
        feedback = AgentFeedback(
            agent="gemini",
            approved=False,
            score=4.0,
            assessment="needs_changes",
        )

        assert feedback.concerns == []
        assert feedback.blocking_issues == []
        assert feedback.summary == ""
        assert feedback.raw_output is None

    def test_to_dict(self, cursor_feedback_approved):
        """Test AgentFeedback to_dict conversion."""
        d = cursor_feedback_approved.to_dict()

        assert d["agent"] == "cursor"
        assert d["approved"] is True
        assert d["score"] == 8.5
        assert "assessment" in d


class TestCreateAgentExecution:
    """Tests for create_agent_execution helper."""

    def test_creates_execution_with_required_fields(self):
        """Test creating execution with required fields."""
        execution = create_agent_execution(
            agent="claude",
            node="planning",
            template_name="planning",
            prompt="Test prompt",
            output="Test output",
            success=True,
            exit_code=0,
            duration_seconds=10.5,
        )

        assert execution["agent"] == "claude"
        assert execution["node"] == "planning"
        assert execution["template_name"] == "planning"
        assert execution["prompt"] == "Test prompt"
        assert execution["output"] == "Test output"
        assert execution["success"] is True
        assert execution["exit_code"] == 0
        assert execution["duration_seconds"] == 10.5
        assert "timestamp" in execution

    def test_creates_execution_with_optional_fields(self):
        """Test creating execution with optional fields."""
        error_ctx = {"error_type": "TestError", "message": "Failed"}
        execution = create_agent_execution(
            agent="cursor",
            node="validation",
            template_name="validation",
            prompt="Review this",
            output="Issues found",
            success=False,
            exit_code=1,
            duration_seconds=5.0,
            model="gpt-4",
            task_id="T1",
            cost_usd=0.05,
            error_context=error_ctx,
        )

        assert execution["model"] == "gpt-4"
        assert execution["task_id"] == "T1"
        assert execution["cost_usd"] == 0.05
        assert execution["error_context"] == error_ctx


class TestCreateErrorContext:
    """Tests for create_error_context helper."""

    def test_creates_error_context_from_exception(self):
        """Test creating error context from exception."""
        try:
            raise ValueError("Test error message")
        except ValueError as e:
            context = create_error_context(
                source_node="test_node",
                exception=e,
                state={},
            )

        assert context["error_type"] == "ValueError"
        assert context["error_message"] == "Test error message"
        assert context["source_node"] == "test_node"
        assert "stack_trace" in context
        assert "timestamp" in context

    def test_creates_error_context_with_recovery_info(self):
        """Test error context with recovery information."""
        try:
            raise TimeoutError("Agent timeout")
        except TimeoutError as e:
            context = create_error_context(
                source_node="implementation",
                exception=e,
                state={"current_phase": 3},
                recoverable=True,
                suggested_actions=["retry", "increase_timeout"],
            )

        assert context["recoverable"] is True
        assert context["suggested_actions"] == ["retry", "increase_timeout"]

    def test_creates_error_context_non_recoverable(self):
        """Test non-recoverable error context."""
        try:
            raise PermissionError("Access denied")
        except PermissionError as e:
            context = create_error_context(
                source_node="file_write",
                exception=e,
                state={},
                recoverable=False,
            )

        assert context["recoverable"] is False


class TestWorkflowStateStructure:
    """Tests for WorkflowState TypedDict structure."""

    def test_state_accepts_all_fields(self, temp_project_dir):
        """Test state accepts all defined fields."""
        state: WorkflowState = {
            "project_name": "test",
            "project_dir": str(temp_project_dir),
            "current_phase": 1,
            "status": "in_progress",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "plan": {"plan_name": "Test"},
            "tasks": [],
            "current_task": None,
            "validation_feedback": {},
            "verification_feedback": {},
            "implementation_result": {},
            "errors": [],
            "phase_status": {},
            "execution_history": [],
            "last_agent_execution": None,
            "error_context": None,
            "next_decision": "continue",
        }

        assert state["project_name"] == "test"
        assert state["current_phase"] == 1

    def test_state_with_feedback(
        self, temp_project_dir, cursor_feedback_approved, gemini_feedback_approved
    ):
        """Test state with agent feedback."""
        state: WorkflowState = create_initial_state(
            project_name="test",
            project_dir=str(temp_project_dir),
        )

        state["validation_feedback"] = {
            "cursor": cursor_feedback_approved,
            "gemini": gemini_feedback_approved,
        }

        assert state["validation_feedback"]["cursor"].score == 8.5
        assert state["validation_feedback"]["gemini"].score == 8.0

    def test_state_with_tasks(self, temp_project_dir, sample_task):
        """Test state with tasks list."""
        state = create_initial_state(
            project_name="test",
            project_dir=str(temp_project_dir),
        )

        state["tasks"] = [sample_task]
        state["current_task"] = sample_task

        assert len(state["tasks"]) == 1
        assert state["current_task"]["id"] == "T1"
