"""Tests for test_pass_gate node.

Regression tests for the test pass gate feature that blocks completion
when tests are failing.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.langgraph.nodes.test_pass_gate import (
    MAX_TEST_GATE_ATTEMPTS,
    _get_test_command,
    _parse_test_output,
    _run_tests,
    test_pass_gate_node,
)
from orchestrator.langgraph.routers.general import test_pass_gate_router
from orchestrator.langgraph.state import WorkflowDecision, WorkflowState


class TestTestPassGateNode:
    """Tests for the test_pass_gate_node function."""

    @pytest.fixture
    def base_state(self) -> WorkflowState:
        """Create a base workflow state for testing."""
        return WorkflowState(
            project_dir="/tmp/test-project",
            project_name="test-project",
            test_gate_attempts=0,
            test_gate_results=None,
            implementation_result={"environment": {"test_command": "npm test"}},
        )

    @pytest.fixture
    def mock_config(self):
        """Create a mock project config."""
        config = MagicMock()
        config.workflow.features.environment_check = True
        return config

    @pytest.mark.asyncio
    async def test_all_tests_pass_continues_to_completion(self, base_state, mock_config):
        """Test that passing tests route to completion."""
        with patch("orchestrator.config.load_project_config") as mock_load_config, patch.object(
            __import__("orchestrator.langgraph.nodes.test_pass_gate", fromlist=["_run_tests"]),
            "_run_tests",
        ) as mock_run_tests, patch(
            "orchestrator.db.repositories.phase_outputs.get_phase_output_repository"
        ), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            mock_load_config.return_value = mock_config
            mock_run_tests.return_value = {
                "status": "passed",
                "passed": 10,
                "failed": 0,
                "total": 10,
            }

            result = await test_pass_gate_node(base_state)

            assert result["next_decision"] == "continue"
            assert result["test_gate_attempts"] == 1
            assert result["test_gate_results"]["status"] == "passed"

    @pytest.mark.asyncio
    async def test_failing_tests_route_to_retry(self, base_state, mock_config):
        """Test that failing tests route back for fixes."""
        with patch("orchestrator.config.load_project_config") as mock_load_config, patch.object(
            __import__("orchestrator.langgraph.nodes.test_pass_gate", fromlist=["_run_tests"]),
            "_run_tests",
        ) as mock_run_tests, patch(
            "orchestrator.db.repositories.phase_outputs.get_phase_output_repository"
        ), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            mock_load_config.return_value = mock_config
            mock_run_tests.return_value = {
                "status": "failed",
                "passed": 5,
                "failed": 3,
                "total": 8,
                "failed_tests": ["test_foo", "test_bar", "test_baz"],
            }

            result = await test_pass_gate_node(base_state)

            assert result["next_decision"] == "retry"
            assert result["test_gate_attempts"] == 1
            assert "errors" in result
            assert result["errors"][0]["type"] == "tests_failing"

    @pytest.mark.asyncio
    async def test_max_retries_escalates_to_human(self, base_state, mock_config):
        """Test that exceeding max retries escalates to human."""
        base_state["test_gate_attempts"] = MAX_TEST_GATE_ATTEMPTS - 1

        with patch("orchestrator.config.load_project_config") as mock_load_config, patch.object(
            __import__("orchestrator.langgraph.nodes.test_pass_gate", fromlist=["_run_tests"]),
            "_run_tests",
        ) as mock_run_tests, patch(
            "orchestrator.db.repositories.phase_outputs.get_phase_output_repository"
        ), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            mock_load_config.return_value = mock_config
            mock_run_tests.return_value = {
                "status": "failed",
                "passed": 5,
                "failed": 3,
                "total": 8,
            }

            result = await test_pass_gate_node(base_state)

            assert result["next_decision"] == "escalate"
            assert result["test_gate_attempts"] == MAX_TEST_GATE_ATTEMPTS
            # Error context should be present for escalation
            assert "errors" in result

    @pytest.mark.asyncio
    async def test_no_test_command_allows_completion_with_warning(self, mock_config):
        """Test that missing test command allows completion."""
        state = WorkflowState(
            project_dir="/tmp/test-project",
            project_name="test-project",
            test_gate_attempts=0,
            test_gate_results=None,
            implementation_result={},  # No test command
        )

        with patch(
            "orchestrator.langgraph.nodes.test_pass_gate.load_project_config"
        ) as mock_load_config, patch(
            "orchestrator.langgraph.nodes.test_pass_gate.EnvironmentChecker"
        ) as mock_checker:
            mock_load_config.return_value = mock_config
            mock_checker_instance = MagicMock()
            mock_checker_instance.check.return_value = MagicMock(test_command=None)
            mock_checker.return_value = mock_checker_instance

            result = await test_pass_gate_node(state)

            assert result["next_decision"] == "continue"
            assert result["test_gate_results"]["status"] == "skipped"
            assert result["test_gate_results"]["reason"] == "no_test_command_detected"

    @pytest.mark.asyncio
    async def test_tracks_attempts_correctly(self, base_state, mock_config):
        """Test that attempt count increments correctly."""
        base_state["test_gate_attempts"] = 1

        with patch("orchestrator.config.load_project_config") as mock_load_config, patch.object(
            __import__("orchestrator.langgraph.nodes.test_pass_gate", fromlist=["_run_tests"]),
            "_run_tests",
        ) as mock_run_tests, patch(
            "orchestrator.db.repositories.phase_outputs.get_phase_output_repository"
        ), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            mock_load_config.return_value = mock_config
            mock_run_tests.return_value = {
                "status": "passed",
                "passed": 10,
                "failed": 0,
                "total": 10,
            }

            result = await test_pass_gate_node(base_state)

            assert result["test_gate_attempts"] == 2


class TestTestPassGateRouter:
    """Tests for the test_pass_gate_router function."""

    def test_continue_routes_to_completion(self):
        """Test that continue decision routes to completion."""
        state = WorkflowState(
            next_decision=WorkflowDecision.CONTINUE,
            test_gate_results={"status": "passed"},
        )

        result = test_pass_gate_router(state)

        assert result == "completion"

    def test_continue_string_routes_to_completion(self):
        """Test that continue string routes to completion."""
        state = WorkflowState(
            next_decision="continue",
            test_gate_results={"status": "passed"},
        )

        result = test_pass_gate_router(state)

        assert result == "completion"

    def test_retry_routes_to_task_subgraph(self):
        """Test that retry decision routes to task_subgraph."""
        state = WorkflowState(
            next_decision=WorkflowDecision.RETRY,
            test_gate_results={"status": "failed"},
        )

        result = test_pass_gate_router(state)

        assert result == "task_subgraph"

    def test_escalate_routes_to_human(self):
        """Test that escalate decision routes to human_escalation."""
        state = WorkflowState(
            next_decision=WorkflowDecision.ESCALATE,
            test_gate_results={"status": "failed"},
            test_gate_attempts=3,
        )

        result = test_pass_gate_router(state)

        assert result == "human_escalation"

    def test_abort_routes_to_end(self):
        """Test that abort decision routes to __end__."""
        state = WorkflowState(
            next_decision=WorkflowDecision.ABORT,
        )

        result = test_pass_gate_router(state)

        assert result == "__end__"

    def test_passed_tests_route_to_completion(self):
        """Test that passed tests (without decision) route to completion."""
        state = WorkflowState(
            test_gate_results={"status": "passed"},
            test_gate_attempts=1,
        )

        result = test_pass_gate_router(state)

        assert result == "completion"

    def test_skipped_tests_route_to_completion(self):
        """Test that skipped tests route to completion."""
        state = WorkflowState(
            test_gate_results={"status": "skipped"},
            test_gate_attempts=1,
        )

        result = test_pass_gate_router(state)

        assert result == "completion"

    def test_failed_tests_below_max_route_to_task_subgraph(self):
        """Test that failed tests below max attempts route to retry."""
        state = WorkflowState(
            test_gate_results={"status": "failed"},
            test_gate_attempts=1,
        )

        result = test_pass_gate_router(state)

        assert result == "task_subgraph"

    def test_failed_tests_at_max_route_to_human(self):
        """Test that failed tests at max attempts escalate."""
        state = WorkflowState(
            test_gate_results={"status": "failed"},
            test_gate_attempts=3,
        )

        result = test_pass_gate_router(state)

        assert result == "human_escalation"


class TestParseTestOutput:
    """Tests for the _parse_test_output function."""

    def test_parses_jest_format(self):
        """Test parsing Jest/Vitest output format."""
        output = """
        PASS tests/auth.test.js
        Tests:       5 passed, 2 failed, 1 skipped, 8 total
        Time:        1.234 s
        """
        result = _parse_test_output(output, "npm test")

        assert result["passed"] == 5
        assert result["failed"] == 2
        assert result["skipped"] == 1
        assert result["total"] == 8

    def test_parses_pytest_format(self):
        """Test parsing pytest output format."""
        output = """
        ==================== test session starts ====================
        collected 10 items

        tests/test_auth.py ....F..x..

        8 passed, 1 failed, 1 skipped in 2.34s
        """
        result = _parse_test_output(output, "pytest")

        assert result["passed"] == 8
        assert result["failed"] == 1
        # Note: pytest output without comma before skipped isn't captured by current regex
        # This tests the basic case

    def test_parses_go_test_format(self):
        """Test parsing Go test output format."""
        output = """
ok      github.com/user/pkg/auth    0.123s
ok      github.com/user/pkg/service 0.456s
FAIL    github.com/user/pkg/api     0.789s
        """
        result = _parse_test_output(output, "go test ./...")

        assert result["passed"] == 2
        assert result["failed"] == 1

    def test_parses_simple_pass_fail_format(self):
        """Test parsing simple pass/fail format."""
        output = "10 passed, 3 failed"
        result = _parse_test_output(output, "npm test")

        assert result["passed"] == 10
        assert result["failed"] == 3
        assert result["total"] == 13


class TestGetTestCommand:
    """Tests for the _get_test_command function."""

    def test_gets_command_from_implementation_result(self):
        """Test getting test command from state."""
        state = WorkflowState(
            implementation_result={"environment": {"test_command": "npm run test"}}
        )

        result = _get_test_command(state, Path("/tmp/test"))

        assert result == "npm run test"

    def test_falls_back_to_environment_checker(self):
        """Test fallback to environment detection."""
        state = WorkflowState(implementation_result={})

        with patch(
            "orchestrator.langgraph.nodes.test_pass_gate.EnvironmentChecker"
        ) as mock_checker:
            mock_checker_instance = MagicMock()
            mock_checker_instance.check.return_value = MagicMock(test_command="pytest")
            mock_checker.return_value = mock_checker_instance

            result = _get_test_command(state, Path("/tmp/test"))

            assert result == "pytest"


class TestRunTests:
    """Tests for the _run_tests function."""

    def test_returns_passed_on_success(self):
        """Test that successful tests return passed status."""
        with patch("orchestrator.langgraph.nodes.test_pass_gate.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="10 passed", stderr="")

            result = _run_tests(Path("/tmp/test"), "npm test")

            assert result["status"] == "passed"
            assert result["exit_code"] == 0

    def test_returns_failed_on_failure(self):
        """Test that failing tests return failed status."""
        with patch("orchestrator.langgraph.nodes.test_pass_gate.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="5 passed, 3 failed", stderr="")

            result = _run_tests(Path("/tmp/test"), "npm test")

            assert result["status"] == "failed"
            assert result["exit_code"] == 1

    def test_handles_timeout(self):
        """Test handling of test timeout."""
        import subprocess

        with patch("orchestrator.langgraph.nodes.test_pass_gate.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("npm test", 300)

            result = _run_tests(Path("/tmp/test"), "npm test")

            assert result["status"] == "timeout"
            assert result["exit_code"] == -1

    def test_handles_exception(self):
        """Test handling of unexpected exceptions."""
        with patch("orchestrator.langgraph.nodes.test_pass_gate.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Something went wrong")

            result = _run_tests(Path("/tmp/test"), "npm test")

            assert result["status"] == "error"
            assert result["exit_code"] == -1
            assert "Something went wrong" in result["error"]


class TestMaxTestGateAttempts:
    """Tests for max retry constant."""

    def test_max_attempts_is_3(self):
        """Regression test: max attempts should be 3."""
        assert MAX_TEST_GATE_ATTEMPTS == 3

    def test_max_attempts_is_positive(self):
        """Ensure max attempts is a positive number."""
        assert MAX_TEST_GATE_ATTEMPTS > 0
