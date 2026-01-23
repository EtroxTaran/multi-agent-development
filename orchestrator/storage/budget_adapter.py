"""Budget storage adapter.

Provides unified interface for budget tracking using SurrealDB.
This is the DB-only version - no file fallback.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Import budget constants from the canonical source to avoid duplication
from orchestrator.agents.budget import (
    DEFAULT_INVOCATION_BUDGET_USD,
    DEFAULT_PROJECT_BUDGET_USD,
    DEFAULT_TASK_BUDGET_USD,
)

from .async_utils import run_async
from .base import BudgetStorageProtocol, BudgetSummaryData

logger = logging.getLogger(__name__)


class BudgetStorageAdapter(BudgetStorageProtocol):
    """Storage adapter for budget tracking.

    Uses SurrealDB as the only storage backend. No file fallback.

    Usage:
        adapter = BudgetStorageAdapter(project_dir)

        # Record spending
        adapter.record_spend("T1", "claude", 0.05, model="sonnet")

        # Get task spending
        spent = adapter.get_task_spent("T1")

        # Check remaining budget
        remaining = adapter.get_task_remaining("T1")

        # Get summary
        summary = adapter.get_summary()
    """

    def __init__(
        self,
        project_dir: Path,
        project_name: Optional[str] = None,
        project_budget_usd: float = DEFAULT_PROJECT_BUDGET_USD,
        task_budget_usd: float = DEFAULT_TASK_BUDGET_USD,
        invocation_budget_usd: float = DEFAULT_INVOCATION_BUDGET_USD,
    ):
        """Initialize budget storage adapter.

        Args:
            project_dir: Project directory
            project_name: Project name (defaults to directory name)
            project_budget_usd: Total project budget limit
            task_budget_usd: Per-task budget limit
            invocation_budget_usd: Per-invocation budget limit
        """
        self.project_dir = Path(project_dir)
        self.project_name = project_name or self.project_dir.name
        self.project_budget_usd = project_budget_usd
        self.task_budget_usd = task_budget_usd
        self.invocation_budget_usd = invocation_budget_usd
        self._db_backend: Optional[Any] = None

    def _get_db_backend(self) -> Any:
        """Get or create database backend."""
        if self._db_backend is None:
            from orchestrator.db.repositories.budget import get_budget_repository

            self._db_backend = get_budget_repository(self.project_name)
        return self._db_backend

    def record_spend(
        self,
        task_id: str,
        agent: str,
        cost_usd: float,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        model: Optional[str] = None,
    ) -> None:
        """Record a spending event.

        Args:
            task_id: Task that incurred the cost
            agent: Agent that incurred the cost
            cost_usd: Cost in USD
            tokens_input: Input token count
            tokens_output: Output token count
            model: Model used
        """
        db = self._get_db_backend()
        run_async(
            db.record_spend(
                agent=agent,
                cost_usd=cost_usd,
                task_id=task_id,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                model=model,
            )
        )

    def get_task_spent(self, task_id: str) -> float:
        """Get total spent for a task.

        Args:
            task_id: Task identifier

        Returns:
            Total spent in USD
        """
        db = self._get_db_backend()
        return run_async(db.get_task_cost(task_id))

    def get_task_remaining(self, task_id: str) -> Optional[float]:
        """Get remaining budget for a task.

        Args:
            task_id: Task identifier

        Returns:
            Remaining budget in USD
        """
        spent = self.get_task_spent(task_id)
        remaining = self.task_budget_usd - spent
        return max(0.0, remaining)

    def can_spend(
        self,
        task_id: str,
        amount_usd: float,
        raise_on_exceeded: bool = False,
    ) -> bool:
        """Check if spending amount is within budget.

        Args:
            task_id: Task identifier
            amount_usd: Amount to spend
            raise_on_exceeded: Whether to raise if over limit

        Returns:
            True if within budget
        """
        remaining = self.get_task_remaining(task_id)
        if remaining is None:
            return True

        can_afford = amount_usd <= remaining

        if not can_afford and raise_on_exceeded:
            from orchestrator.agents.budget import BudgetExceeded

            raise BudgetExceeded(
                f"Task {task_id} budget exceeded. "
                f"Requested: ${amount_usd:.2f}, Remaining: ${remaining:.2f}"
            )

        return can_afford

    def get_invocation_budget(self, task_id: str, default: float = 1.0) -> float:
        """Get the per-invocation budget for a task.

        This returns the budget to pass to --max-budget-usd.

        Args:
            task_id: Task identifier
            default: Default budget if not configured

        Returns:
            Per-invocation budget in USD
        """
        # Check remaining budget
        remaining = self.get_task_remaining(task_id)
        if remaining is not None:
            # Don't exceed remaining budget
            return min(self.invocation_budget_usd, remaining)
        return self.invocation_budget_usd

    def get_summary(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> BudgetSummaryData:
        """Get budget summary.

        Args:
            since: Start time
            until: End time

        Returns:
            BudgetSummaryData summary
        """
        db = self._get_db_backend()
        summary = run_async(db.get_summary(since=since, until=until))
        return BudgetSummaryData(
            total_cost_usd=summary.total_cost_usd,
            total_tokens_input=summary.total_tokens_input,
            total_tokens_output=summary.total_tokens_output,
            record_count=summary.record_count,
            by_agent=summary.by_agent,
            by_task=summary.by_task,
            by_model=summary.by_model,
        )

    def get_total_spent(
        self,
        since: Optional[datetime] = None,
    ) -> float:
        """Get total amount spent.

        Args:
            since: Optional start time filter

        Returns:
            Total spent in USD
        """
        db = self._get_db_backend()
        return run_async(db.get_total_cost(since=since))

    def get_daily_costs(self, days: int = 7) -> list[dict]:
        """Get daily cost breakdown.

        Args:
            days: Number of days to include

        Returns:
            List of daily cost records
        """
        db = self._get_db_backend()
        return run_async(db.get_daily_costs(days))

    def get_project_remaining(self) -> float:
        """Get remaining project budget.

        Returns:
            Remaining budget in USD
        """
        total_spent = self.get_total_spent()
        return max(0.0, self.project_budget_usd - total_spent)

    def enforce_budget(
        self,
        task_id: str,
        amount_usd: float,
        soft_limit_percent: float = 90.0,
    ) -> dict[str, Any]:
        """Check budget with detailed result for workflow decisions.

        Args:
            task_id: Task identifier
            amount_usd: Amount to spend
            soft_limit_percent: Percentage at which to warn

        Returns:
            Dict with can_proceed, warning, remaining, etc.
        """
        task_spent = self.get_task_spent(task_id)
        task_remaining = self.task_budget_usd - task_spent
        project_remaining = self.get_project_remaining()

        # Calculate usage percentage
        task_usage_pct = (
            (task_spent / self.task_budget_usd) * 100 if self.task_budget_usd > 0 else 0
        )

        # Check if we can proceed
        can_proceed = amount_usd <= task_remaining and amount_usd <= project_remaining

        # Check for soft limit warning
        warning = None
        if task_usage_pct >= soft_limit_percent:
            warning = f"Task {task_id} is at {task_usage_pct:.1f}% of budget"

        return {
            "can_proceed": can_proceed,
            "warning": warning,
            "task_spent": task_spent,
            "task_remaining": task_remaining,
            "task_budget": self.task_budget_usd,
            "task_usage_percent": task_usage_pct,
            "project_remaining": project_remaining,
            "project_budget": self.project_budget_usd,
            "requested_amount": amount_usd,
        }


# Cache of adapters per project
_budget_adapters: dict[str, BudgetStorageAdapter] = {}


def get_budget_storage(
    project_dir: Path,
    project_name: Optional[str] = None,
) -> BudgetStorageAdapter:
    """Get or create budget storage adapter for a project.

    Args:
        project_dir: Project directory
        project_name: Project name (defaults to directory name)

    Returns:
        BudgetStorageAdapter instance
    """
    key = str(Path(project_dir).resolve())

    if key not in _budget_adapters:
        _budget_adapters[key] = BudgetStorageAdapter(project_dir, project_name)
    return _budget_adapters[key]
