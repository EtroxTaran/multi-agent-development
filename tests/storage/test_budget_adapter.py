"""Tests for budget storage adapter."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.storage.base import BudgetSummaryData
from orchestrator.storage.budget_adapter import BudgetStorageAdapter, get_budget_storage


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        yield project_dir


@pytest.fixture
def mock_budget_repository():
    """Create a mock budget repository."""
    mock_repo = MagicMock()
    mock_repo.record_spend = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.get_task_cost = AsyncMock(return_value=0.0)
    mock_repo.get_total_cost = AsyncMock(return_value=0.0)
    mock_repo.get_cost_by_agent = AsyncMock(return_value={})
    mock_repo.get_summary = AsyncMock(
        return_value=MagicMock(
            total_cost_usd=0.0,
            by_agent={},
            by_task={},
            record_count=0,
        )
    )
    mock_repo.get_config = AsyncMock(
        return_value=MagicMock(
            enabled=True,
            task_budget_usd=5.0,
            invocation_budget_usd=1.0,
            project_budget_usd=50.0,
            task_budgets={},
            warn_at_percent=80.0,
        )
    )
    mock_repo.enforce_budget = AsyncMock(
        return_value=MagicMock(
            allowed=True,
            reason=None,
            remaining=5.0,
        )
    )
    return mock_repo


class TestBudgetStorageAdapter:
    """Tests for BudgetStorageAdapter."""

    def test_init(self, temp_project):
        """Test adapter initialization."""
        adapter = BudgetStorageAdapter(temp_project)
        assert adapter.project_dir == temp_project
        assert adapter.project_name == temp_project.name

    def test_record_spend(self, temp_project, mock_budget_repository):
        """Test recording spend."""
        # Set up mock to return accumulated cost
        mock_budget_repository.get_task_cost = AsyncMock(return_value=0.05)

        with patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repository,
        ):
            adapter = BudgetStorageAdapter(temp_project)

            adapter.record_spend(
                task_id="T1",
                agent="claude",
                cost_usd=0.05,
                model="sonnet",
            )

            # Verify spend was recorded
            spent = adapter.get_task_spent("T1")
            assert spent == 0.05

    def test_get_task_spent_none(self, temp_project, mock_budget_repository):
        """Test get_task_spent returns 0 for unknown task."""
        with patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repository,
        ):
            adapter = BudgetStorageAdapter(temp_project)
            spent = adapter.get_task_spent("nonexistent")
            assert spent == 0.0

    def test_get_task_spent_after_record(self, temp_project, mock_budget_repository):
        """Test get_task_spent returns accumulated spend."""
        # Set up mock to return accumulated cost
        mock_budget_repository.get_task_cost = AsyncMock(return_value=0.15)

        with patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repository,
        ):
            adapter = BudgetStorageAdapter(temp_project)

            adapter.record_spend("T1", "claude", 0.05)
            adapter.record_spend("T1", "claude", 0.10)

            spent = adapter.get_task_spent("T1")
            assert spent == pytest.approx(0.15)

    def test_get_task_remaining(self, temp_project, mock_budget_repository):
        """Test get_task_remaining returns remaining budget."""
        # Set up mock - task cost is 1.0, task budget is 5.0
        mock_budget_repository.get_task_cost = AsyncMock(return_value=1.0)

        with patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repository,
        ):
            adapter = BudgetStorageAdapter(temp_project)

            # Get remaining
            remaining = adapter.get_task_remaining("T1")
            # Default task budget is 5.0, remaining should be 4.0
            assert remaining == 4.0

    def test_can_spend_true(self, temp_project, mock_budget_repository):
        """Test can_spend returns True when within budget."""
        with patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repository,
        ):
            adapter = BudgetStorageAdapter(temp_project)

            result = adapter.can_spend("T1", 0.50)
            assert result is True

    def test_can_spend_after_spending(self, temp_project, mock_budget_repository):
        """Test can_spend returns True after some spending."""
        # Set up mock - task cost is 2.0, budget is 5.0
        mock_budget_repository.get_task_cost = AsyncMock(return_value=2.0)

        with patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repository,
        ):
            adapter = BudgetStorageAdapter(temp_project)

            result = adapter.can_spend("T1", 0.50)
            assert result is True

    def test_get_invocation_budget(self, temp_project, mock_budget_repository):
        """Test get_invocation_budget returns configured budget."""
        with patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repository,
        ):
            adapter = BudgetStorageAdapter(temp_project)

            budget = adapter.get_invocation_budget("T1")
            assert budget == 1.0

    def test_get_summary_empty(self, temp_project, mock_budget_repository):
        """Test get_summary returns empty summary."""
        with patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repository,
        ):
            adapter = BudgetStorageAdapter(temp_project)

            summary = adapter.get_summary()
            assert isinstance(summary, BudgetSummaryData)
            assert summary.total_cost_usd == 0.0

    def test_get_summary_with_records(self, temp_project, mock_budget_repository):
        """Test get_summary includes recorded spend."""
        # Set up mock to return non-zero summary
        mock_budget_repository.get_summary = AsyncMock(
            return_value=MagicMock(
                total_cost_usd=0.08,
                by_agent={"claude": 0.05, "gemini": 0.03},
                by_task={"T1": 0.08},
                record_count=2,
            )
        )

        with patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repository,
        ):
            adapter = BudgetStorageAdapter(temp_project)

            summary = adapter.get_summary()
            assert summary.total_cost_usd == 0.08

    def test_get_total_spent(self, temp_project, mock_budget_repository):
        """Test get_total_spent returns total."""
        # Set up mock to return total cost
        mock_budget_repository.get_total_cost = AsyncMock(return_value=0.15)

        with patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repository,
        ):
            adapter = BudgetStorageAdapter(temp_project)

            total = adapter.get_total_spent()
            assert total == pytest.approx(0.15)

    def test_enforce_budget(self, temp_project, mock_budget_repository):
        """Test enforce_budget returns result."""
        with patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repository,
        ):
            adapter = BudgetStorageAdapter(temp_project)

            result = adapter.enforce_budget("T1", 0.50)
            assert result is not None
            # enforce_budget returns dict with 'can_proceed' key
            assert result.get("can_proceed") is True


class TestGetBudgetStorage:
    """Tests for get_budget_storage factory function."""

    def test_returns_adapter(self, temp_project):
        """Test factory returns an adapter."""
        adapter = get_budget_storage(temp_project)
        assert isinstance(adapter, BudgetStorageAdapter)

    def test_caches_adapter(self, temp_project):
        """Test factory returns same adapter for same project."""
        adapter1 = get_budget_storage(temp_project)
        adapter2 = get_budget_storage(temp_project)
        assert adapter1 is adapter2
