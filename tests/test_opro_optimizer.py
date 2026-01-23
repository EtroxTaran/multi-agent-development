"""Tests for the OPRO optimizer."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.optimization.opro import OPROOptimizer, OPROResult
from orchestrator.optimization.bootstrap import BootstrapOptimizer, BootstrapResult
from orchestrator.optimization.optimizer import PromptOptimizer, OptimizationResult


class TestOPROOptimizer:
    """Tests for OPRO-style optimization."""

    def test_truncate(self):
        """Test text truncation."""
        optimizer = OPROOptimizer()
        long_text = "a" * 5000
        truncated = optimizer._truncate(long_text, 1000)
        assert len(truncated) <= 1003  # Plus "..."
        assert truncated.endswith("...")

    def test_truncate_short(self):
        """Test truncation of short text."""
        optimizer = OPROOptimizer()
        short_text = "short"
        truncated = optimizer._truncate(short_text, 1000)
        assert truncated == short_text

    def test_format_examples_high(self):
        """Test formatting high-scoring examples."""
        optimizer = OPROOptimizer()
        examples = [
            {"overall_score": 9.0, "feedback": "Excellent", "suggestions": ["Minor tweak"]},
            {"overall_score": 8.5, "feedback": "Good", "suggestions": []},
        ]
        formatted = optimizer._format_examples(examples, "high")
        assert "Example 1" in formatted
        assert "Score: 9.0" in formatted
        assert "Excellent" in formatted

    def test_format_examples_empty(self):
        """Test formatting empty examples list."""
        optimizer = OPROOptimizer()
        formatted = optimizer._format_examples([], "high")
        assert "No examples available" in formatted

    def test_extract_issues(self):
        """Test issue extraction from low-scoring examples."""
        optimizer = OPROOptimizer()
        examples = [
            {"suggestions": ["fix verbosity", "improve structure"]},
            {"suggestions": ["fix verbosity", "add examples"]},
            {"suggestions": ["fix verbosity"]},
        ]
        issues = optimizer._extract_issues(examples)
        assert "fix verbosity" in issues.lower()
        assert "3 times" in issues or "occurred 3" in issues

    def test_extract_issues_empty(self):
        """Test issue extraction with no suggestions."""
        optimizer = OPROOptimizer()
        examples = [{"suggestions": []}, {}]
        issues = optimizer._extract_issues(examples)
        assert "No specific issues" in issues

    @pytest.mark.asyncio
    async def test_optimize_no_history(self):
        """Test optimization with no evaluation history."""
        optimizer = OPROOptimizer()
        result = await optimizer.optimize(
            template_name="test",
            current_prompt="Test prompt",
            evaluation_history=[],
        )
        assert not result.success
        assert "No evaluation history" in result.error

    @pytest.mark.asyncio
    async def test_optimize_with_mock_llm(self):
        """Test optimization with mocked LLM call."""
        optimizer = OPROOptimizer()

        # Mock the LLM call - return a string longer than 100 chars
        long_prompt = "Improved prompt content that is sufficiently long to pass the validation check requiring at least 100 characters in the response."
        with patch.object(optimizer, '_call_optimizer', return_value=long_prompt):
            result = await optimizer.optimize(
                template_name="test",
                current_prompt="Original prompt",
                evaluation_history=[
                    {"overall_score": 9.0, "feedback": "Great", "suggestions": []},
                    {"overall_score": 8.5, "feedback": "Good", "suggestions": []},
                    {"overall_score": 4.0, "feedback": "Poor", "suggestions": ["improve"]},
                ],
            )

            assert result.success
            assert result.new_prompt is not None
            assert len(result.new_prompt) > 100


class TestBootstrapOptimizer:
    """Tests for bootstrap optimization."""

    def test_truncate(self):
        """Test text truncation."""
        optimizer = BootstrapOptimizer()
        long_text = "a" * 5000
        truncated = optimizer._truncate(long_text, 1000)
        assert len(truncated) <= 1003
        assert truncated.endswith("...")

    def test_format_golden_examples(self):
        """Test formatting golden examples."""
        optimizer = BootstrapOptimizer()
        examples = [
            {
                "score": 9.5,
                "input_prompt": "Test input",
                "output": "Test output",
            },
        ]
        formatted = optimizer._format_golden_examples(examples)
        assert "Example 1" in formatted
        assert "Score: 9.5" in formatted
        assert "Test input" in formatted
        assert "Test output" in formatted


class TestPromptOptimizer:
    """Tests for the main prompt optimizer."""

    def test_get_avg_score(self):
        """Test average score calculation."""
        optimizer = PromptOptimizer(project_name="test")
        evaluations = [
            {"overall_score": 8.0},
            {"overall_score": 7.0},
            {"overall_score": 9.0},
        ]
        avg = optimizer._get_avg_score(evaluations)
        assert avg == 8.0

    def test_get_avg_score_empty(self):
        """Test average score with empty list."""
        optimizer = PromptOptimizer(project_name="test")
        avg = optimizer._get_avg_score([])
        assert avg == 5.0  # Default


class TestOPROResult:
    """Tests for OPRO result."""

    def test_success_result(self):
        """Test successful result."""
        result = OPROResult(
            success=True,
            new_prompt="Improved prompt",
            examples_used=5,
        )
        assert result.success
        assert result.new_prompt == "Improved prompt"
        assert result.examples_used == 5

    def test_failure_result(self):
        """Test failure result."""
        result = OPROResult(
            success=False,
            error="No data",
        )
        assert not result.success
        assert result.error == "No data"
        assert result.new_prompt is None


class TestBootstrapResult:
    """Tests for bootstrap result."""

    def test_success_result(self):
        """Test successful result."""
        result = BootstrapResult(
            success=True,
            new_prompt="Prompt with examples",
            examples_used=3,
        )
        assert result.success
        assert result.examples_used == 3


class TestOptimizationResult:
    """Tests for optimization result."""

    def test_to_dict(self):
        """Test serialization."""
        result = OptimizationResult(
            success=True,
            new_prompt="New prompt",
            source_version="v1",
            expected_improvement=0.5,
            method="opro",
            samples_used=10,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["method"] == "opro"
        assert d["samples_used"] == 10

    def test_to_dict_truncates_prompt(self):
        """Test that long prompts are truncated in dict."""
        result = OptimizationResult(
            success=True,
            new_prompt="a" * 1000,
            method="opro",
        )
        d = result.to_dict()
        assert len(d["new_prompt"]) == 500
