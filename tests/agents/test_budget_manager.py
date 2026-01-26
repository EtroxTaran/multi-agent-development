"""Tests for budget manager.

Tests budget tracking, limits, enforcement, and cost estimation.
"""


import pytest

from orchestrator.agents.budget import (
    AGENT_PRICING,
    DEFAULT_INVOCATION_BUDGET_USD,
    DEFAULT_PROJECT_BUDGET_USD,
    DEFAULT_TASK_BUDGET_USD,
    BudgetConfig,
    BudgetEnforcementResult,
    BudgetExceeded,
    BudgetManager,
    BudgetState,
    SpendRecord,
    estimate_cost,
    get_model_pricing,
)


class TestSpendRecord:
    """Tests for SpendRecord dataclass."""

    def test_spend_record_creation(self, sample_spend_record):
        """Test SpendRecord creation."""
        assert sample_spend_record.id == "spend-20260126120000-0001"
        assert sample_spend_record.task_id == "T1"
        assert sample_spend_record.agent == "claude"
        assert sample_spend_record.amount_usd == 0.05
        assert sample_spend_record.model == "sonnet"
        assert sample_spend_record.prompt_tokens == 1000
        assert sample_spend_record.completion_tokens == 500

    def test_spend_record_to_dict(self, sample_spend_record):
        """Test serialization to dictionary."""
        d = sample_spend_record.to_dict()
        assert d["id"] == "spend-20260126120000-0001"
        assert d["task_id"] == "T1"
        assert d["agent"] == "claude"
        assert d["amount_usd"] == 0.05

    def test_spend_record_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "spend-123",
            "timestamp": "2026-01-26T12:00:00",
            "task_id": "T2",
            "agent": "cursor",
            "amount_usd": 0.10,
            "model": "codex-5.2",
            "prompt_tokens": 2000,
            "completion_tokens": 1000,
            "metadata": {},
        }
        record = SpendRecord.from_dict(data)
        assert record.id == "spend-123"
        assert record.task_id == "T2"
        assert record.agent == "cursor"
        assert record.amount_usd == 0.10


class TestBudgetConfig:
    """Tests for BudgetConfig dataclass."""

    def test_budget_config_defaults(self):
        """Test default configuration values."""
        config = BudgetConfig()
        assert config.project_budget_usd == DEFAULT_PROJECT_BUDGET_USD
        assert config.task_budget_usd == DEFAULT_TASK_BUDGET_USD
        assert config.invocation_budget_usd == DEFAULT_INVOCATION_BUDGET_USD
        assert config.task_budgets == {}
        assert config.warn_at_percent == 80.0
        assert config.enabled is True

    def test_budget_config_custom_values(self, sample_budget_config):
        """Test custom configuration values."""
        assert sample_budget_config.project_budget_usd == 50.00
        assert sample_budget_config.task_budget_usd == 5.00
        assert sample_budget_config.invocation_budget_usd == 1.00
        assert sample_budget_config.task_budgets == {"T1": 2.00}

    def test_budget_config_to_dict(self, sample_budget_config):
        """Test serialization."""
        d = sample_budget_config.to_dict()
        assert d["project_budget_usd"] == 50.00
        assert d["task_budget_usd"] == 5.00
        assert d["task_budgets"] == {"T1": 2.00}

    def test_budget_config_from_dict(self):
        """Test deserialization."""
        data = {
            "project_budget_usd": 100.00,
            "task_budget_usd": 10.00,
            "invocation_budget_usd": 2.00,
            "task_budgets": {"T1": 5.00},
            "warn_at_percent": 75.0,
            "enabled": True,
        }
        config = BudgetConfig.from_dict(data)
        assert config.project_budget_usd == 100.00
        assert config.task_budget_usd == 10.00


class TestBudgetState:
    """Tests for BudgetState dataclass."""

    def test_budget_state_defaults(self):
        """Test default state values."""
        state = BudgetState()
        assert state.total_spent_usd == 0.0
        assert state.task_spent == {}
        assert state.records == []
        assert isinstance(state.config, BudgetConfig)

    def test_budget_state_to_dict(self):
        """Test serialization."""
        state = BudgetState(total_spent_usd=5.0, task_spent={"T1": 2.0, "T2": 3.0})
        d = state.to_dict()
        assert d["total_spent_usd"] == 5.0
        assert d["task_spent"] == {"T1": 2.0, "T2": 3.0}

    def test_budget_state_from_dict(self):
        """Test deserialization."""
        data = {
            "total_spent_usd": 10.0,
            "task_spent": {"T1": 5.0},
            "records": [],
            "config": {"project_budget_usd": 100.0},
            "updated_at": "2026-01-26T12:00:00",
        }
        state = BudgetState.from_dict(data)
        assert state.total_spent_usd == 10.0
        assert state.task_spent == {"T1": 5.0}


class TestBudgetExceeded:
    """Tests for BudgetExceeded exception."""

    def test_budget_exceeded_message(self):
        """Test exception message format."""
        exc = BudgetExceeded(
            limit_type="project",
            limit_usd=50.00,
            current_usd=45.00,
            requested_usd=10.00,
        )
        assert exc.limit_type == "project"
        assert exc.limit_usd == 50.00
        assert exc.current_usd == 45.00
        assert exc.requested_usd == 10.00
        assert "project budget exceeded" in str(exc)


class TestBudgetEnforcementResult:
    """Tests for BudgetEnforcementResult dataclass."""

    def test_enforcement_result_allowed(self):
        """Test allowed enforcement result."""
        result = BudgetEnforcementResult(
            allowed=True,
            current_usd=10.0,
            requested_usd=1.0,
            remaining_usd=39.0,
            message="Budget check passed",
        )
        assert result.allowed is True
        assert result.should_escalate is False
        assert result.should_abort is False

    def test_enforcement_result_exceeded(self):
        """Test exceeded enforcement result."""
        result = BudgetEnforcementResult(
            allowed=False,
            exceeded_type="project",
            limit_usd=50.0,
            current_usd=50.0,
            requested_usd=1.0,
            remaining_usd=0.0,
            should_escalate=True,
            should_abort=True,
            message="Project budget exceeded",
        )
        assert result.allowed is False
        assert result.should_escalate is True
        assert result.should_abort is True

    def test_enforcement_result_to_dict(self):
        """Test serialization."""
        result = BudgetEnforcementResult(allowed=True, message="OK")
        d = result.to_dict()
        assert d["allowed"] is True
        assert d["message"] == "OK"


class TestBudgetManager:
    """Tests for BudgetManager class."""

    def test_initialization(self, budget_manager):
        """Test manager initialization."""
        assert budget_manager.project_dir.exists()
        assert budget_manager._state is not None

    def test_initialization_with_config(self, temp_project_dir, sample_budget_config):
        """Test initialization with custom config."""
        manager = BudgetManager(temp_project_dir, config=sample_budget_config)
        assert manager.config.project_budget_usd == 50.00
        assert manager.config.task_budgets == {"T1": 2.00}

    def test_set_project_budget(self, budget_manager):
        """Test setting project budget."""
        budget_manager.set_project_budget(100.00)
        assert budget_manager.config.project_budget_usd == 100.00

    def test_set_project_budget_unlimited(self, budget_manager):
        """Test setting unlimited project budget."""
        budget_manager.set_project_budget(None)
        assert budget_manager.config.project_budget_usd is None

    def test_set_task_budget(self, budget_manager):
        """Test setting task-specific budget."""
        budget_manager.set_task_budget("T1", 10.00)
        assert budget_manager.config.task_budgets["T1"] == 10.00

    def test_set_task_budget_remove(self, budget_manager):
        """Test removing task-specific budget."""
        budget_manager.set_task_budget("T1", 10.00)
        budget_manager.set_task_budget("T1", None)
        assert "T1" not in budget_manager.config.task_budgets

    def test_set_default_task_budget(self, budget_manager):
        """Test setting default task budget."""
        budget_manager.set_default_task_budget(8.00)
        assert budget_manager.config.task_budget_usd == 8.00

    def test_set_invocation_budget(self, budget_manager):
        """Test setting per-invocation budget."""
        budget_manager.set_invocation_budget(2.00)
        assert budget_manager.config.invocation_budget_usd == 2.00

    def test_get_task_budget_specific(self, budget_manager):
        """Test getting task-specific budget."""
        budget_manager.set_task_budget("T1", 10.00)
        assert budget_manager.get_task_budget("T1") == 10.00

    def test_get_task_budget_default(self, budget_manager):
        """Test getting default task budget."""
        budget = budget_manager.get_task_budget("T-NEW")
        assert budget == budget_manager.config.task_budget_usd

    def test_get_invocation_budget(self, budget_manager):
        """Test getting invocation budget."""
        budget = budget_manager.get_invocation_budget("T1")
        assert budget == budget_manager.config.invocation_budget_usd

    def test_get_task_spent(self, budget_manager):
        """Test getting task spending."""
        budget_manager.record_spend("T1", "claude", 0.50)
        assert budget_manager.get_task_spent("T1") == 0.50

    def test_get_task_spent_none(self, budget_manager):
        """Test getting spending for task with no spending."""
        assert budget_manager.get_task_spent("T-NEW") == 0.0

    def test_get_task_remaining(self, budget_manager):
        """Test getting remaining task budget."""
        budget_manager.set_task_budget("T1", 5.00)
        budget_manager.record_spend("T1", "claude", 2.00)
        assert budget_manager.get_task_remaining("T1") == 3.00

    def test_get_task_remaining_unlimited(self, budget_manager):
        """Test remaining for unlimited task budget."""
        budget_manager.set_default_task_budget(None)
        remaining = budget_manager.get_task_remaining("T1")
        assert remaining is None

    def test_get_project_remaining(self, budget_manager):
        """Test getting remaining project budget."""
        budget_manager.set_project_budget(50.00)
        budget_manager.record_spend("T1", "claude", 10.00)
        assert budget_manager.get_project_remaining() == 40.00

    def test_get_project_remaining_unlimited(self, budget_manager):
        """Test remaining for unlimited project budget."""
        budget_manager.set_project_budget(None)
        remaining = budget_manager.get_project_remaining()
        assert remaining is None

    def test_can_spend_allowed(self, budget_manager):
        """Test can_spend when within budget."""
        budget_manager.set_project_budget(50.00)
        assert budget_manager.can_spend("T1", 5.00) is True

    def test_can_spend_project_exceeded(self, budget_manager):
        """Test can_spend when project budget would be exceeded."""
        budget_manager.set_project_budget(10.00)
        budget_manager.record_spend("T1", "claude", 8.00)
        assert budget_manager.can_spend("T1", 5.00) is False

    def test_can_spend_task_exceeded(self, budget_manager):
        """Test can_spend when task budget would be exceeded."""
        budget_manager.set_task_budget("T1", 5.00)
        budget_manager.record_spend("T1", "claude", 4.00)
        assert budget_manager.can_spend("T1", 2.00) is False

    def test_can_spend_raises_on_exceeded(self, budget_manager):
        """Test can_spend with raise_on_exceeded."""
        budget_manager.set_project_budget(10.00)
        budget_manager.record_spend("T1", "claude", 8.00)

        with pytest.raises(BudgetExceeded):
            budget_manager.can_spend("T1", 5.00, raise_on_exceeded=True)

    def test_require_budget(self, budget_manager):
        """Test require_budget raises when exceeded."""
        budget_manager.set_project_budget(10.00)
        budget_manager.record_spend("T1", "claude", 8.00)

        with pytest.raises(BudgetExceeded):
            budget_manager.require_budget("T1", 5.00)

    def test_enforce_budget_allowed(self, budget_manager):
        """Test enforce_budget when allowed."""
        budget_manager.set_project_budget(50.00)
        result = budget_manager.enforce_budget("T1", 5.00)

        assert result.allowed is True
        assert result.should_escalate is False
        assert result.should_abort is False

    def test_enforce_budget_project_exceeded(self, budget_manager):
        """Test enforce_budget when project budget exceeded."""
        budget_manager.set_project_budget(10.00)
        budget_manager.record_spend("T1", "claude", 8.00)

        result = budget_manager.enforce_budget("T1", 5.00)

        assert result.allowed is False
        assert result.exceeded_type == "project"
        assert result.should_escalate is True

    def test_enforce_budget_task_exceeded(self, budget_manager):
        """Test enforce_budget when task budget exceeded."""
        budget_manager.set_task_budget("T1", 5.00)
        budget_manager.record_spend("T1", "claude", 4.00)

        result = budget_manager.enforce_budget("T1", 2.00)

        assert result.allowed is False
        assert "task:T1" in result.exceeded_type
        assert result.should_escalate is True

    def test_enforce_budget_soft_limit(self, budget_manager):
        """Test enforce_budget at soft limit threshold."""
        budget_manager.set_project_budget(100.00)
        budget_manager.record_spend("T1", "claude", 91.00)  # 91% used

        result = budget_manager.enforce_budget("T1", 1.00, soft_limit_percent=90.0)

        assert result.allowed is True
        assert result.should_escalate is True  # At soft limit

    def test_is_budget_exceeded_false(self, budget_manager):
        """Test is_budget_exceeded when not exceeded."""
        budget_manager.set_project_budget(50.00)
        assert budget_manager.is_budget_exceeded() is False

    def test_is_budget_exceeded_true(self, budget_manager):
        """Test is_budget_exceeded when exceeded."""
        budget_manager.set_project_budget(10.00)
        budget_manager.record_spend("T1", "claude", 10.00)
        assert budget_manager.is_budget_exceeded() is True

    def test_is_budget_exceeded_task(self, budget_manager):
        """Test is_budget_exceeded for specific task."""
        budget_manager.set_task_budget("T1", 5.00)
        budget_manager.record_spend("T1", "claude", 5.00)
        assert budget_manager.is_budget_exceeded("T1") is True

    def test_record_spend(self, budget_manager):
        """Test recording a spend event."""
        record = budget_manager.record_spend(
            task_id="T1",
            agent="claude",
            amount_usd=0.50,
            model="sonnet",
            prompt_tokens=1000,
            completion_tokens=500,
        )

        assert record.task_id == "T1"
        assert record.agent == "claude"
        assert record.amount_usd == 0.50
        assert budget_manager._state.total_spent_usd == 0.50
        assert budget_manager._state.task_spent["T1"] == 0.50

    def test_record_spend_accumulates(self, budget_manager):
        """Test that spending accumulates."""
        budget_manager.record_spend("T1", "claude", 0.25)
        budget_manager.record_spend("T1", "claude", 0.25)
        budget_manager.record_spend("T2", "cursor", 0.50)

        assert budget_manager._state.total_spent_usd == 1.00
        assert budget_manager._state.task_spent["T1"] == 0.50
        assert budget_manager._state.task_spent["T2"] == 0.50

    def test_get_budget_status(self, budget_manager):
        """Test getting budget status."""
        budget_manager.set_project_budget(50.00)
        budget_manager.record_spend("T1", "claude", 10.00)

        status = budget_manager.get_budget_status()

        assert status["total_spent_usd"] == 10.00
        assert status["project_budget_usd"] == 50.00
        assert status["project_remaining_usd"] == 40.00
        assert status["project_used_percent"] == 20.0
        assert status["enabled"] is True

    def test_get_enforcement_status(self, budget_manager):
        """Test getting enforcement status."""
        budget_manager.set_project_budget(50.00)
        budget_manager.record_spend("T1", "claude", 10.00)

        status = budget_manager.get_enforcement_status()

        assert status["budget_enabled"] is True
        assert status["project_budget_usd"] == 50.00
        assert status["project_spent_usd"] == 10.00
        assert status["project_exceeded"] is False
        assert status["project_percent_used"] == 20.0

    def test_get_task_spending_report(self, budget_manager):
        """Test getting task spending report."""
        budget_manager.set_task_budget("T1", 5.00)
        budget_manager.record_spend("T1", "claude", 2.00)
        budget_manager.record_spend("T2", "cursor", 1.00)

        report = budget_manager.get_task_spending_report()

        assert len(report) == 2
        # Should be sorted by spending (descending)
        assert report[0]["task_id"] == "T1"
        assert report[0]["spent_usd"] == 2.00
        assert report[0]["budget_usd"] == 5.00
        assert report[0]["remaining_usd"] == 3.00

    def test_reset_task_spending(self, budget_manager):
        """Test resetting task spending."""
        budget_manager.record_spend("T1", "claude", 5.00)
        budget_manager.record_spend("T2", "cursor", 3.00)

        result = budget_manager.reset_task_spending("T1")

        assert result is True
        assert budget_manager.get_task_spent("T1") == 0.0
        assert budget_manager._state.total_spent_usd == 3.00

    def test_reset_task_spending_nonexistent(self, budget_manager):
        """Test resetting nonexistent task."""
        result = budget_manager.reset_task_spending("T-NONEXISTENT")
        assert result is False

    def test_reset_all(self, budget_manager):
        """Test resetting all spending."""
        budget_manager.record_spend("T1", "claude", 5.00)
        budget_manager.record_spend("T2", "cursor", 3.00)

        budget_manager.reset_all()

        assert budget_manager._state.total_spent_usd == 0.0
        assert budget_manager._state.task_spent == {}
        assert budget_manager._state.records == []

    def test_persistence(self, temp_project_dir):
        """Test that state persists across manager instances."""
        manager1 = BudgetManager(temp_project_dir)
        manager1.set_project_budget(100.00)
        manager1.record_spend("T1", "claude", 10.00)

        manager2 = BudgetManager(temp_project_dir)
        assert manager2.config.project_budget_usd == 100.00
        assert manager2._state.total_spent_usd == 10.00
        assert manager2._state.task_spent["T1"] == 10.00


class TestEstimateCost:
    """Tests for estimate_cost function."""

    def test_estimate_cost_claude_sonnet(self):
        """Test cost estimation for Claude Sonnet."""
        cost = estimate_cost("sonnet", 1000, 500)
        # Input: 1000 tokens * $3/1M = $0.003
        # Output: 500 tokens * $15/1M = $0.0075
        # Total: $0.0105
        assert cost == pytest.approx(0.0105, rel=0.01)

    def test_estimate_cost_claude_opus(self):
        """Test cost estimation for Claude Opus."""
        cost = estimate_cost("opus", 1000, 500, agent="claude")
        # Input: 1000 tokens * $15/1M = $0.015
        # Output: 500 tokens * $75/1M = $0.0375
        # Total: $0.0525
        assert cost == pytest.approx(0.0525, rel=0.01)

    def test_estimate_cost_gemini_flash(self):
        """Test cost estimation for Gemini Flash."""
        cost = estimate_cost("gemini-2.0-flash", 1000, 500, agent="gemini")
        # Much cheaper - should be < $0.01
        assert cost < 0.01

    def test_estimate_cost_unknown_model(self):
        """Test cost estimation for unknown model falls back to default."""
        cost = estimate_cost("unknown-model", 1000, 500, agent="claude")
        # Should use sonnet pricing as fallback
        assert cost == pytest.approx(0.0105, rel=0.01)


class TestGetModelPricing:
    """Tests for get_model_pricing function."""

    def test_get_claude_sonnet_pricing(self):
        """Test getting Claude Sonnet pricing."""
        pricing = get_model_pricing("claude", "sonnet")
        assert pricing["input"] == 3.0
        assert pricing["output"] == 15.0

    def test_get_cursor_pricing(self):
        """Test getting Cursor pricing."""
        pricing = get_model_pricing("cursor", "codex-5.2")
        assert pricing["input"] == 5.0
        assert pricing["output"] == 15.0

    def test_get_gemini_pricing(self):
        """Test getting Gemini pricing."""
        pricing = get_model_pricing("gemini", "gemini-2.0-flash")
        assert pricing["input"] == 0.075
        assert pricing["output"] == 0.30

    def test_get_unknown_model_fallback(self):
        """Test unknown model falls back to first in agent's pricing."""
        pricing = get_model_pricing("claude", "unknown")
        # Should get some valid pricing
        assert "input" in pricing
        assert "output" in pricing


class TestAgentPricing:
    """Tests for AGENT_PRICING constant."""

    def test_all_agents_have_pricing(self):
        """Test all agents have pricing defined."""
        assert "claude" in AGENT_PRICING
        assert "cursor" in AGENT_PRICING
        assert "gemini" in AGENT_PRICING

    def test_claude_models_have_pricing(self):
        """Test Claude models have pricing."""
        claude_pricing = AGENT_PRICING["claude"]
        assert "sonnet" in claude_pricing
        assert "opus" in claude_pricing
        assert "haiku" in claude_pricing

    def test_pricing_structure(self):
        """Test pricing has correct structure."""
        for _agent, models in AGENT_PRICING.items():
            for _model, pricing in models.items():
                assert "input" in pricing
                assert "output" in pricing
                assert pricing["input"] >= 0
                assert pricing["output"] >= 0
