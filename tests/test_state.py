"""Tests for state management.

NOTE: These tests test both the legacy StateManager (file-based) and the
WorkflowStorageAdapter (DB-based) interfaces.
"""


import pytest

from orchestrator.utils.state import PhaseState, PhaseStatus, StateManager, WorkflowState


class TestPhaseState:
    """Tests for PhaseState dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        state = PhaseState(name="planning")
        assert state.name == "planning"
        assert state.status == PhaseStatus.PENDING
        assert state.attempts == 0
        assert state.max_attempts == 3
        assert state.blockers == []
        assert state.approvals == {}

    def test_to_dict(self):
        """Test conversion to dictionary."""
        state = PhaseState(name="planning", status=PhaseStatus.COMPLETED)
        d = state.to_dict()
        assert d["name"] == "planning"
        assert d["status"] == "completed"

    def test_from_dict(self):
        """Test creation from dictionary."""
        d = {
            "name": "validation",
            "status": "in_progress",
            "attempts": 2,
            "max_attempts": 3,
            "blockers": ["blocker1"],
            "approvals": {"cursor": True},
            "outputs": {},
            "started_at": "2024-01-01T00:00:00",
            "completed_at": None,
            "error": None,
        }
        state = PhaseState.from_dict(d)
        assert state.name == "validation"
        assert state.status == PhaseStatus.IN_PROGRESS
        assert state.attempts == 2
        assert state.blockers == ["blocker1"]


class TestWorkflowState:
    """Tests for WorkflowState dataclass."""

    def test_default_phases(self):
        """Test that default phases are created."""
        state = WorkflowState(project_name="test")
        assert len(state.phases) == 5
        assert "planning" in state.phases
        assert "validation" in state.phases
        assert "implementation" in state.phases
        assert "verification" in state.phases
        assert "completion" in state.phases

    def test_to_dict(self):
        """Test conversion to dictionary."""
        state = WorkflowState(project_name="test")
        d = state.to_dict()
        assert d["project_name"] == "test"
        assert "phases" in d
        assert len(d["phases"]) == 5

    def test_from_dict(self):
        """Test creation from dictionary."""
        d = {
            "project_name": "test-project",
            "current_phase": 2,
            "phases": {
                "planning": {
                    "name": "planning",
                    "status": "completed",
                    "attempts": 1,
                    "max_attempts": 3,
                    "blockers": [],
                    "approvals": {},
                    "outputs": {},
                    "started_at": None,
                    "completed_at": None,
                    "error": None,
                },
            },
            "git_commits": [],
            "metadata": {},
        }
        state = WorkflowState.from_dict(d)
        assert state.project_name == "test-project"
        assert state.current_phase == 2
        assert state.phases["planning"].status == PhaseStatus.COMPLETED


class TestStateManager:
    """Tests for StateManager class (legacy file-based state).

    NOTE: These tests use the file-based StateManager directly,
    not the WorkflowStorageAdapter.
    """

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        return project_dir

    @pytest.fixture
    def manager(self, temp_project):
        """Create a StateManager for the temp project."""
        manager = StateManager(temp_project)
        manager.load()
        return manager

    def test_ensure_workflow_dir(self, temp_project):
        """Test workflow directory creation."""
        manager = StateManager(temp_project)
        workflow_dir = manager.ensure_workflow_dir()

        assert workflow_dir.exists()
        assert (workflow_dir / "phases").exists()
        assert (workflow_dir / "phases" / "planning").exists()
        assert (workflow_dir / "phases" / "completion").exists()

    def test_load_creates_new_state(self, temp_project):
        """Test that loading creates new state if none exists."""
        manager = StateManager(temp_project)
        state = manager.load()

        assert state is not None
        assert state.project_name == temp_project.name
        assert state.current_phase == 1

    def test_save_and_load(self, temp_project):
        """Test saving and loading state."""
        manager = StateManager(temp_project)
        manager.load()

        # Modify state
        manager.state.current_phase = 3
        manager.state.phases["planning"].status = PhaseStatus.COMPLETED
        manager.save()

        # Load again
        manager2 = StateManager(temp_project)
        state = manager2.load()

        assert state.current_phase == 3
        assert state.phases["planning"].status == PhaseStatus.COMPLETED

    def test_start_phase(self, manager):
        """Test starting a phase."""
        phase = manager.start_phase(1)

        assert phase.status == PhaseStatus.IN_PROGRESS
        assert phase.started_at is not None
        assert phase.attempts == 1
        assert manager.state.current_phase == 1

    def test_complete_phase(self, manager):
        """Test completing a phase."""
        manager.start_phase(1)
        phase = manager.complete_phase(1, {"result": "success"})

        assert phase.status == PhaseStatus.COMPLETED
        assert phase.completed_at is not None
        assert phase.outputs["result"] == "success"

    def test_fail_phase(self, manager):
        """Test failing a phase."""
        manager.start_phase(1)
        phase = manager.fail_phase(1, "Something went wrong")

        assert phase.status == PhaseStatus.FAILED
        assert phase.error == "Something went wrong"

    def test_can_retry(self, manager):
        """Test retry checking."""
        assert manager.can_retry(1) is True

        # Exhaust retries
        for _ in range(3):
            manager.start_phase(1)

        assert manager.can_retry(1) is False

    def test_reset_phase(self, manager):
        """Test resetting a phase."""
        manager.start_phase(1)
        manager.fail_phase(1, "error")

        phase = manager.reset_phase(1)

        assert phase.status == PhaseStatus.PENDING
        assert phase.error is None
        assert phase.blockers == []
        # Attempts should be preserved
        assert phase.attempts == 1

    def test_record_commit(self, manager):
        """Test recording git commits."""
        manager.record_commit(1, "abc123", "Test commit")

        assert len(manager.state.git_commits) == 1
        assert manager.state.git_commits[0]["hash"] == "abc123"
        assert manager.state.git_commits[0]["phase"] == 1

    def test_get_summary(self, manager):
        """Test getting workflow summary."""
        summary = manager.get_summary()

        assert "project" in summary
        assert "current_phase" in summary
        assert "phase_statuses" in summary
        assert len(summary["phase_statuses"]) == 5
