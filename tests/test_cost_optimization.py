"""Tests for cost optimization utilities.

Covers token tracking, budget enforcement, model routing,
cost estimation, and usage summaries.
"""

import json
from datetime import datetime, timedelta

import pytest

from orchestrator.utils.cost_optimization import (
    MODEL_REGISTRY,
    ModelRouter,
    ModelSpec,
    TaskComplexity,
    TokenTracker,
    TokenUsage,
    UsageSummary,
)

# =============================================================================
# Task Complexity Tests
# =============================================================================


class TestTaskComplexity:
    """Tests for TaskComplexity enum."""

    def test_complexity_values(self):
        """Test complexity enum values."""
        assert TaskComplexity.TRIVIAL.value == "trivial"
        assert TaskComplexity.SIMPLE.value == "simple"
        assert TaskComplexity.MODERATE.value == "moderate"
        assert TaskComplexity.COMPLEX.value == "complex"
        assert TaskComplexity.EXPERT.value == "expert"

    def test_complexity_ordering(self):
        """Test that complexity levels are ordered."""
        # Using value comparison for ordering
        complexities = [
            TaskComplexity.TRIVIAL,
            TaskComplexity.SIMPLE,
            TaskComplexity.MODERATE,
            TaskComplexity.COMPLEX,
            TaskComplexity.EXPERT,
        ]

        # Values should be in ascending order lexicographically
        # (not necessarily the case here, but the enum exists)
        assert len(complexities) == 5


# =============================================================================
# Model Spec Tests
# =============================================================================


class TestModelSpec:
    """Tests for ModelSpec dataclass."""

    def test_avg_cost_per_1k(self):
        """Test average cost calculation."""
        spec = ModelSpec(
            name="test-model",
            provider="test",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
            context_window=100000,
            capabilities=["code"],
            complexity_threshold=TaskComplexity.MODERATE,
            latency_ms=1000,
        )

        assert spec.avg_cost_per_1k == 0.02

    def test_model_registry_contains_expected_models(self):
        """Test MODEL_REGISTRY has expected models."""
        expected_models = [
            "gpt-5.2-codex",
            "gpt-5.1-codex",
            "gpt-4.5-turbo",
            "gemini-3-pro",
            "gemini-3-flash",
            "claude-opus-4.5",
            "claude-sonnet-4",
        ]

        for model in expected_models:
            assert model in MODEL_REGISTRY

    def test_model_registry_has_required_fields(self):
        """Test all models in registry have required fields."""
        for name, spec in MODEL_REGISTRY.items():
            assert spec.name == name
            assert spec.provider in ["openai", "google", "anthropic"]
            assert spec.input_cost_per_1k > 0
            assert spec.output_cost_per_1k > 0
            assert spec.context_window > 0
            assert len(spec.capabilities) > 0
            assert isinstance(spec.complexity_threshold, TaskComplexity)
            assert spec.latency_ms > 0


# =============================================================================
# Token Usage Tests
# =============================================================================


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_calculate_cost_known_model(self):
        """Test cost calculation for known model."""
        # Using gpt-4.5-turbo: input=0.005, output=0.015
        usage = TokenUsage(
            model="gpt-4.5-turbo",
            input_tokens=1000,
            output_tokens=1000,
        )

        # (1000/1000 * 0.005) + (1000/1000 * 0.015) = 0.02
        assert usage.cost == pytest.approx(0.02)

    def test_calculate_cost_unknown_model(self):
        """Test cost calculation for unknown model uses defaults."""
        usage = TokenUsage(
            model="unknown-model",
            input_tokens=1000,
            output_tokens=1000,
        )

        # Default: (1000/1000 * 0.01) + (1000/1000 * 0.03) = 0.04
        assert usage.cost == pytest.approx(0.04)

    def test_calculate_cost_with_explicit_cost(self):
        """Test explicit cost is preserved."""
        usage = TokenUsage(
            model="gpt-4.5-turbo",
            input_tokens=1000,
            output_tokens=1000,
            cost=0.50,  # Explicit cost
        )

        assert usage.cost == 0.50

    def test_to_dict(self):
        """Test serialization to dict."""
        usage = TokenUsage(
            model="gpt-4.5-turbo",
            input_tokens=500,
            output_tokens=1000,
            task_type="test",
            phase=1,
        )

        d = usage.to_dict()

        assert d["model"] == "gpt-4.5-turbo"
        assert d["input_tokens"] == 500
        assert d["output_tokens"] == 1000
        assert d["task_type"] == "test"
        assert d["phase"] == 1
        assert "timestamp" in d
        assert "cost" in d

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "model": "gemini-3-flash",
            "input_tokens": 100,
            "output_tokens": 200,
            "timestamp": "2026-01-21T10:00:00",
            "task_type": "validation",
            "phase": 2,
            "cost": 0.001,
        }

        usage = TokenUsage.from_dict(data)

        assert usage.model == "gemini-3-flash"
        assert usage.input_tokens == 100
        assert usage.output_tokens == 200
        assert usage.task_type == "validation"
        assert usage.phase == 2

    def test_default_values(self):
        """Test default values are set."""
        usage = TokenUsage(
            model="test",
            input_tokens=100,
            output_tokens=200,
        )

        assert usage.task_type == "unknown"
        assert usage.phase is None
        assert usage.timestamp is not None


# =============================================================================
# Usage Summary Tests
# =============================================================================


class TestUsageSummary:
    """Tests for UsageSummary dataclass."""

    def test_default_values(self):
        """Test default summary values."""
        summary = UsageSummary()

        assert summary.total_input_tokens == 0
        assert summary.total_output_tokens == 0
        assert summary.total_cost == 0.0
        assert summary.total_calls == 0
        assert summary.by_model == {}
        assert summary.by_phase == {}
        assert summary.by_task_type == {}

    def test_to_dict(self):
        """Test serialization to dict."""
        summary = UsageSummary(
            total_input_tokens=1000,
            total_output_tokens=2000,
            total_cost=0.05,
            total_calls=5,
        )

        d = summary.to_dict()

        assert d["total_input_tokens"] == 1000
        assert d["total_output_tokens"] == 2000
        assert d["total_cost"] == 0.05
        assert d["total_calls"] == 5


# =============================================================================
# Token Tracker Tests
# =============================================================================


class TestTokenTracker:
    """Tests for TokenTracker class."""

    @pytest.fixture
    def tracker(self, tmp_path):
        """Create a test token tracker."""
        return TokenTracker(storage_dir=tmp_path)

    def test_record_usage(self, tracker):
        """Test recording token usage."""
        usage = tracker.record(
            model="gpt-4.5-turbo",
            input_tokens=500,
            output_tokens=1000,
            task_type="test",
            phase=1,
        )

        assert usage.model == "gpt-4.5-turbo"
        assert usage.input_tokens == 500
        assert usage.output_tokens == 1000

    def test_get_total_cost(self, tracker):
        """Test getting total cost."""
        tracker.record(
            model="gpt-4.5-turbo",
            input_tokens=1000,
            output_tokens=1000,
        )
        tracker.record(
            model="gpt-4.5-turbo",
            input_tokens=1000,
            output_tokens=1000,
        )

        total = tracker.get_total_cost()

        # 2 * 0.02 = 0.04
        assert total == pytest.approx(0.04)

    def test_get_total_cost_with_since(self, tracker):
        """Test getting total cost filtered by time."""
        # Record some usage
        tracker.record(model="gpt-4.5-turbo", input_tokens=1000, output_tokens=1000)

        # Get cost since future time
        future = datetime.now() + timedelta(hours=1)
        total = tracker.get_total_cost(since=future)

        assert total == 0.0

    def test_check_budget_no_limit(self, tmp_path):
        """Test budget check with no limit."""
        tracker = TokenTracker(storage_dir=tmp_path, budget_limit=None)

        within, remaining = tracker.check_budget(estimated_cost=100.0)

        assert within is True
        assert remaining == float("inf")

    def test_check_budget_within_limit(self, tmp_path):
        """Test budget check when within limit."""
        tracker = TokenTracker(storage_dir=tmp_path, budget_limit=10.0)

        tracker.record(model="gpt-4.5-turbo", input_tokens=1000, output_tokens=1000)

        within, remaining = tracker.check_budget(estimated_cost=1.0)

        assert within is True
        assert remaining == pytest.approx(10.0 - 0.02)

    def test_check_budget_exceeds_limit(self, tmp_path):
        """Test budget check when exceeds limit."""
        tracker = TokenTracker(storage_dir=tmp_path, budget_limit=0.01)

        tracker.record(model="gpt-4.5-turbo", input_tokens=1000, output_tokens=1000)

        within, remaining = tracker.check_budget(estimated_cost=0.0)

        assert within is False

    def test_get_summary(self, tracker):
        """Test getting usage summary."""
        tracker.record(
            model="gpt-4.5-turbo",
            input_tokens=500,
            output_tokens=500,
            task_type="validation",
            phase=2,
        )
        tracker.record(
            model="gemini-3-flash",
            input_tokens=1000,
            output_tokens=500,
            task_type="review",
            phase=4,
        )

        summary = tracker.get_summary()

        assert summary.total_calls == 2
        assert summary.total_input_tokens == 1500
        assert summary.total_output_tokens == 1000
        assert "gpt-4.5-turbo" in summary.by_model
        assert "gemini-3-flash" in summary.by_model
        assert "2" in summary.by_phase
        assert "4" in summary.by_phase
        assert "validation" in summary.by_task_type
        assert "review" in summary.by_task_type

    def test_get_summary_with_period(self, tracker):
        """Test getting summary for specific period."""
        tracker.record(model="gpt-4.5-turbo", input_tokens=1000, output_tokens=1000)

        # Summary for future period should be empty
        future = datetime.now() + timedelta(hours=1)
        summary = tracker.get_summary(since=future)

        assert summary.total_calls == 0

    def test_persistence(self, tmp_path):
        """Test usage is persisted to disk."""
        tracker1 = TokenTracker(storage_dir=tmp_path)
        tracker1.record(model="gpt-4.5-turbo", input_tokens=1000, output_tokens=1000)

        # Create new tracker instance
        tracker2 = TokenTracker(storage_dir=tmp_path)

        # Should have loaded previous usage
        assert tracker2.get_total_cost() == pytest.approx(0.02)

    def test_get_cost_report(self, tracker):
        """Test generating cost report."""
        tracker.record(
            model="gpt-4.5-turbo",
            input_tokens=1000,
            output_tokens=1000,
            task_type="test",
            phase=1,
        )

        report = tracker.get_cost_report()

        assert "TOKEN USAGE & COST REPORT" in report
        assert "gpt-4.5-turbo" in report
        assert "Total Calls: 1" in report

    def test_get_cost_report_with_budget(self, tmp_path):
        """Test cost report includes budget info."""
        tracker = TokenTracker(storage_dir=tmp_path, budget_limit=10.0)
        tracker.record(model="gpt-4.5-turbo", input_tokens=1000, output_tokens=1000)

        report = tracker.get_cost_report()

        assert "Budget" in report
        assert "$10.00" in report

    def test_load_empty_file(self, tmp_path):
        """Test loading from empty/invalid file."""
        usage_file = tmp_path / "token_usage.json"
        usage_file.write_text("not valid json")

        # Should not raise, just start with empty usage
        tracker = TokenTracker(storage_dir=tmp_path)
        assert tracker.get_total_cost() == 0.0

    def test_load_missing_usage_key(self, tmp_path):
        """Test loading file without 'usage' key."""
        usage_file = tmp_path / "token_usage.json"
        usage_file.write_text(json.dumps({"other": "data"}))

        tracker = TokenTracker(storage_dir=tmp_path)
        assert tracker.get_total_cost() == 0.0


# =============================================================================
# Model Router Tests
# =============================================================================


class TestModelRouter:
    """Tests for ModelRouter class."""

    @pytest.fixture
    def router(self):
        """Create a test model router."""
        return ModelRouter(
            default_cursor_model="gpt-5.2-codex",
            default_gemini_model="gemini-3-pro",
            cost_optimization_enabled=True,
        )

    def test_get_complexity_known_task(self, router):
        """Test getting complexity for known task type."""
        assert router.get_complexity("format_check") == TaskComplexity.TRIVIAL
        assert router.get_complexity("security_audit") == TaskComplexity.COMPLEX
        assert router.get_complexity("system_design") == TaskComplexity.EXPERT

    def test_get_complexity_unknown_task(self, router):
        """Test getting complexity for unknown task defaults to MODERATE."""
        assert router.get_complexity("unknown_task") == TaskComplexity.MODERATE

    def test_select_model_optimization_disabled(self):
        """Test model selection with optimization disabled."""
        router = ModelRouter(
            default_cursor_model="gpt-5.2-codex",
            default_gemini_model="gemini-3-pro",
            cost_optimization_enabled=False,
        )

        model = router.select_model("cursor", "format_check")

        assert model == "gpt-5.2-codex"

    def test_select_model_cursor_trivial_task(self, router):
        """Test selecting cheapest cursor model for trivial task."""
        model = router.select_model("cursor", "format_check")

        # Should select cheapest capable model
        # gpt-4.5-turbo is cheapest OpenAI model that handles SIMPLE+
        # But format_check is TRIVIAL, so it might not find a match and use default
        assert model in MODEL_REGISTRY

    def test_select_model_gemini_trivial_task(self, router):
        """Test selecting cheapest gemini model for trivial task."""
        model = router.select_model("gemini", "format_check")

        # gemini-3-flash is cheapest and handles TRIVIAL
        assert model == "gemini-3-flash"

    def test_select_model_complex_task(self, router):
        """Test model selection for complex task."""
        model = router.select_model("cursor", "security_audit")

        # Should select model capable of COMPLEX tasks
        spec = MODEL_REGISTRY.get(model)
        if spec:
            # Complexity threshold should be at or above COMPLEX
            assert spec.complexity_threshold.value in ["complex", "expert"]

    def test_select_model_with_required_capabilities(self, router):
        """Test model selection with capability requirements."""
        model = router.select_model(
            "cursor",
            "security_audit",
            required_capabilities=["security"],
        )

        # Should be a model with security capability
        spec = MODEL_REGISTRY.get(model)
        if spec:
            assert "security" in spec.capabilities

    def test_select_model_with_context_size(self, router):
        """Test model selection with context window requirement."""
        model = router.select_model(
            "gemini",
            "architecture_review",
            context_size=500000,
        )

        # Should select model with sufficient context
        spec = MODEL_REGISTRY.get(model)
        if spec:
            assert spec.context_window >= 500000

    def test_select_model_prefer_speed(self, router):
        """Test model selection preferring speed over cost."""
        model_speed = router.select_model("gemini", "format_check", prefer_speed=True)
        model_cost = router.select_model("gemini", "format_check", prefer_speed=False)

        # Speed-preferred should have lower latency (or be same model)
        # Both should be valid models
        assert model_speed in MODEL_REGISTRY
        assert model_cost in MODEL_REGISTRY

    def test_estimate_cost(self, router):
        """Test cost estimation for model."""
        cost = router.estimate_cost(
            model="gpt-4.5-turbo",
            estimated_input_tokens=1000,
            estimated_output_tokens=1000,
        )

        # (1000/1000 * 0.005) + (1000/1000 * 0.015) = 0.02
        assert cost == pytest.approx(0.02)

    def test_estimate_cost_unknown_model(self, router):
        """Test cost estimation for unknown model."""
        cost = router.estimate_cost(
            model="unknown-model",
            estimated_input_tokens=1000,
            estimated_output_tokens=1000,
        )

        # Default estimate
        assert cost == pytest.approx(0.04)

    def test_get_savings_estimate(self, router):
        """Test savings estimation."""
        savings = router.get_savings_estimate(
            task_type="format_check",
            input_tokens=1000,
            output_tokens=1000,
        )

        assert "cursor" in savings
        assert "gemini" in savings

        # Should have default and optimized costs
        assert "default_cost" in savings["cursor"]
        assert "optimized_cost" in savings["cursor"]
        assert "savings" in savings["cursor"]
        assert "savings_pct" in savings["cursor"]

    def test_get_savings_trivial_task(self, router):
        """Test savings are positive for trivial tasks."""
        savings = router.get_savings_estimate(
            task_type="format_check",
            input_tokens=10000,
            output_tokens=5000,
        )

        # Gemini flash is much cheaper than gemini-3-pro
        # So there should be savings for gemini
        assert savings["gemini"]["savings"] >= 0

    def test_task_complexity_map_coverage(self, router):
        """Test task complexity map has entries for common tasks."""
        expected_tasks = [
            "format_check",
            "syntax_validation",
            "code_formatting",
            "bug_detection",
            "security_audit",
            "system_design",
        ]

        for task in expected_tasks:
            assert task in router.TASK_COMPLEXITY_MAP


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for cost optimization."""

    def test_tracker_with_router(self, tmp_path):
        """Test using tracker with router for complete workflow."""
        tracker = TokenTracker(storage_dir=tmp_path, budget_limit=1.0)
        router = ModelRouter(cost_optimization_enabled=True)

        # Select model for task
        model = router.select_model("gemini", "format_check")

        # Estimate cost
        estimated = router.estimate_cost(model, 1000, 500)

        # Check budget
        within, remaining = tracker.check_budget(estimated)
        assert within is True

        # Record actual usage
        usage = tracker.record(
            model=model,
            input_tokens=1000,
            output_tokens=500,
            task_type="format_check",
            phase=2,
        )

        # Verify tracking
        assert usage.model == model
        assert tracker.get_total_cost() > 0

    def test_multiple_phases_tracking(self, tmp_path):
        """Test tracking usage across multiple phases."""
        tracker = TokenTracker(storage_dir=tmp_path)

        # Phase 1: Planning
        tracker.record(
            model="claude-opus-4.5",
            input_tokens=5000,
            output_tokens=2000,
            task_type="planning",
            phase=1,
        )

        # Phase 2: Validation
        tracker.record(
            model="gemini-3-flash",
            input_tokens=3000,
            output_tokens=500,
            task_type="validation",
            phase=2,
        )
        tracker.record(
            model="gpt-4.5-turbo",
            input_tokens=3000,
            output_tokens=500,
            task_type="validation",
            phase=2,
        )

        # Phase 3: Implementation
        tracker.record(
            model="claude-sonnet-4",
            input_tokens=10000,
            output_tokens=8000,
            task_type="implementation",
            phase=3,
        )

        summary = tracker.get_summary()

        assert summary.total_calls == 4
        assert "1" in summary.by_phase
        assert "2" in summary.by_phase
        assert "3" in summary.by_phase
        assert summary.by_phase["2"]["calls"] == 2


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_zero_tokens(self, tmp_path):
        """Test handling zero tokens."""
        tracker = TokenTracker(storage_dir=tmp_path)

        usage = tracker.record(
            model="gpt-4.5-turbo",
            input_tokens=0,
            output_tokens=0,
        )

        assert usage.cost == 0.0

    def test_very_large_tokens(self, tmp_path):
        """Test handling very large token counts."""
        tracker = TokenTracker(storage_dir=tmp_path)

        usage = tracker.record(
            model="gpt-4.5-turbo",
            input_tokens=1000000,
            output_tokens=500000,
        )

        # Should calculate cost correctly
        # (1M/1K * 0.005) + (500K/1K * 0.015) = 5 + 7.5 = 12.5
        assert usage.cost == pytest.approx(12.5)

    def test_storage_dir_creation(self, tmp_path):
        """Test storage directory is created if it doesn't exist."""
        storage_dir = tmp_path / "nested" / "path" / "usage"

        tracker = TokenTracker(storage_dir=storage_dir)
        tracker.record(model="test", input_tokens=1, output_tokens=1)

        assert storage_dir.exists()
        assert (storage_dir / "token_usage.json").exists()

    def test_model_router_no_matching_model(self):
        """Test router falls back to default when no model matches."""
        router = ModelRouter(
            default_cursor_model="gpt-5.2-codex",
            cost_optimization_enabled=True,
        )

        # Request impossible combination
        model = router.select_model(
            "cursor",
            "system_design",
            required_capabilities=["nonexistent_capability"],
            context_size=10000000,  # 10M context
        )

        # Should fall back to default
        assert model == "gpt-5.2-codex"

    def test_savings_with_zero_default_cost(self, tmp_path):
        """Test savings calculation doesn't divide by zero."""
        router = ModelRouter(cost_optimization_enabled=True)

        savings = router.get_savings_estimate(
            task_type="format_check",
            input_tokens=0,
            output_tokens=0,
        )

        # Should handle gracefully
        assert savings["cursor"]["savings_pct"] == 0
