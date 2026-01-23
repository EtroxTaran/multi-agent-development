"""Integration tests for the auto-improvement system.

Tests the full flow from evaluation to optimization to deployment.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEvaluationFlow:
    """Test evaluation node and G-Eval integration."""

    @pytest.mark.asyncio
    async def test_evaluation_node_creates_evaluation(self):
        """Test that evaluate_agent_node creates evaluation for last execution."""
        from orchestrator.langgraph.nodes.evaluate_agent import evaluate_agent_node

        # Mock state with last execution
        state = {
            "project_name": "test-project",
            "project_dir": "/tmp/test",
            "last_agent_execution": {
                "agent": "claude",
                "node": "implement_task",
                "prompt": "Implement the feature",
                "output": "Code implementation here",
                "template_name": "implementation",
            },
            "current_task_id": "T1",
        }

        # Mock the evaluator at the source module where it's defined
        # (local imports inside functions require patching at source)
        with patch("orchestrator.evaluation.AgentEvaluator") as MockEvaluator:
            mock_result = MagicMock()
            mock_result.to_dict.return_value = {
                "overall_score": 8.5,
                "scores": {"task_completion": 9.0},
            }
            mock_result.needs_optimization.return_value = False
            mock_result.is_golden_example.return_value = False

            mock_evaluator = MagicMock()
            mock_evaluator.evaluate = AsyncMock(return_value=mock_result)
            MockEvaluator.return_value = mock_evaluator

            result = await evaluate_agent_node(state)

            assert "last_evaluation" in result
            assert result["last_evaluation"]["overall_score"] == 8.5

    @pytest.mark.asyncio
    async def test_evaluation_queues_optimization_on_low_score(self):
        """Test that low scores trigger optimization queue."""
        from orchestrator.langgraph.nodes.evaluate_agent import evaluate_agent_node

        state = {
            "project_name": "test-project",
            "project_dir": "/tmp/test",
            "last_agent_execution": {
                "agent": "claude",
                "node": "implement_task",
                "prompt": "Implement the feature",
                "output": "Bad implementation",
                "template_name": "implementation",
            },
        }

        # Mock at source modules (local imports require patching at source)
        with patch("orchestrator.evaluation.AgentEvaluator") as MockEvaluator:
            mock_result = MagicMock()
            mock_result.to_dict.return_value = {"overall_score": 5.5}
            mock_result.overall_score = 5.5
            mock_result.needs_optimization.return_value = True
            mock_result.is_golden_example.return_value = False

            mock_evaluator = MagicMock()
            mock_evaluator.evaluate = AsyncMock(return_value=mock_result)
            MockEvaluator.return_value = mock_evaluator

            # Mock scheduler at source module
            with patch("orchestrator.optimization.scheduler.OptimizationScheduler"):
                result = await evaluate_agent_node(state)

                assert "optimization_queue" in result
                assert len(result["optimization_queue"]) > 0
                assert result["optimization_queue"][0]["agent"] == "claude"


class TestOptimizationFlow:
    """Test optimization and deployment integration."""

    @pytest.mark.asyncio
    async def test_optimization_node_runs_optimizer(self):
        """Test that optimize_prompts_node processes queue."""
        from orchestrator.langgraph.nodes.evaluate_agent import optimize_prompts_node

        state = {
            "project_dir": "/tmp/test",
            "project_name": "test-project",
            "optimization_queue": [
                {
                    "agent": "claude",
                    "template_name": "implementation",
                    "reason": "Low score",
                }
            ],
        }

        # Mock at source modules (local imports require patching at source)
        with patch("orchestrator.optimization.PromptOptimizer") as MockOptimizer:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.method = "opro"
            mock_result.expected_improvement = 0.5
            mock_result.source_version = "pv-claude-impl-v1"
            mock_result.error = None

            mock_optimizer = MagicMock()
            mock_optimizer.optimize = AsyncMock(return_value=mock_result)
            MockOptimizer.return_value = mock_optimizer

            # Mock deployer at source module
            with patch("orchestrator.optimization.deployer.DeploymentController") as MockDeployer:
                mock_deploy_result = MagicMock()
                mock_deploy_result.to_dict.return_value = {
                    "success": True,
                    "to_status": "shadow",
                }

                mock_deployer = MagicMock()
                mock_deployer.start_shadow_testing = AsyncMock(return_value=mock_deploy_result)
                MockDeployer.return_value = mock_deployer

                result = await optimize_prompts_node(state)

                assert "optimization_results" in result
                assert len(result["optimization_results"]) == 1
                assert result["optimization_results"][0]["success"] is True
                assert "deployment_results" in result

    @pytest.mark.asyncio
    async def test_optimization_clears_queue(self):
        """Test that processed items are cleared from queue."""
        from orchestrator.langgraph.nodes.evaluate_agent import optimize_prompts_node

        state = {
            "project_dir": "/tmp/test",
            "project_name": "test-project",
            "optimization_queue": [
                {"agent": "claude", "template_name": "impl"},
                {"agent": "cursor", "template_name": "review"},
            ],
        }

        # Mock at source module (local imports require patching at source)
        with patch("orchestrator.optimization.PromptOptimizer") as MockOptimizer:
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.error = "Not enough samples"
            mock_result.method = "none"
            mock_result.expected_improvement = 0
            mock_result.source_version = None

            mock_optimizer = MagicMock()
            mock_optimizer.optimize = AsyncMock(return_value=mock_result)
            MockOptimizer.return_value = mock_optimizer

            result = await optimize_prompts_node(state)

            assert result["optimization_queue"] == []  # Queue cleared


class TestRouterLogic:
    """Test evaluation router decisions."""

    def test_evaluate_router_routes_to_analyze_on_low_score(self):
        """Test router sends low scores to analysis."""
        from orchestrator.langgraph.routers.evaluation import evaluate_agent_router

        state = {"last_evaluation": {"overall_score": 4.5}}

        result = evaluate_agent_router(state)
        assert result == "analyze_output"

    def test_evaluate_router_continues_on_good_score(self):
        """Test router continues workflow on good scores."""
        from orchestrator.langgraph.routers.evaluation import evaluate_agent_router

        state = {"last_evaluation": {"overall_score": 8.0}}

        result = evaluate_agent_router(state)
        assert result == "continue_workflow"

    def test_analyze_router_optimizes_when_queue_exists(self):
        """Test analyze router sends to optimization when queue has items."""
        from orchestrator.langgraph.routers.evaluation import analyze_output_router

        state = {"optimization_queue": [{"agent": "claude"}]}

        result = analyze_output_router(state)
        assert result == "optimize_prompts"

    def test_analyze_router_continues_when_queue_empty(self):
        """Test analyze router continues when no optimization needed."""
        from orchestrator.langgraph.routers.evaluation import analyze_output_router

        state = {"optimization_queue": []}

        result = analyze_output_router(state)
        assert result == "continue_workflow"


class TestGEvalAsync:
    """Test G-Eval async behavior."""

    @pytest.mark.asyncio
    async def test_g_eval_evaluate_is_async(self):
        """Test that G-Eval evaluate method is properly async."""
        from orchestrator.evaluation.g_eval import GEvalEvaluator

        evaluator = GEvalEvaluator(evaluator_model="haiku")

        # Mock subprocess to avoid actual CLI calls
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = '{"score": 7, "reasoning": "Good", "feedback": "OK"}'
            mock_to_thread.return_value = mock_result

            # This should be awaitable
            coro = evaluator.evaluate(
                agent="claude",
                node="test",
                prompt="Test prompt",
                output="Test output",
            )

            # Verify it returns a coroutine
            assert asyncio.iscoroutine(coro)

            # Clean up
            coro.close()


class TestCostControls:
    """Test cost control and sampling features."""

    @pytest.mark.asyncio
    async def test_sampling_skips_evaluations(self):
        """Test that sampling_rate < 1.0 skips some evaluations."""
        from orchestrator.evaluation.evaluator import AgentEvaluator

        evaluator = AgentEvaluator(
            project_dir="/tmp/test",
            sampling_rate=0.0,  # Skip all
            enable_storage=False,
        )

        result = await evaluator.evaluate(
            agent="claude",
            node="test",
            prompt="Test",
            output="Output",
        )

        assert result is None
        assert evaluator._skipped_count >= 1

    @pytest.mark.asyncio
    async def test_force_bypasses_sampling(self):
        """Test that force=True bypasses sampling."""
        from orchestrator.evaluation.evaluator import AgentEvaluator

        evaluator = AgentEvaluator(
            project_dir="/tmp/test",
            sampling_rate=0.0,  # Would skip all
            enable_storage=False,
        )

        with patch.object(evaluator._g_eval, "evaluate") as mock_eval:
            mock_result = MagicMock()
            mock_result.scores = {}
            mock_result.overall_score = 7.0
            mock_result.evaluations = []
            mock_result.suggestions = []
            mock_result.prompt_hash = "abc123"
            mock_result.evaluator_model = "haiku"
            mock_eval.return_value = mock_result

            result = await evaluator.evaluate(
                agent="claude",
                node="test",
                prompt="Test",
                output="Output",
                force=True,
            )

            assert result is not None
            mock_eval.assert_called_once()

    def test_cost_constrained_metric_selection(self):
        """Test that cost limits reduce evaluated metrics."""
        from orchestrator.evaluation.evaluator import AgentEvaluator

        # Very low cost limit
        evaluator = AgentEvaluator(
            project_dir="/tmp/test",
            max_cost_per_eval=0.002,  # Only ~2 criteria
            enable_storage=False,
        )

        metrics = evaluator._select_metrics_for_cost()

        assert metrics is not None
        assert len(metrics) <= 3  # Should select fewer metrics


class TestValidatePrompt:
    """Test prompt validation in optimizer."""

    @pytest.mark.asyncio
    async def test_validate_prompt_uses_golden_examples(self):
        """Test that validation uses golden examples when available."""
        from orchestrator.optimization.optimizer import PromptOptimizer

        optimizer = PromptOptimizer(
            project_dir="/tmp/test",
            project_name="test-project",
        )

        # Mock repositories
        optimizer._golden_repo = MagicMock()
        optimizer._golden_repo.get_by_template = AsyncMock(
            return_value=[
                {"input": "Test input 1", "output": "Test output 1"},
                {"input": "Test input 2", "output": "Test output 2"},
                {"input": "Test input 3", "output": "Test output 3"},
            ]
        )

        optimizer._eval_repo = MagicMock()

        # Mock G-Eval at source module (local imports require patching at source)
        with patch("orchestrator.evaluation.AgentEvaluator") as MockEval:
            mock_g_eval = MagicMock()
            mock_result = MagicMock()
            mock_result.overall_score = 8.0
            mock_g_eval.evaluate_prompt_quality = AsyncMock(return_value=mock_result)

            mock_evaluator = MagicMock()
            mock_evaluator._g_eval = mock_g_eval
            MockEval.return_value = mock_evaluator

            score = await optimizer._validate_prompt(
                agent="claude",
                template_name="implementation",
                prompt="New prompt content",
            )

            # Should use golden examples for validation
            optimizer._golden_repo.get_by_template.assert_called_once()
            assert score is not None

    def test_heuristic_validation_scores_prompt_quality(self):
        """Test heuristic validation for prompts without holdout data."""
        from orchestrator.optimization.optimizer import PromptOptimizer

        optimizer = PromptOptimizer(project_dir="/tmp/test")

        # Good prompt with structure
        good_prompt = """## Instructions
You must complete the task.

## Output Format
Return JSON with the result.

## Example
```json
{"status": "done"}
```
"""

        score = optimizer._heuristic_validate(good_prompt)
        assert score >= 6.0  # Should score reasonably well

        # Bad prompt - too short
        bad_prompt = "Do the thing"
        score = optimizer._heuristic_validate(bad_prompt)
        assert score < 6.0  # Should score poorly


class TestConfiguration:
    """Test configuration loading."""

    def test_config_loads_from_file(self, tmp_path):
        """Test configuration loading from .project-config.json."""
        from orchestrator.evaluation.config import AutoImprovementConfig

        config_file = tmp_path / ".project-config.json"
        config_file.write_text(
            """{
            "auto_improvement": {
                "evaluation": {
                    "enabled": true,
                    "sampling_rate": 0.5
                },
                "optimization": {
                    "optimization_threshold": 6.5
                }
            }
        }"""
        )

        config = AutoImprovementConfig.load(tmp_path)

        assert config.evaluation.sampling_rate == 0.5
        assert config.optimization.optimization_threshold == 6.5

    def test_config_uses_defaults_when_missing(self, tmp_path):
        """Test that defaults are used when config file is missing."""
        from orchestrator.evaluation.config import AutoImprovementConfig

        config = AutoImprovementConfig.load(tmp_path)

        assert config.evaluation.enabled is True
        assert config.evaluation.sampling_rate == 1.0
        assert config.optimization.optimization_threshold == 7.0

    def test_config_caching(self, tmp_path):
        """Test that configuration is cached."""
        from orchestrator.evaluation.config import clear_config_cache, get_config

        clear_config_cache()

        config1 = get_config(tmp_path)
        config2 = get_config(tmp_path)

        assert config1 is config2  # Same object (cached)

        clear_config_cache(tmp_path)
        config3 = get_config(tmp_path)

        assert config1 is not config3  # New object after cache clear


class TestWorkflowIntegration:
    """Test workflow node exports and router exports."""

    def test_evaluation_nodes_exported(self):
        """Test that evaluation nodes are properly exported."""
        from orchestrator.langgraph.nodes import (
            analyze_output_node,
            evaluate_agent_node,
            optimize_prompts_node,
        )

        assert callable(evaluate_agent_node)
        assert callable(analyze_output_node)
        assert callable(optimize_prompts_node)

    def test_evaluation_routers_exported(self):
        """Test that evaluation routers are properly exported."""
        from orchestrator.langgraph.routers import (
            analyze_output_router,
            evaluate_agent_router,
            optimize_prompts_router,
        )

        assert callable(evaluate_agent_router)
        assert callable(analyze_output_router)
        assert callable(optimize_prompts_router)
