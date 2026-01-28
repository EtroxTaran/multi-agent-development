"""Regression tests for planning phase routing bugs.

These tests verify fixes for:
1. SpecialistRunner crashing when agents/ directory doesn't exist
2. Validation phase running even when planning failed

Bug Report: Planning showed "failed" but validation proceeded to "in_progress"
Root Cause: Unconditional edges from planning to validation nodes
Fix: Use Send() for conditional parallel dispatch based on planning success
"""


import pytest

from orchestrator.langgraph.state import PhaseState, PhaseStatus, WorkflowState
from orchestrator.langgraph.workflow import create_workflow_graph, planning_send_router
from orchestrator.specialists.runner import SpecialistRunner


class TestSpecialistRunnerMissingAgentsDir:
    """Regression tests for SpecialistRunner handling missing agents directory.

    Bug: SpecialistRunner.get_agent_config() crashed with FileNotFoundError
    when the project's agents/ directory didn't exist.
    """

    def test_has_agents_dir_returns_false_for_nonexistent_directory(self, tmp_path):
        """has_agents_dir() should return False when agents/ doesn't exist.

        This test ensures we don't crash when checking for agents directory.
        """
        # Create a project directory without agents/
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()

        runner = SpecialistRunner(project_dir)

        # Should return False, not raise FileNotFoundError
        assert runner.has_agents_dir() is False

    def test_has_agents_dir_returns_false_for_empty_directory(self, tmp_path):
        """has_agents_dir() should return False when agents/ exists but is empty."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        (project_dir / "agents").mkdir()

        runner = SpecialistRunner(project_dir)

        # Empty directory should return False (no agent subdirs)
        assert runner.has_agents_dir() is False

    def test_has_agents_dir_returns_true_when_agents_exist(self, tmp_path):
        """has_agents_dir() should return True when agents/ has subdirectories."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        agents_dir = project_dir / "agents"
        agents_dir.mkdir()
        (agents_dir / "A01-planner").mkdir()

        runner = SpecialistRunner(project_dir)

        assert runner.has_agents_dir() is True

    def test_get_agent_config_raises_helpful_error_when_no_agents_dir(self, tmp_path):
        """get_agent_config() should raise ValueError with helpful message.

        This test verifies the error message tells users what to do.
        """
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()

        runner = SpecialistRunner(project_dir)

        with pytest.raises(ValueError) as exc_info:
            runner.get_agent_config("A01")

        error_msg = str(exc_info.value)
        assert "Agents directory not found" in error_msg
        assert "agents/" in error_msg.lower()


class TestPlanningRouterConditionalDispatch:
    """Regression tests for conditional routing after planning phase.

    Bug: Validation nodes ran even when planning failed because graph used
    unconditional edges (add_edge) instead of conditional edges.
    """

    def test_planning_send_router_routes_to_error_when_no_plan(self):
        """Router should route to error_dispatch when no plan exists.

        This test verifies validation doesn't run when planning produces no plan.
        """
        state: WorkflowState = {
            "plan": None,
            "phase_status": {},
            "next_decision": None,
            "project_dir": "/tmp/test",
            "project_name": "test",
        }

        result = planning_send_router(state)

        # Should route to error_dispatch, NOT to validators
        assert len(result) == 1
        assert result[0].node == "error_dispatch"

    def test_planning_send_router_routes_to_error_when_plan_invalid(self):
        """Router should route to error_dispatch when plan lacks plan_name."""
        state: WorkflowState = {
            "plan": {"tasks": []},  # Missing plan_name
            "phase_status": {},
            "next_decision": None,
            "project_dir": "/tmp/test",
            "project_name": "test",
        }

        result = planning_send_router(state)

        assert len(result) == 1
        assert result[0].node == "error_dispatch"

    def test_planning_send_router_routes_to_error_when_phase_failed(self):
        """Router should route to error_dispatch when phase status is FAILED.

        This is the specific scenario from the bug report: planning failed
        but validation still started.
        """
        phase_1 = PhaseState(
            status=PhaseStatus.FAILED,
            attempts=7,
            max_attempts=3,
            error="Test error",
        )

        state: WorkflowState = {
            "plan": {"plan_name": "Test", "tasks": []},  # Even with plan
            "phase_status": {"1": phase_1},
            "next_decision": None,
            "project_dir": "/tmp/test",
            "project_name": "test",
        }

        result = planning_send_router(state)

        # Should still route to error because phase is FAILED
        assert len(result) == 1
        assert result[0].node == "error_dispatch"

    def test_planning_send_router_routes_to_error_when_escalate_decision(self):
        """Router should route to error_dispatch when next_decision is escalate."""
        state: WorkflowState = {
            "plan": {"plan_name": "Test", "tasks": []},
            "phase_status": {},
            "next_decision": "escalate",
            "project_dir": "/tmp/test",
            "project_name": "test",
        }

        result = planning_send_router(state)

        assert len(result) == 1
        assert result[0].node == "error_dispatch"

    def test_planning_send_router_dispatches_parallel_when_plan_valid(self):
        """Router should dispatch to BOTH validators when planning succeeds.

        This test verifies the parallel fan-out still works for success case.
        """
        phase_1 = PhaseState(
            status=PhaseStatus.COMPLETED,
            attempts=1,
            max_attempts=3,
        )

        state: WorkflowState = {
            "plan": {"plan_name": "Test Plan", "tasks": [{"id": "t1"}]},
            "phase_status": {"1": phase_1},
            "next_decision": "continue",
            "project_dir": "/tmp/test",
            "project_name": "test",
        }

        result = planning_send_router(state)

        # Should dispatch to BOTH validators in parallel
        assert len(result) == 2
        nodes = {r.node for r in result}
        assert "cursor_validate" in nodes
        assert "gemini_validate" in nodes


class TestWorkflowGraphPlanningEdges:
    """Tests for workflow graph structure after fix."""

    def test_workflow_graph_compiles_with_conditional_planning_edges(self):
        """Workflow graph should compile with conditional planning edges."""
        graph = create_workflow_graph()

        # Verify the graph compiles without error
        assert graph is not None

        drawable = graph.get_graph()
        nodes = set(drawable.nodes)

        # Verify key nodes exist
        assert "planning" in nodes
        assert "cursor_validate" in nodes
        assert "gemini_validate" in nodes
        assert "error_dispatch" in nodes

    def test_planning_node_uses_conditional_edges(self):
        """Planning node should have conditional edges, not multiple unconditional."""
        graph = create_workflow_graph()
        drawable = graph.get_graph()

        # Get edges from planning node
        planning_edges = [e for e in drawable.edges if e[0] == "planning"]

        # With Send(), there should be exactly 1 conditional edge
        # (the conditional edge router handles dispatching to multiple nodes)
        assert len(planning_edges) == 1
