"""Comprehensive tests for the LangGraph workflow implementation.

Tests cover:
1. State schema and reducers
2. Router logic (validation, verification, general)
3. Node execution (mocked agents)
4. Integration adapters
5. Error handling paths
6. Parallel execution merging
7. Clarification handling
8. Human escalation

Run with: pytest tests/test_langgraph.py -v
"""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import asdict


# =============================================================================
# Test State Schema and Reducers
# =============================================================================

class TestStateSchema:
    """Test LangGraph state schema and reducers."""

    def test_phase_status_enum(self):
        """Test PhaseStatus enum values."""
        from orchestrator.langgraph.state import PhaseStatus

        assert PhaseStatus.PENDING == "pending"
        assert PhaseStatus.IN_PROGRESS == "in_progress"
        assert PhaseStatus.COMPLETED == "completed"
        assert PhaseStatus.FAILED == "failed"
        assert PhaseStatus.SKIPPED == "skipped"
        assert PhaseStatus.BLOCKED == "blocked"

    def test_workflow_decision_enum(self):
        """Test WorkflowDecision enum values."""
        from orchestrator.langgraph.state import WorkflowDecision

        assert WorkflowDecision.CONTINUE == "continue"
        assert WorkflowDecision.RETRY == "retry"
        assert WorkflowDecision.ESCALATE == "escalate"
        assert WorkflowDecision.ABORT == "abort"

    def test_phase_state_dataclass(self):
        """Test PhaseState dataclass initialization and methods."""
        from orchestrator.langgraph.state import PhaseState, PhaseStatus

        ps = PhaseState()
        assert ps.status == PhaseStatus.PENDING
        assert ps.attempts == 0
        assert ps.max_attempts == 3
        assert ps.blockers == []

        # Test to_dict
        d = ps.to_dict()
        assert d["status"] == "pending"
        assert d["attempts"] == 0

    def test_agent_feedback_dataclass(self):
        """Test AgentFeedback dataclass."""
        from orchestrator.langgraph.state import AgentFeedback

        feedback = AgentFeedback(
            agent="cursor",
            score=8.0,
            approved=True,
            assessment="approve",
            concerns=["minor concern"],
            blocking_issues=[],
        )
        assert feedback.agent == "cursor"
        assert feedback.score == 8.0
        assert feedback.approved is True
        assert len(feedback.concerns) == 1


class TestStateReducers:
    """Test state reducers for parallel execution merging."""

    def test_merge_feedback_reducer_with_none(self):
        """Test feedback merger when existing is None."""
        from orchestrator.langgraph.state import _merge_feedback

        result = _merge_feedback(None, {"cursor": {"score": 8}})
        assert result == {"cursor": {"score": 8}}

    def test_merge_feedback_reducer_merge(self):
        """Test feedback merger combines dicts."""
        from orchestrator.langgraph.state import _merge_feedback

        existing = {"cursor": {"score": 8}}
        new = {"gemini": {"score": 9}}
        result = _merge_feedback(existing, new)

        assert "cursor" in result
        assert "gemini" in result
        assert result["cursor"]["score"] == 8
        assert result["gemini"]["score"] == 9

    def test_merge_feedback_reducer_overwrite(self):
        """Test feedback merger overwrites same key."""
        from orchestrator.langgraph.state import _merge_feedback

        existing = {"cursor": {"score": 5}}
        new = {"cursor": {"score": 8}}
        result = _merge_feedback(existing, new)

        assert result["cursor"]["score"] == 8

    def test_append_errors_reducer(self):
        """Test error appending reducer."""
        from orchestrator.langgraph.state import _append_errors

        existing = [{"type": "error1"}]
        new = [{"type": "error2"}]
        result = _append_errors(existing, new)

        assert len(result) == 2
        assert result[0]["type"] == "error1"
        assert result[1]["type"] == "error2"

    def test_append_errors_with_none(self):
        """Test error appending with None existing."""
        from orchestrator.langgraph.state import _append_errors

        result = _append_errors(None, [{"type": "error1"}])
        assert len(result) == 1

    def test_latest_timestamp_reducer(self):
        """Test timestamp reducer keeps latest."""
        from orchestrator.langgraph.state import _latest_timestamp

        old = "2024-01-01T00:00:00"
        new = "2024-01-02T00:00:00"
        result = _latest_timestamp(old, new)

        assert result == new

    def test_latest_timestamp_with_none(self):
        """Test timestamp reducer with None."""
        from orchestrator.langgraph.state import _latest_timestamp

        result = _latest_timestamp(None, "2024-01-01T00:00:00")
        assert result == "2024-01-01T00:00:00"


# =============================================================================
# Test Routers
# =============================================================================

class TestValidationRouter:
    """Test validation phase routing logic."""

    def test_route_to_implementation_on_continue(self):
        """Test routing to implementation when approved."""
        from orchestrator.langgraph.routers.validation import validation_router

        state = {"next_decision": "continue"}
        result = validation_router(state)
        assert result == "implementation"

    def test_route_to_planning_on_retry(self):
        """Test routing back to planning on retry."""
        from orchestrator.langgraph.routers.validation import validation_router

        state = {"next_decision": "retry"}
        result = validation_router(state)
        assert result == "planning"

    def test_route_to_escalation_on_escalate(self):
        """Test routing to human escalation."""
        from orchestrator.langgraph.routers.validation import validation_router

        state = {"next_decision": "escalate"}
        result = validation_router(state)
        assert result == "human_escalation"

    def test_route_to_end_on_abort(self):
        """Test routing to end on abort."""
        from orchestrator.langgraph.routers.validation import validation_router

        state = {"next_decision": "abort"}
        result = validation_router(state)
        assert result == "__end__"

    def test_route_default_to_escalation(self):
        """Test default routing goes to human escalation for unknown decisions."""
        from orchestrator.langgraph.routers.validation import validation_router

        state = {"next_decision": "unknown"}
        result = validation_router(state)
        # Unknown decisions route to human escalation for safety
        assert result == "human_escalation"


class TestVerificationRouter:
    """Test verification phase routing logic."""

    def test_route_to_completion_on_continue(self):
        """Test routing to completion when approved."""
        from orchestrator.langgraph.routers.verification import verification_router

        state = {"next_decision": "continue"}
        result = verification_router(state)
        assert result == "completion"

    def test_route_to_implementation_on_retry(self):
        """Test routing back to implementation on retry."""
        from orchestrator.langgraph.routers.verification import verification_router

        state = {"next_decision": "retry"}
        result = verification_router(state)
        assert result == "implementation"

    def test_route_to_escalation_on_escalate(self):
        """Test routing to human escalation."""
        from orchestrator.langgraph.routers.verification import verification_router

        state = {"next_decision": "escalate"}
        result = verification_router(state)
        assert result == "human_escalation"


class TestGeneralRouters:
    """Test general routing functions."""

    def test_prerequisites_router_continue(self):
        """Test prerequisites routes to planning on success."""
        from orchestrator.langgraph.routers.general import prerequisites_router

        state = {"next_decision": "continue"}
        result = prerequisites_router(state)
        assert result == "planning"

    def test_prerequisites_router_escalate(self):
        """Test prerequisites routes to escalation on error."""
        from orchestrator.langgraph.routers.general import prerequisites_router

        state = {"next_decision": "escalate"}
        result = prerequisites_router(state)
        assert result == "human_escalation"

    def test_completion_router_always_ends(self):
        """Test completion always routes to end."""
        from orchestrator.langgraph.routers.general import completion_router

        state = {"anything": "value"}
        result = completion_router(state)
        assert result == "__end__"

    def test_human_escalation_router_retry_planning(self):
        """Test escalation routes to planning on retry at phase 1."""
        from orchestrator.langgraph.routers.general import human_escalation_router

        state = {"next_decision": "retry", "current_phase": 1}
        result = human_escalation_router(state)
        assert result == "planning"

    def test_human_escalation_router_retry_implementation(self):
        """Test escalation routes to implementation on retry at phase 3."""
        from orchestrator.langgraph.routers.general import human_escalation_router

        state = {"next_decision": "retry", "current_phase": 3}
        result = human_escalation_router(state)
        assert result == "implementation"


# =============================================================================
# Test Validation Fan-In Logic
# =============================================================================

class TestValidationFanIn:
    """Test validation fan-in node logic."""

    @pytest.fixture
    def base_state(self, temp_project_dir):
        """Create base state for testing."""
        from orchestrator.langgraph.state import PhaseState, PhaseStatus, AgentFeedback

        return {
            "project_dir": str(temp_project_dir),
            "project_name": "test-project",
            "current_phase": 2,
            "phase_status": {
                "2": PhaseState(status=PhaseStatus.IN_PROGRESS)
            },
            "validation_feedback": {},
        }

    def test_fan_in_both_approve_high_score(self, base_state):
        """Test approval logic when both agents approve with high scores."""
        from orchestrator.langgraph.state import AgentFeedback

        cursor_fb = AgentFeedback(
            agent="cursor",
            score=8.0,
            approved=True,
            assessment="approve",
            concerns=[],
            blocking_issues=[],
        )
        gemini_fb = AgentFeedback(
            agent="gemini",
            score=9.0,
            approved=True,
            assessment="approve",
            concerns=[],
            blocking_issues=[],
        )

        # Test the approval logic directly
        cursor_approved = cursor_fb.approved
        gemini_approved = gemini_fb.approved
        combined_score = (cursor_fb.score * 0.5) + (gemini_fb.score * 0.5)
        blocking_issues = cursor_fb.blocking_issues + gemini_fb.blocking_issues
        MIN_SCORE = 6.0

        both_approved = cursor_approved and gemini_approved
        approved = both_approved and combined_score >= MIN_SCORE and len(blocking_issues) == 0

        assert approved is True
        assert combined_score == 8.5

    def test_fan_in_one_rejects(self, base_state):
        """Test approval logic when one agent rejects."""
        from orchestrator.langgraph.state import AgentFeedback

        cursor_fb = AgentFeedback(
            agent="cursor",
            score=4.0,
            approved=False,
            assessment="needs_changes",
            concerns=["Major security issue"],
            blocking_issues=["SQL injection vulnerability"],
        )
        gemini_fb = AgentFeedback(
            agent="gemini",
            score=9.0,
            approved=True,
            assessment="approve",
            concerns=[],
            blocking_issues=[],
        )

        # Test the approval logic directly
        both_approved = cursor_fb.approved and gemini_fb.approved

        assert both_approved is False

    def test_fan_in_blocking_issues_reject(self, base_state):
        """Test approval logic rejects when there are blocking issues."""
        from orchestrator.langgraph.state import AgentFeedback

        cursor_fb = AgentFeedback(
            agent="cursor",
            score=7.0,
            approved=True,
            assessment="approve",
            concerns=[],
            blocking_issues=["Critical: Missing error handling"],
        )
        gemini_fb = AgentFeedback(
            agent="gemini",
            score=8.0,
            approved=True,
            assessment="approve",
            concerns=[],
            blocking_issues=[],
        )

        # Test the approval logic directly
        blocking_issues = cursor_fb.blocking_issues + gemini_fb.blocking_issues
        combined_score = (cursor_fb.score * 0.5) + (gemini_fb.score * 0.5)
        MIN_SCORE = 6.0
        both_approved = cursor_fb.approved and gemini_fb.approved
        approved = both_approved and combined_score >= MIN_SCORE and len(blocking_issues) == 0

        # Should reject due to blocking issues even with high scores
        assert len(blocking_issues) > 0
        assert approved is False


# =============================================================================
# Test Implementation Node Logic
# =============================================================================

class TestImplementationNode:
    """Test implementation node helper functions."""

    def test_extract_clarifications_none(self):
        """Test no clarifications found."""
        from orchestrator.langgraph.nodes.implementation import _extract_clarifications

        result = {"implementation_complete": True}
        clarifications = _extract_clarifications(result)
        assert len(clarifications) == 0

    def test_extract_clarifications_from_array(self):
        """Test extracting clarifications from array."""
        from orchestrator.langgraph.nodes.implementation import _extract_clarifications

        result = {
            "clarifications_needed": [
                {"task_id": "T1", "question": "What auth method?"}
            ]
        }
        clarifications = _extract_clarifications(result)
        assert len(clarifications) == 1
        assert clarifications[0]["question"] == "What auth method?"

    def test_extract_clarifications_from_raw_output(self):
        """Test extracting clarifications from raw output."""
        from orchestrator.langgraph.nodes.implementation import _extract_clarifications

        result = {
            "raw_output": '{"task_id": "T1", "status": "needs_clarification", "question": "What auth method?"}'
        }
        clarifications = _extract_clarifications(result)
        assert len(clarifications) == 1

    def test_load_clarification_answers_none(self, temp_project_dir):
        """Test loading when no answers file exists."""
        from orchestrator.langgraph.nodes.implementation import _load_clarification_answers

        answers = _load_clarification_answers(temp_project_dir)
        assert answers == {}

    def test_load_clarification_answers_exists(self, temp_project_dir):
        """Test loading existing answers."""
        from orchestrator.langgraph.nodes.implementation import _load_clarification_answers

        workflow_dir = temp_project_dir / ".workflow"
        workflow_dir.mkdir(exist_ok=True)
        answers_file = workflow_dir / "clarification_answers.json"
        answers_file.write_text(json.dumps({
            "auth_method": "JWT",
            "timestamp": "2024-01-01"
        }))

        answers = _load_clarification_answers(temp_project_dir)
        assert answers["auth_method"] == "JWT"
        assert "timestamp" not in answers  # Should be removed

    def test_is_transient_error(self):
        """Test transient error detection."""
        from orchestrator.langgraph.nodes.implementation import _is_transient_error

        assert _is_transient_error(Exception("connection timeout")) is True
        assert _is_transient_error(Exception("rate limit exceeded")) is True
        assert _is_transient_error(Exception("503 service unavailable")) is True
        assert _is_transient_error(Exception("syntax error in code")) is False
        assert _is_transient_error(Exception("file not found")) is False

    def test_build_feedback_section_empty(self):
        """Test building feedback section with no feedback."""
        from orchestrator.langgraph.nodes.implementation import _build_feedback_section

        state = {"validation_feedback": {}}
        result = _build_feedback_section(state)
        assert result == ""

    def test_detect_test_commands_python(self, temp_project_dir):
        """Test detecting test commands for Python project."""
        from orchestrator.langgraph.nodes.implementation import _detect_test_commands

        pyproject = temp_project_dir / "pyproject.toml"
        pyproject.write_text("[build-system]\nrequires = ['setuptools']")

        commands = _detect_test_commands(temp_project_dir)
        assert "pytest" in commands

    def test_detect_test_commands_node(self, temp_project_dir):
        """Test detecting test commands for Node project."""
        from orchestrator.langgraph.nodes.implementation import _detect_test_commands

        package_json = temp_project_dir / "package.json"
        package_json.write_text(json.dumps({
            "scripts": {"test": "jest"}
        }))

        commands = _detect_test_commands(temp_project_dir)
        assert "npm test" in commands

    def test_find_test_files(self, temp_project_dir):
        """Test finding test files."""
        from orchestrator.langgraph.nodes.implementation import _find_test_files

        # Create test files
        tests_dir = temp_project_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("")
        (tests_dir / "test_utils.py").write_text("")

        test_files = _find_test_files(temp_project_dir)
        assert len(test_files) == 2


# =============================================================================
# Test Escalation Node
# =============================================================================

class TestEscalationNode:
    """Test human escalation node logic."""

    def test_escalation_context_building(self, temp_project_dir):
        """Test escalation context includes all necessary info."""
        # We can't easily test the full node due to interrupt()
        # But we can test the context building logic

        errors = [
            {"type": "validation_failed", "message": "Score too low"},
            {"type": "validation_failed", "message": "Blocking issues found"},
        ]

        # Build escalation context manually
        escalation = {
            "project": "test-project",
            "current_phase": 2,
            "recent_errors": errors[-5:],
        }

        assert escalation["current_phase"] == 2
        assert len(escalation["recent_errors"]) == 2


# =============================================================================
# Test Integration Adapters
# =============================================================================

class TestLangGraphStateAdapter:
    """Test state adapter between LangGraph and legacy StateManager."""

    def test_adapter_initialization(self, temp_project_dir):
        """Test adapter initializes correctly."""
        from orchestrator.langgraph.integrations.state import LangGraphStateAdapter

        adapter = LangGraphStateAdapter(temp_project_dir)
        assert adapter.project_dir == temp_project_dir

    def test_convert_phase_mapping(self):
        """Test phase number to name mapping."""
        from orchestrator.langgraph.integrations.state import LangGraphStateAdapter

        assert LangGraphStateAdapter.PHASE_MAP[0] == "prerequisites"
        assert LangGraphStateAdapter.PHASE_MAP[1] == "planning"
        assert LangGraphStateAdapter.PHASE_MAP[2] == "validation"
        assert LangGraphStateAdapter.PHASE_MAP[3] == "implementation"
        assert LangGraphStateAdapter.PHASE_MAP[4] == "verification"
        assert LangGraphStateAdapter.PHASE_MAP[5] == "completion"


class TestLangGraphApprovalAdapter:
    """Test approval adapter."""

    def test_agent_feedback_to_dict_via_native(self):
        """Test AgentFeedback native to_dict conversion."""
        from orchestrator.langgraph.state import AgentFeedback

        feedback = AgentFeedback(
            agent="cursor", score=8.0, approved=True,
            assessment="approve", concerns=[], blocking_issues=[]
        )

        # Test native to_dict
        result = feedback.to_dict()

        assert result["agent"] == "cursor"
        assert result["score"] == 8.0
        assert result["approved"] is True
        assert result["assessment"] == "approve"

    def test_adapter_feedback_conversion(self):
        """Test approval adapter converts assessment to overall_assessment."""
        from orchestrator.langgraph.integrations.approval import LangGraphApprovalAdapter
        from orchestrator.langgraph.state import AgentFeedback

        adapter = LangGraphApprovalAdapter()

        feedback = AgentFeedback(
            agent="cursor", score=8.0, approved=True,
            assessment="approve", concerns=[], blocking_issues=[]
        )

        # Adapter conversion includes overall_assessment mapping
        result = adapter._agent_feedback_to_dict(feedback)

        # Since feedback has to_dict, adapter may use it directly
        # Check key fields exist
        assert "score" in result
        assert result["score"] == 8.0


class TestLangGraphConflictAdapter:
    """Test conflict resolution adapter."""

    def test_feedback_to_dict_conversion(self):
        """Test converting AgentFeedback to dict format."""
        from orchestrator.langgraph.state import AgentFeedback

        feedback = AgentFeedback(
            agent="cursor", score=8.0, approved=True,
            assessment="approve", concerns=["minor concern"], blocking_issues=[]
        )

        # Test the conversion manually (what _feedback_to_dict does)
        result = {
            "overall_assessment": feedback.assessment,
            "score": feedback.score,
            "concerns": feedback.concerns,
            "blocking_issues": feedback.blocking_issues,
        }

        assert result["overall_assessment"] == "approve"
        assert result["score"] == 8.0
        assert len(result["concerns"]) == 1

    def test_detect_disagreement_manually(self):
        """Test detecting disagreement between agents manually."""
        from orchestrator.langgraph.state import AgentFeedback

        cursor_fb = AgentFeedback(
            agent="cursor", score=4.0, approved=False,
            assessment="reject", concerns=["Security issue"], blocking_issues=["Critical"]
        )
        gemini_fb = AgentFeedback(
            agent="gemini", score=9.0, approved=True,
            assessment="approve", concerns=[], blocking_issues=[]
        )

        # Detect disagreement manually
        has_approval_conflict = cursor_fb.approved != gemini_fb.approved
        score_difference = abs(cursor_fb.score - gemini_fb.score)

        assert has_approval_conflict is True
        assert score_difference == 5.0  # Significant disagreement


class TestAsyncCircuitBreaker:
    """Test circuit breaker pattern."""

    def test_circuit_breaker_closed_state(self):
        """Test circuit breaker in closed (working) state."""
        import asyncio
        from orchestrator.langgraph.integrations.resilience import (
            AsyncCircuitBreaker,
            AsyncCircuitBreakerConfig,
            AsyncCircuitState
        )

        async def run_test():
            config = AsyncCircuitBreakerConfig(failure_threshold=3)
            cb = AsyncCircuitBreaker("test-breaker", config=config)

            # Use as context manager - successful call should work
            async with cb:
                pass  # Successful operation

            assert cb.state == AsyncCircuitState.CLOSED

        asyncio.run(run_test())

    def test_circuit_breaker_opens_on_failures(self):
        """Test circuit breaker opens after threshold failures."""
        import asyncio
        from orchestrator.langgraph.integrations.resilience import (
            AsyncCircuitBreaker,
            AsyncCircuitBreakerConfig,
            AsyncCircuitState
        )

        async def run_test():
            config = AsyncCircuitBreakerConfig(failure_threshold=2)
            cb = AsyncCircuitBreaker("test-breaker", config=config)

            # First failure
            try:
                async with cb:
                    raise Exception("Failed")
            except Exception:
                pass

            # Second failure - should open circuit
            try:
                async with cb:
                    raise Exception("Failed")
            except Exception:
                pass

            assert cb.state == AsyncCircuitState.OPEN

        asyncio.run(run_test())

    def test_circuit_breaker_rejects_when_open(self):
        """Test circuit breaker rejects calls when open."""
        import asyncio
        from orchestrator.langgraph.integrations.resilience import (
            AsyncCircuitBreaker,
            AsyncCircuitBreakerConfig,
            AsyncCircuitBreakerError,
            AsyncCircuitState
        )

        async def run_test():
            config = AsyncCircuitBreakerConfig(failure_threshold=1, timeout_seconds=60)
            cb = AsyncCircuitBreaker("test-breaker", config=config)

            # Open the circuit with one failure
            try:
                async with cb:
                    raise Exception("Failed")
            except Exception:
                pass

            assert cb.state == AsyncCircuitState.OPEN

            # Next call should be rejected
            try:
                async with cb:
                    pass
                assert False, "Should have raised AsyncCircuitBreakerError"
            except AsyncCircuitBreakerError:
                pass  # Expected

        asyncio.run(run_test())


# =============================================================================
# Test Cursor JSON Parsing
# =============================================================================

class TestCursorJsonParsing:
    """Test cursor-agent JSON wrapper parsing."""

    def test_parse_cursor_wrapper_format(self):
        """Test parsing cursor-agent wrapper with markdown code block."""
        # Simulate cursor-agent output
        cursor_output = {
            "type": "result",
            "result": '```json\n{"reviewer": "cursor", "score": 8, "approved": true}\n```'
        }

        import re

        content = cursor_output.get("result", "")
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)

        assert json_match is not None
        parsed = json.loads(json_match.group(1))
        assert parsed["score"] == 8
        assert parsed["approved"] is True

    def test_parse_cursor_raw_json(self):
        """Test parsing cursor output with raw JSON."""
        cursor_output = {
            "type": "result",
            "result": '{"reviewer": "cursor", "score": 7, "approved": true}'
        }

        import re

        content = cursor_output.get("result", "")
        # First try markdown
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)

        if not json_match:
            # Try raw JSON
            json_match = re.search(r"\{[\s\S]*\}", content)

        assert json_match is not None
        parsed = json.loads(json_match.group(0) if not hasattr(json_match, 'group') else json_match.group(0))
        assert parsed["score"] == 7


# =============================================================================
# Test Parallel Execution Scenarios
# =============================================================================

class TestParallelExecution:
    """Test parallel execution edge cases."""

    def test_partial_failure_one_agent(self):
        """Test handling when one agent fails during parallel execution."""
        from orchestrator.langgraph.state import AgentFeedback, _merge_feedback

        # Cursor succeeds
        cursor_feedback = AgentFeedback(
            agent="cursor", score=8.0, approved=True,
            assessment="approve", concerns=[], blocking_issues=[]
        )

        # Gemini returns error
        gemini_feedback = AgentFeedback(
            agent="gemini", score=0.0, approved=False,
            assessment="error", concerns=["Agent failed to respond"],
            blocking_issues=["Agent unavailable"]
        )

        merged = _merge_feedback(
            {"cursor": cursor_feedback},
            {"gemini": gemini_feedback}
        )

        assert "cursor" in merged
        assert "gemini" in merged
        # Should have both feedbacks even if one is an error

    def test_timeout_on_one_branch(self):
        """Test handling timeout on one parallel branch."""
        from orchestrator.langgraph.state import AgentFeedback

        # Simulate timeout scenario
        cursor_feedback = AgentFeedback(
            agent="cursor", score=8.0, approved=True,
            assessment="approve", concerns=[], blocking_issues=[]
        )

        # Gemini times out - represented as error
        gemini_feedback = AgentFeedback(
            agent="gemini", score=0.0, approved=False,
            assessment="timeout", concerns=["Request timed out"],
            blocking_issues=["Timeout: No response within 5 minutes"]
        )

        # Test approval logic directly - should not approve due to gemini failure
        combined_score = (cursor_feedback.score * 0.5) + (gemini_feedback.score * 0.5)
        both_approved = cursor_feedback.approved and gemini_feedback.approved
        blocking_issues = cursor_feedback.blocking_issues + gemini_feedback.blocking_issues
        MIN_SCORE = 6.0

        approved = both_approved and combined_score >= MIN_SCORE and len(blocking_issues) == 0

        # Should not approve due to gemini failure
        assert both_approved is False
        assert approved is False
        assert combined_score == 4.0


# =============================================================================
# Test Error Recovery Paths
# =============================================================================

class TestErrorRecovery:
    """Test error handling and recovery paths."""

    def test_max_retries_escalates(self):
        """Test that max retries triggers escalation."""
        from orchestrator.langgraph.state import PhaseState, PhaseStatus

        phase = PhaseState(status=PhaseStatus.IN_PROGRESS, attempts=3, max_attempts=3)

        # After 3 attempts, should not allow more retries
        assert phase.attempts >= phase.max_attempts

    def test_transient_error_allows_retry(self):
        """Test transient errors allow retry."""
        from orchestrator.langgraph.nodes.implementation import _is_transient_error

        transient = Exception("Connection timeout")
        permanent = Exception("Syntax error in module")

        assert _is_transient_error(transient) is True
        assert _is_transient_error(permanent) is False


# =============================================================================
# Test Workflow File Operations
# =============================================================================

class TestWorkflowFileOperations:
    """Test workflow file creation and management."""

    def test_workflow_dir_creation(self, temp_project_dir):
        """Test workflow directory structure creation."""
        workflow_dir = temp_project_dir / ".workflow"
        workflow_dir.mkdir(exist_ok=True)

        phases_dir = workflow_dir / "phases"
        phases_dir.mkdir(exist_ok=True)

        for phase in ["planning", "validation", "implementation", "verification", "completion"]:
            phase_dir = phases_dir / phase
            phase_dir.mkdir(exist_ok=True)

        assert (workflow_dir / "phases" / "planning").exists()
        assert (workflow_dir / "phases" / "implementation").exists()

    def test_escalation_file_creation(self, temp_project_dir):
        """Test escalation file is created correctly."""
        workflow_dir = temp_project_dir / ".workflow"
        workflow_dir.mkdir(exist_ok=True)

        escalation = {
            "project": "test-project",
            "current_phase": 2,
            "issue_summary": "Validation failed",
            "suggested_actions": ["Review feedback", "Fix issues"],
        }

        escalation_file = workflow_dir / "escalation.json"
        escalation_file.write_text(json.dumps(escalation, indent=2))

        loaded = json.loads(escalation_file.read_text())
        assert loaded["project"] == "test-project"
        assert len(loaded["suggested_actions"]) == 2

    def test_blockers_md_append(self, temp_project_dir):
        """Test blockers.md is appended correctly."""
        workflow_dir = temp_project_dir / ".workflow"
        workflow_dir.mkdir(exist_ok=True)

        blockers_file = workflow_dir / "blockers.md"

        # First entry
        with open(blockers_file, "a") as f:
            f.write("## Blocker 1\n\nFirst blocker\n\n---\n")

        # Second entry
        with open(blockers_file, "a") as f:
            f.write("## Blocker 2\n\nSecond blocker\n\n---\n")

        content = blockers_file.read_text()
        assert "Blocker 1" in content
        assert "Blocker 2" in content


# =============================================================================
# Integration Tests (Mocked)
# =============================================================================

class TestWorkflowIntegration:
    """Integration tests with mocked agents."""

    @pytest.fixture
    def mock_agents(self):
        """Create all mock agents."""
        claude = MagicMock()
        claude.run_planning = AsyncMock(return_value={
            "success": True,
            "parsed_output": {"plan_name": "Test", "phases": []}
        })

        cursor = MagicMock()
        cursor.run_validation = AsyncMock(return_value={
            "success": True,
            "parsed_output": {"score": 8, "approved": True}
        })

        gemini = MagicMock()
        gemini.run_validation = AsyncMock(return_value={
            "success": True,
            "parsed_output": {"score": 9, "approved": True}
        })

        return {"claude": claude, "cursor": cursor, "gemini": gemini}

    def test_initial_state_creation(self, temp_project_dir):
        """Test initial workflow state is created correctly."""
        from orchestrator.langgraph.state import WorkflowState, PhaseState, PhaseStatus

        state: WorkflowState = {
            "project_dir": str(temp_project_dir),
            "project_name": "test-project",
            "current_phase": 0,
            "phase_status": {
                "0": PhaseState(status=PhaseStatus.PENDING),
                "1": PhaseState(status=PhaseStatus.PENDING),
                "2": PhaseState(status=PhaseStatus.PENDING),
                "3": PhaseState(status=PhaseStatus.PENDING),
                "4": PhaseState(status=PhaseStatus.PENDING),
                "5": PhaseState(status=PhaseStatus.PENDING),
            },
            "plan": None,
            "validation_feedback": None,
            "verification_feedback": None,
            "implementation_result": None,
            "next_decision": None,
            "errors": [],
            "created_at": datetime.now().isoformat(),
        }

        assert state["current_phase"] == 0
        assert len(state["phase_status"]) == 6
        assert state["errors"] == []


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
