"""Unit tests for BudgetManager."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.agents.budget import (
    BudgetConfig,
    BudgetEnforcementResult,
    BudgetExceeded,
    BudgetManager,
    SpendRecord,
    estimate_cost,
)


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project = tmp_path / "test-project"
    project.mkdir()
    return project


def create_mock_budget_storage():
    """Create a mock BudgetStorageAdapter with in-memory tracking."""
    mock_storage = MagicMock()

    # In-memory data store
    mock_storage._records = []
    mock_storage.project_budget_usd = 50.0
    mock_storage.task_budget_usd = 5.0
    mock_storage.invocation_budget_usd = 1.0

    # Mock DB backend
    mock_db = MagicMock()
    mock_storage._get_db_backend = MagicMock(return_value=mock_db)

    def record_spend(task_id, agent, cost_usd, model=None, tokens_input=None, tokens_output=None):
        record = MagicMock()
        record.id = f"spend-{len(mock_storage._records)}"
        record.task_id = task_id
        record.agent = agent
        record.cost_usd = cost_usd
        record.model = model
        mock_storage._records.append(record)
        return record

    def get_task_spent(task_id):
        return sum(r.cost_usd for r in mock_storage._records if r.task_id == task_id)

    def get_total_spent():
        return sum(r.cost_usd for r in mock_storage._records)

    def get_task_ids():
        return list({r.task_id for r in mock_storage._records})

    def get_all_records():
        return mock_storage._records

    def get_project_remaining():
        total = sum(r.cost_usd for r in mock_storage._records)
        return mock_storage.project_budget_usd - total

    def get_summary():
        summary = MagicMock()
        summary.total_cost_usd = sum(r.cost_usd for r in mock_storage._records)
        # Build by_task dict
        by_task = {}
        for r in mock_storage._records:
            if r.task_id not in by_task:
                by_task[r.task_id] = 0.0
            by_task[r.task_id] += r.cost_usd
        summary.by_task = by_task
        summary.by_agent = {}
        summary.record_count = len(mock_storage._records)
        summary.total_tokens_input = 0
        summary.total_tokens_output = 0
        summary.by_model = {}
        return summary

    mock_storage.record_spend = MagicMock(side_effect=record_spend)
    mock_storage.get_task_spent = MagicMock(side_effect=get_task_spent)
    mock_storage.get_total_spent = MagicMock(side_effect=get_total_spent)
    mock_storage.get_task_ids = MagicMock(side_effect=get_task_ids)
    mock_storage.get_all_records = MagicMock(side_effect=get_all_records)
    mock_storage.get_project_remaining = MagicMock(side_effect=get_project_remaining)
    mock_storage.get_summary = MagicMock(side_effect=get_summary)

    # Mock async reset methods for db backend
    async def mock_reset_task(task_id):
        # Add negative record to zero out spending
        spent = sum(r.cost_usd for r in mock_storage._records if r.task_id == task_id)
        if spent > 0:
            record = MagicMock()
            record.task_id = task_id
            record.agent = "system_reset"
            record.cost_usd = -spent
            mock_storage._records.append(record)
            return 1
        return 0

    async def mock_delete_task(task_id):
        initial_count = len(mock_storage._records)
        mock_storage._records = [r for r in mock_storage._records if r.task_id != task_id]
        return initial_count - len(mock_storage._records)

    async def mock_reset_all():
        task_ids = list({r.task_id for r in mock_storage._records if r.cost_usd > 0})
        for tid in task_ids:
            await mock_reset_task(tid)
        return len(task_ids)

    async def mock_delete_all():
        count = len(mock_storage._records)
        mock_storage._records = []
        return count

    mock_db.reset_task_spending = mock_reset_task
    mock_db.delete_task_records = mock_delete_task
    mock_db.reset_all_spending = mock_reset_all
    mock_db.delete_all_records = mock_delete_all

    return mock_storage


@pytest.fixture
def budget_manager(temp_project: Path) -> BudgetManager:
    """Create a budget manager for testing with mocked storage."""
    manager = BudgetManager(temp_project)
    # Replace storage with mock
    mock_storage = create_mock_budget_storage()
    manager._storage = mock_storage
    return manager


class TestSpendRecord:
    """Tests for SpendRecord dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        record = SpendRecord(
            id="spend-001",
            timestamp="2024-01-15T10:00:00",
            task_id="T1",
            agent="claude",
            amount_usd=0.05,
            model="claude-3-opus",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        data = record.to_dict()

        assert data["id"] == "spend-001"
        assert data["amount_usd"] == 0.05
        assert data["model"] == "claude-3-opus"
        assert data["prompt_tokens"] == 1000

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "spend-002",
            "timestamp": "2024-01-15T11:00:00",
            "task_id": "T2",
            "agent": "cursor",
            "amount_usd": 0.03,
            "model": "gpt-4",
        }
        record = SpendRecord.from_dict(data)

        assert record.id == "spend-002"
        assert record.amount_usd == 0.03
        assert record.model == "gpt-4"


class TestBudgetConfig:
    """Tests for BudgetConfig dataclass."""

    def test_defaults(self):
        """Test default configuration with reasonable limits."""
        config = BudgetConfig()

        # Now defaults to reasonable limits to prevent runaway costs
        assert config.project_budget_usd == 50.0  # $50 per workflow run
        assert config.task_budget_usd == 5.0  # $5 per task
        assert config.invocation_budget_usd == 1.00
        assert config.warn_at_percent == 80.0
        assert config.enabled is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = BudgetConfig(
            project_budget_usd=100.0,
            task_budget_usd=5.0,
            invocation_budget_usd=0.50,
        )

        assert config.project_budget_usd == 100.0
        assert config.task_budget_usd == 5.0
        assert config.invocation_budget_usd == 0.50


class TestBudgetManager:
    """Tests for BudgetManager."""

    def test_record_spend(self, budget_manager: BudgetManager):
        """Test recording a spend."""
        record = budget_manager.record_spend(
            task_id="T1",
            agent="claude",
            amount_usd=0.05,
            model="claude-3-opus",
        )

        assert record.task_id == "T1"
        assert record.amount_usd == 0.05
        assert record.agent == "claude"

    def test_get_task_spent(self, budget_manager: BudgetManager):
        """Test getting amount spent on a task."""
        budget_manager.record_spend("T1", "claude", 0.05)
        budget_manager.record_spend("T1", "claude", 0.03)
        budget_manager.record_spend("T2", "claude", 0.10)

        assert budget_manager.get_task_spent("T1") == 0.08
        assert budget_manager.get_task_spent("T2") == 0.10
        assert budget_manager.get_task_spent("T3") == 0.0

    def test_set_project_budget(self, budget_manager: BudgetManager):
        """Test setting project budget."""
        budget_manager.set_project_budget(50.0)

        assert budget_manager.config.project_budget_usd == 50.0

    def test_set_task_budget(self, budget_manager: BudgetManager):
        """Test setting task budget."""
        budget_manager.set_task_budget("T1", 2.0)

        assert budget_manager.get_task_budget("T1") == 2.0

    def test_get_task_budget_default(self, budget_manager: BudgetManager):
        """Test getting default task budget."""
        budget_manager.set_default_task_budget(5.0)

        # Task without specific budget gets default
        assert budget_manager.get_task_budget("T1") == 5.0

        # Task with specific budget gets override
        budget_manager.set_task_budget("T2", 3.0)
        assert budget_manager.get_task_budget("T2") == 3.0

    def test_can_spend_within_budget(self, budget_manager: BudgetManager):
        """Test can_spend within budget."""
        budget_manager.set_project_budget(10.0)
        budget_manager.set_task_budget("T1", 5.0)

        assert budget_manager.can_spend("T1", 1.0) is True
        assert budget_manager.can_spend("T1", 4.0) is True

    def test_can_spend_exceeds_task_budget(self, budget_manager: BudgetManager):
        """Test can_spend when exceeding task budget."""
        budget_manager.set_task_budget("T1", 2.0)
        budget_manager.record_spend("T1", "claude", 1.5)

        assert budget_manager.can_spend("T1", 0.3) is True
        assert budget_manager.can_spend("T1", 0.6) is False

    def test_can_spend_exceeds_project_budget(self, budget_manager: BudgetManager):
        """Test can_spend when exceeding project budget."""
        budget_manager.set_project_budget(5.0)
        budget_manager.record_spend("T1", "claude", 4.0)

        assert budget_manager.can_spend("T2", 0.5) is True
        assert budget_manager.can_spend("T2", 2.0) is False

    def test_can_spend_raises_exception(self, budget_manager: BudgetManager):
        """Test can_spend raises BudgetExceeded."""
        budget_manager.set_task_budget("T1", 1.0)
        budget_manager.record_spend("T1", "claude", 0.8)

        with pytest.raises(BudgetExceeded) as exc_info:
            budget_manager.can_spend("T1", 0.5, raise_on_exceeded=True)

        assert exc_info.value.limit_type == "task:T1"
        assert exc_info.value.limit_usd == 1.0
        assert exc_info.value.current_usd == 0.8
        assert exc_info.value.requested_usd == 0.5

    def test_get_task_remaining(self, budget_manager: BudgetManager):
        """Test getting remaining task budget."""
        budget_manager.set_task_budget("T1", 5.0)
        budget_manager.record_spend("T1", "claude", 2.0)

        assert budget_manager.get_task_remaining("T1") == 3.0

    def test_get_task_remaining_unlimited(self, budget_manager: BudgetManager):
        """Test remaining for unlimited task."""
        # Explicitly set unlimited budget (override default)
        budget_manager.set_default_task_budget(None)
        assert budget_manager.get_task_remaining("T1") is None

    def test_get_project_remaining(self, budget_manager: BudgetManager):
        """Test getting remaining project budget."""
        budget_manager.set_project_budget(10.0)
        budget_manager.record_spend("T1", "claude", 3.0)
        budget_manager.record_spend("T2", "claude", 2.0)

        assert budget_manager.get_project_remaining() == 5.0

    def test_get_budget_status(self, budget_manager: BudgetManager):
        """Test getting budget status."""
        budget_manager.set_project_budget(100.0)
        budget_manager.record_spend("T1", "claude", 10.0)
        budget_manager.record_spend("T1", "claude", 5.0)
        budget_manager.record_spend("T2", "cursor", 3.0)

        status = budget_manager.get_budget_status()

        assert status["total_spent_usd"] == 18.0
        assert status["project_budget_usd"] == 100.0
        assert status["project_remaining_usd"] == 82.0
        assert status["project_used_percent"] == 18.0
        assert status["task_count"] == 2
        assert status["record_count"] == 3

    def test_get_task_spending_report(self, budget_manager: BudgetManager):
        """Test getting spending report by task."""
        budget_manager.set_task_budget("T1", 10.0)
        budget_manager.record_spend("T1", "claude", 5.0)
        budget_manager.record_spend("T2", "claude", 2.0)
        budget_manager.record_spend("T3", "cursor", 8.0)

        report = budget_manager.get_task_spending_report()

        # Sorted by spending descending
        assert report[0]["task_id"] == "T3"
        assert report[0]["spent_usd"] == 8.0
        assert report[1]["task_id"] == "T1"
        assert report[1]["remaining_usd"] == 5.0  # 10 - 5
        assert report[2]["task_id"] == "T2"

    def test_reset_task_spending(self, budget_manager: BudgetManager):
        """Test resetting task spending using soft delete."""
        budget_manager.record_spend("T1", "claude", 5.0)
        budget_manager.record_spend("T2", "claude", 3.0)

        result = budget_manager.reset_task_spending("T1")

        assert result is True
        # Soft delete creates a negative record that zeros out the balance
        assert budget_manager.get_task_spent("T1") == 0.0
        assert budget_manager.get_task_spent("T2") == 3.0

    def test_reset_task_spending_no_spending(self, budget_manager: BudgetManager):
        """Test resetting task with no spending returns False."""
        result = budget_manager.reset_task_spending("T1")
        assert result is False

    def test_reset_task_spending_hard_delete(self, budget_manager: BudgetManager):
        """Test hard delete removes records permanently."""
        budget_manager.record_spend("T1", "claude", 5.0)
        budget_manager.record_spend("T2", "claude", 3.0)

        result = budget_manager.reset_task_spending("T1", hard_delete=True)

        assert result is True
        assert budget_manager.get_task_spent("T1") == 0.0
        assert budget_manager.get_task_spent("T2") == 3.0

    def test_reset_all(self, budget_manager: BudgetManager):
        """Test resetting all spending using soft delete."""
        budget_manager.set_project_budget(100.0)
        budget_manager.record_spend("T1", "claude", 10.0)
        budget_manager.record_spend("T2", "claude", 5.0)

        count = budget_manager.reset_all()

        assert count == 2  # Two tasks were reset
        status = budget_manager.get_budget_status()
        # Soft delete creates negative records, so total becomes 0
        assert status["total_spent_usd"] == 0.0
        # Config should be preserved
        assert status["project_budget_usd"] == 100.0

    def test_reset_all_hard_delete(self, budget_manager: BudgetManager):
        """Test hard delete removes all records permanently."""
        budget_manager.set_project_budget(100.0)
        budget_manager.record_spend("T1", "claude", 10.0)
        budget_manager.record_spend("T2", "claude", 5.0)

        count = budget_manager.reset_all(hard_delete=True)

        assert count >= 2  # At least 2 records deleted
        status = budget_manager.get_budget_status()
        assert status["total_spent_usd"] == 0.0
        assert status["record_count"] == 0
        # Config should be preserved
        assert status["project_budget_usd"] == 100.0

    @pytest.mark.db_integration
    def test_budget_persistence(self, temp_project: Path):
        """Test that budget state persists.

        This test requires a real SurrealDB connection.
        """
        pytest.skip("Integration test - requires SurrealDB")
        manager1 = BudgetManager(temp_project)
        manager1.set_project_budget(50.0)
        manager1.record_spend("T1", "claude", 10.0)

        # Create new manager instance
        manager2 = BudgetManager(temp_project)

        assert manager2.config.project_budget_usd == 50.0
        assert manager2.get_task_spent("T1") == 10.0

    def test_get_invocation_budget(self, budget_manager: BudgetManager):
        """Test getting invocation budget."""
        budget_manager.set_invocation_budget(0.75)

        assert budget_manager.get_invocation_budget() == 0.75


class TestEstimateCost:
    """Tests for estimate_cost function."""

    def test_estimate_opus(self):
        """Test cost estimation for Opus model."""
        cost = estimate_cost(
            model="claude-opus-4",
            prompt_tokens=10000,  # 10K tokens
            completion_tokens=5000,  # 5K tokens
        )

        # $15/M input + $75/M output
        # (10000/1M * 15) + (5000/1M * 75) = 0.15 + 0.375 = 0.525
        assert cost == pytest.approx(0.525, abs=0.001)

    def test_estimate_sonnet(self):
        """Test cost estimation for Sonnet model."""
        cost = estimate_cost(
            model="claude-sonnet-4",
            prompt_tokens=10000,
            completion_tokens=5000,
        )

        # $3/M input + $15/M output
        # (10000/1M * 3) + (5000/1M * 15) = 0.03 + 0.075 = 0.105
        assert cost == pytest.approx(0.105, abs=0.001)

    def test_estimate_haiku(self):
        """Test cost estimation for Haiku model."""
        cost = estimate_cost(
            model="claude-haiku-3.5",
            prompt_tokens=10000,
            completion_tokens=5000,
        )

        # $0.80/M input + $4/M output
        # (10000/1M * 0.8) + (5000/1M * 4) = 0.008 + 0.02 = 0.028
        assert cost == pytest.approx(0.028, abs=0.001)

    def test_estimate_unknown_model(self):
        """Test cost estimation for unknown model (defaults to Sonnet)."""
        cost = estimate_cost(
            model="unknown-model",
            prompt_tokens=10000,
            completion_tokens=5000,
        )

        # Should default to Sonnet pricing
        assert cost == pytest.approx(0.105, abs=0.001)

    def test_estimate_short_model_names(self):
        """Test cost estimation with short model names."""
        opus_cost = estimate_cost("opus", 1000, 500)
        sonnet_cost = estimate_cost("sonnet", 1000, 500)
        haiku_cost = estimate_cost("haiku", 1000, 500)

        # Opus should be most expensive
        assert opus_cost > sonnet_cost > haiku_cost


class TestBudgetExceeded:
    """Tests for BudgetExceeded exception."""

    def test_exception_message(self):
        """Test exception message format."""
        exc = BudgetExceeded(
            limit_type="project",
            limit_usd=100.0,
            current_usd=95.0,
            requested_usd=10.0,
        )

        assert "project budget exceeded" in str(exc)
        assert "limit=$100.00" in str(exc)
        assert "current=$95.00" in str(exc)
        assert "requested=$10.00" in str(exc)

    def test_exception_attributes(self):
        """Test exception attributes."""
        exc = BudgetExceeded(
            limit_type="task:T1",
            limit_usd=5.0,
            current_usd=4.0,
            requested_usd=2.0,
        )

        assert exc.limit_type == "task:T1"
        assert exc.limit_usd == 5.0
        assert exc.current_usd == 4.0
        assert exc.requested_usd == 2.0


class TestBudgetEnforcementResult:
    """Tests for BudgetEnforcementResult dataclass."""

    def test_allowed_result(self):
        """Test allowed result."""
        result = BudgetEnforcementResult(
            allowed=True,
            current_usd=10.0,
            requested_usd=1.0,
            remaining_usd=40.0,
            message="Budget check passed",
        )

        assert result.allowed is True
        assert result.should_escalate is False
        assert result.should_abort is False

    def test_exceeded_result(self):
        """Test exceeded result."""
        result = BudgetEnforcementResult(
            allowed=False,
            exceeded_type="project",
            limit_usd=50.0,
            current_usd=49.0,
            requested_usd=5.0,
            remaining_usd=1.0,
            should_escalate=True,
            should_abort=False,
            message="Budget exceeded",
        )

        assert result.allowed is False
        assert result.exceeded_type == "project"
        assert result.should_escalate is True
        assert result.should_abort is False

    def test_to_dict(self):
        """Test serialization to dict."""
        result = BudgetEnforcementResult(
            allowed=True,
            current_usd=10.0,
            requested_usd=1.0,
        )

        d = result.to_dict()
        assert d["allowed"] is True
        assert d["current_usd"] == 10.0
        assert d["requested_usd"] == 1.0


class TestBudgetEnforcement:
    """Tests for budget enforcement methods."""

    def test_require_budget_passes(self, budget_manager: BudgetManager):
        """Test require_budget when within limits."""
        budget_manager.set_project_budget(50.0)
        budget_manager.set_task_budget("T1", 10.0)

        # Should not raise
        budget_manager.require_budget("T1", 5.0)

    def test_require_budget_raises_on_project_exceeded(self, budget_manager: BudgetManager):
        """Test require_budget raises when project budget exceeded."""
        budget_manager.set_project_budget(10.0)
        budget_manager.record_spend("T1", "claude", 8.0)

        with pytest.raises(BudgetExceeded) as exc_info:
            budget_manager.require_budget("T1", 5.0)

        assert exc_info.value.limit_type == "project"

    def test_require_budget_raises_on_task_exceeded(self, budget_manager: BudgetManager):
        """Test require_budget raises when task budget exceeded."""
        budget_manager.set_task_budget("T1", 5.0)
        budget_manager.record_spend("T1", "claude", 4.0)

        with pytest.raises(BudgetExceeded) as exc_info:
            budget_manager.require_budget("T1", 2.0)

        assert "task:T1" in exc_info.value.limit_type

    def test_enforce_budget_allowed(self, budget_manager: BudgetManager):
        """Test enforce_budget returns allowed result."""
        budget_manager.set_project_budget(50.0)

        result = budget_manager.enforce_budget("T1", 5.0)

        assert result.allowed is True
        assert result.should_escalate is False
        assert result.should_abort is False

    def test_enforce_budget_project_exceeded(self, budget_manager: BudgetManager):
        """Test enforce_budget when project budget exceeded."""
        budget_manager.set_project_budget(10.0)
        budget_manager.record_spend("T1", "claude", 8.0)

        result = budget_manager.enforce_budget("T1", 5.0)

        assert result.allowed is False
        assert result.exceeded_type == "project"
        assert result.should_escalate is True
        assert result.limit_usd == 10.0
        assert result.current_usd == 8.0

    def test_enforce_budget_task_exceeded(self, budget_manager: BudgetManager):
        """Test enforce_budget when task budget exceeded."""
        budget_manager.set_project_budget(100.0)
        budget_manager.set_task_budget("T1", 5.0)
        budget_manager.record_spend("T1", "claude", 4.0)

        result = budget_manager.enforce_budget("T1", 2.0)

        assert result.allowed is False
        assert result.exceeded_type == "task:T1"
        assert result.should_escalate is True

    def test_enforce_budget_soft_limit_warning(self, budget_manager: BudgetManager):
        """Test enforce_budget triggers escalation at soft limit."""
        budget_manager.set_project_budget(10.0)
        budget_manager.record_spend("T1", "claude", 9.0)  # 90% used

        result = budget_manager.enforce_budget("T1", 0.5, soft_limit_percent=90.0)

        # Should be allowed but should escalate for warning
        assert result.allowed is True
        assert result.should_escalate is True
        assert result.should_abort is False

    def test_enforce_budget_hard_abort_when_exhausted(self, budget_manager: BudgetManager):
        """Test enforce_budget triggers abort when budget exhausted."""
        budget_manager.set_project_budget(10.0)
        budget_manager.record_spend("T1", "claude", 10.0)  # Exactly at limit

        result = budget_manager.enforce_budget("T1", 1.0)

        assert result.allowed is False
        assert result.should_escalate is True
        assert result.should_abort is True  # Hard abort - nothing left

    def test_is_budget_exceeded_false(self, budget_manager: BudgetManager):
        """Test is_budget_exceeded when within limits."""
        budget_manager.set_project_budget(50.0)

        assert budget_manager.is_budget_exceeded() is False
        assert budget_manager.is_budget_exceeded("T1") is False

    def test_is_budget_exceeded_project(self, budget_manager: BudgetManager):
        """Test is_budget_exceeded when project limit hit."""
        budget_manager.set_project_budget(10.0)
        budget_manager.record_spend("T1", "claude", 10.0)

        assert budget_manager.is_budget_exceeded() is True

    def test_is_budget_exceeded_task(self, budget_manager: BudgetManager):
        """Test is_budget_exceeded when task limit hit."""
        budget_manager.set_project_budget(100.0)
        budget_manager.set_task_budget("T1", 5.0)
        budget_manager.record_spend("T1", "claude", 5.0)

        assert budget_manager.is_budget_exceeded() is False  # Project OK
        assert budget_manager.is_budget_exceeded("T1") is True  # Task exceeded

    def test_get_enforcement_status(self, budget_manager: BudgetManager):
        """Test get_enforcement_status returns comprehensive info."""
        budget_manager.set_project_budget(50.0)
        budget_manager.set_task_budget("T1", 10.0)
        budget_manager.record_spend("T1", "claude", 5.0)

        status = budget_manager.get_enforcement_status()

        assert status["budget_enabled"] is True
        assert status["project_budget_usd"] == 50.0
        assert status["project_spent_usd"] == 5.0
        assert status["project_remaining_usd"] == 45.0
        assert status["project_exceeded"] is False
        assert status["project_percent_used"] == 10.0
        assert status["task_budgets_set"] == 1
        assert status["invocation_budget_usd"] == 1.0
