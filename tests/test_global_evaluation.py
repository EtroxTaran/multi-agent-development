"""Tests for global agent evaluation.

Verifies that ALL agent executions are tracked and evaluated
with template-specific criteria.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.langgraph.nodes.evaluate_agent import (
    TEMPLATE_CRITERIA,
    _get_template_requirements,
    evaluate_agent_node,
    get_template_criteria,
)
from orchestrator.langgraph.state import create_agent_execution, create_initial_state


@pytest.fixture
def initial_state():
    """Create initial workflow state for tests."""
    return create_initial_state(
        project_dir="/tmp/test-project",
        project_name="test-project",
    )


class TestTemplateCriteria:
    """Tests for template-specific evaluation criteria."""

    def test_all_templates_have_criteria(self):
        """Test all 9 template types have defined criteria."""
        expected_templates = [
            "planning",
            "validation",
            "code_review",
            "architecture_review",
            "task_implementation",
            "test_writing",
            "bug_fix",
            "fixer_diagnose",
            "fixer_apply",
        ]

        for template in expected_templates:
            assert template in TEMPLATE_CRITERIA, f"Missing criteria for {template}"
            criteria = TEMPLATE_CRITERIA[template]
            assert isinstance(criteria, dict), f"{template} criteria not a dict"
            assert len(criteria) > 0, f"{template} has no criteria"

    def test_criteria_weights_sum_to_one(self):
        """Test criteria weights sum to approximately 1.0."""
        for template, criteria in TEMPLATE_CRITERIA.items():
            total = sum(criteria.values())
            assert 0.99 <= total <= 1.01, f"{template} weights sum to {total}, not 1.0"

    def test_get_template_criteria_known(self):
        """Test getting criteria for known template."""
        criteria = get_template_criteria("planning")
        assert "completeness" in criteria
        assert "task_clarity" in criteria

    def test_get_template_criteria_unknown(self):
        """Test getting criteria for unknown template returns default."""
        criteria = get_template_criteria("nonexistent_template")
        assert criteria == TEMPLATE_CRITERIA["default"]


class TestTemplateRequirements:
    """Tests for template-specific requirements."""

    def test_planning_requirements(self, initial_state):
        """Test planning template has specific requirements."""
        reqs = _get_template_requirements(initial_state, "planning")

        assert any("valid JSON" in r for r in reqs)
        assert any("tasks" in r for r in reqs)

    def test_validation_requirements(self, initial_state):
        """Test validation template has score requirements."""
        reqs = _get_template_requirements(initial_state, "validation")

        assert any("score" in r.lower() for r in reqs)
        assert any("severity" in r.lower() for r in reqs)

    def test_code_review_requirements(self, initial_state):
        """Test code review template has security requirements."""
        reqs = _get_template_requirements(initial_state, "code_review")

        assert any("OWASP" in r for r in reqs)
        assert any("security" in r.lower() for r in reqs)

    def test_task_implementation_requirements(self, initial_state):
        """Test task implementation has TDD requirements."""
        reqs = _get_template_requirements(initial_state, "task_implementation")

        assert any("TDD" in r for r in reqs)
        assert any("acceptance criteria" in r.lower() for r in reqs)

    def test_unknown_template_uses_generic_requirements(self, initial_state):
        """Test unknown template gets generic requirements only."""
        reqs = _get_template_requirements(initial_state, "nonexistent")

        # Should only have generic requirements (from _get_requirements)
        # No template-specific ones
        assert not any("TDD" in r for r in reqs)
        assert not any("OWASP" in r for r in reqs)


class TestEvaluateAgentNode:
    """Tests for evaluate_agent_node."""

    @pytest.mark.asyncio
    async def test_skips_when_no_execution(self, initial_state):
        """Test node skips when no last_agent_execution."""
        result = await evaluate_agent_node(initial_state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_skips_failed_execution(self, initial_state):
        """Test node skips evaluation for failed executions."""
        initial_state["last_agent_execution"] = create_agent_execution(
            agent="claude",
            node="planning",
            template_name="planning",
            prompt="Test",
            output="Error",
            success=False,  # Failed execution
        )

        result = await evaluate_agent_node(initial_state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_evaluates_successful_execution(self, initial_state):
        """Test node evaluates successful execution."""
        initial_state["last_agent_execution"] = create_agent_execution(
            agent="claude",
            node="planning",
            template_name="planning",
            prompt="Create implementation plan",
            output='{"tasks": [{"id": "T1", "title": "Test"}]}',
            success=True,
        )

        # Patch at the module where AgentEvaluator is imported
        with patch("orchestrator.evaluation.AgentEvaluator") as mock_eval:
            mock_instance = MagicMock()
            mock_eval.return_value = mock_instance

            # Mock evaluation result
            mock_result = MagicMock()
            mock_result.to_dict.return_value = {"score": 7.5}
            mock_result.needs_optimization.return_value = False
            mock_result.is_golden_example.return_value = False
            mock_instance.evaluate = AsyncMock(return_value=mock_result)

            result = await evaluate_agent_node(initial_state)

            # Should have called evaluator
            mock_instance.evaluate.assert_called_once()

            # Should have evaluation result
            assert "last_evaluation" in result

    @pytest.mark.asyncio
    async def test_queues_optimization_for_low_score(self, initial_state):
        """Test node queues optimization when score is low."""
        initial_state["last_agent_execution"] = create_agent_execution(
            agent="claude",
            node="planning",
            template_name="planning",
            prompt="Test",
            output="Bad output",
            success=True,
        )

        # Patch at the module where AgentEvaluator is imported
        with patch("orchestrator.evaluation.AgentEvaluator") as mock_eval:
            mock_instance = MagicMock()
            mock_eval.return_value = mock_instance

            # Mock low score evaluation
            mock_result = MagicMock()
            mock_result.to_dict.return_value = {"score": 4.0}
            mock_result.needs_optimization.return_value = True  # Score below threshold
            mock_result.is_golden_example.return_value = False
            mock_result.overall_score = 4.0
            mock_instance.evaluate = AsyncMock(return_value=mock_result)

            # Mock scheduler
            with patch("orchestrator.optimization.scheduler.OptimizationScheduler"):
                result = await evaluate_agent_node(initial_state)

            # Should have queued optimization
            assert "optimization_queue" in result
            assert len(result["optimization_queue"]) == 1
            assert result["optimization_queue"][0]["template_name"] == "planning"


class TestAgentExecutionTracking:
    """Tests for agent execution tracking."""

    def test_create_agent_execution_structure(self):
        """Test AgentExecution has all required fields."""
        execution = create_agent_execution(
            agent="claude",
            node="planning",
            template_name="planning",
            prompt="Test prompt",
            output="Test output",
            success=True,
            exit_code=0,
            duration_seconds=1.5,
            cost_usd=0.05,
            model="sonnet",
            task_id="T1",
        )

        assert execution["agent"] == "claude"
        assert execution["node"] == "planning"
        assert execution["template_name"] == "planning"
        assert execution["success"] is True
        assert execution["task_id"] == "T1"
        assert "execution_id" in execution
        assert "timestamp" in execution

    def test_execution_truncates_long_prompt(self):
        """Test execution truncates long prompts."""
        long_prompt = "x" * 20000  # Exceeds MAX_PROMPT_LENGTH

        execution = create_agent_execution(
            agent="claude",
            node="planning",
            template_name="planning",
            prompt=long_prompt,
            output="",
        )

        assert len(execution["prompt"]) <= 10000

    def test_execution_truncates_long_output(self):
        """Test execution truncates long outputs."""
        long_output = "y" * 30000  # Exceeds MAX_OUTPUT_LENGTH

        execution = create_agent_execution(
            agent="claude",
            node="planning",
            template_name="planning",
            prompt="",
            output=long_output,
        )

        assert len(execution["output"]) <= 20000

    def test_execution_includes_error_context(self):
        """Test execution can include error context."""
        from orchestrator.langgraph.state import create_error_context

        error_ctx = create_error_context(
            source_node="planning",
            exception=ValueError("Test"),
        )

        execution = create_agent_execution(
            agent="claude",
            node="planning",
            template_name="planning",
            prompt="",
            output="",
            success=False,
            error_context=error_ctx,
        )

        assert execution["error_context"] is not None
        assert execution["error_context"]["error_type"] == "ValueError"


class TestAllTemplatesEvaluated:
    """Tests to verify all 9 template types can be evaluated."""

    @pytest.mark.parametrize(
        "template_name,agent",
        [
            ("planning", "claude"),
            ("validation", "cursor"),
            ("validation", "gemini"),
            ("code_review", "cursor"),
            ("architecture_review", "gemini"),
            ("task_implementation", "claude"),
            ("test_writing", "claude"),
            ("bug_fix", "claude"),
            ("fixer_diagnose", "claude"),
            ("fixer_apply", "claude"),
        ],
    )
    def test_template_has_criteria(self, template_name, agent):
        """Test each template type has evaluation criteria."""
        criteria = get_template_criteria(template_name)
        assert len(criteria) > 0, f"No criteria for {template_name}"

    @pytest.mark.parametrize(
        "template_name",
        [
            "planning",
            "validation",
            "code_review",
            "architecture_review",
            "task_implementation",
            "test_writing",
            "bug_fix",
            "fixer_diagnose",
            "fixer_apply",
        ],
    )
    def test_template_has_requirements(self, template_name, initial_state):
        """Test each template type has specific requirements."""
        reqs = _get_template_requirements(initial_state, template_name)

        # Each template should add its own requirements
        assert len(reqs) > 0, f"No requirements for {template_name}"
