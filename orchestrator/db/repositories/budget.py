"""Budget repository.

Provides cost tracking and budget management.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from ..connection import get_connection
from .base import BaseRepository

logger = logging.getLogger(__name__)


@dataclass
class BudgetRecord:
    """Budget record for cost tracking.

    Note: project_name removed in schema v2.0.0 (per-project database isolation).
    """

    task_id: Optional[str]
    agent: str
    cost_usd: float
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    model: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "agent": self.agent,
            "cost_usd": self.cost_usd,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "model": self.model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BudgetRecord":
        """Create from dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        return cls(
            task_id=data.get("task_id"),
            agent=data.get("agent", ""),
            cost_usd=data.get("cost_usd", 0.0),
            tokens_input=data.get("tokens_input"),
            tokens_output=data.get("tokens_output"),
            model=data.get("model"),
            created_at=created_at,
        )


@dataclass
class BudgetSummary:
    """Budget summary with breakdowns."""

    total_cost_usd: float = 0.0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    record_count: int = 0
    by_agent: dict[str, float] = None
    by_task: dict[str, float] = None
    by_model: dict[str, float] = None

    def __post_init__(self):
        if self.by_agent is None:
            self.by_agent = {}
        if self.by_task is None:
            self.by_task = {}
        if self.by_model is None:
            self.by_model = {}


class BudgetRepository(BaseRepository[BudgetRecord]):
    """Repository for budget tracking."""

    table_name = "budget_records"

    def _to_record(self, data: dict[str, Any]) -> BudgetRecord:
        return BudgetRecord.from_dict(data)

    def _from_record(self, record: BudgetRecord) -> dict[str, Any]:
        return record.to_dict()

    async def record_spend(
        self,
        agent: str,
        cost_usd: float,
        task_id: Optional[str] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        model: Optional[str] = None,
    ) -> BudgetRecord:
        """Record a spend event.

        Note: Database is already scoped to project (schema v2.0.0).

        Args:
            agent: Agent identifier
            cost_usd: Cost in USD
            task_id: Optional task identifier
            tokens_input: Input token count
            tokens_output: Output token count
            model: Model used

        Returns:
            Created budget record
        """
        record = BudgetRecord(
            task_id=task_id,
            agent=agent,
            cost_usd=cost_usd,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            model=model,
            created_at=datetime.now(),
        )

        await self.create(record.to_dict())

        logger.debug(f"Recorded spend: ${cost_usd:.4f} for {agent}")
        return record

    async def get_total_cost(
        self,
        task_id: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> float:
        """Get total cost.

        Args:
            task_id: Optional task filter
            since: Optional time filter

        Returns:
            Total cost in USD
        """
        params: dict[str, Any] = {}
        where_clauses = []

        if task_id:
            where_clauses.append("task_id = $task_id")
            params["task_id"] = task_id

        if since:
            where_clauses.append("created_at >= $since")
            params["since"] = since.isoformat()

        where = " AND ".join(where_clauses) if where_clauses else "true"

        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT math::sum(cost_usd) as total
                FROM budget_records
                WHERE {where}
                GROUP ALL
                """,
                params,
            )

            if results:
                return results[0].get("total", 0) or 0
            return 0

    async def get_task_cost(self, task_id: str) -> float:
        """Get total cost for a task.

        Args:
            task_id: Task identifier

        Returns:
            Task cost in USD
        """
        return await self.get_total_cost(task_id=task_id)

    async def get_remaining_budget(
        self,
        budget_limit: float,
        task_id: Optional[str] = None,
    ) -> float:
        """Get remaining budget.

        Args:
            budget_limit: Budget limit in USD
            task_id: Optional task filter

        Returns:
            Remaining budget in USD
        """
        spent = await self.get_total_cost(task_id=task_id)
        return max(0, budget_limit - spent)

    async def can_spend(
        self,
        amount: float,
        budget_limit: float,
        task_id: Optional[str] = None,
    ) -> bool:
        """Check if spending amount is within budget.

        Args:
            amount: Amount to spend
            budget_limit: Budget limit
            task_id: Optional task filter

        Returns:
            True if within budget
        """
        remaining = await self.get_remaining_budget(budget_limit, task_id)
        return amount <= remaining

    async def get_summary(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> BudgetSummary:
        """Get budget summary with breakdowns.

        Args:
            since: Start time
            until: End time

        Returns:
            BudgetSummary
        """
        params: dict[str, Any] = {}
        where_clauses = []

        if since:
            where_clauses.append("created_at >= $since")
            params["since"] = since.isoformat()

        if until:
            where_clauses.append("created_at < $until")
            params["until"] = until.isoformat()

        where = " AND ".join(where_clauses) if where_clauses else "true"

        async with get_connection(self.project_name) as conn:
            # Get totals
            total_results = await conn.query(
                f"""
                SELECT
                    count() as count,
                    math::sum(cost_usd) as total_cost,
                    math::sum(tokens_input) as total_input,
                    math::sum(tokens_output) as total_output
                FROM budget_records
                WHERE {where}
                GROUP ALL
                """,
                params,
            )

            summary = BudgetSummary()
            if total_results:
                row = total_results[0]
                summary.total_cost_usd = row.get("total_cost", 0) or 0
                summary.total_tokens_input = row.get("total_input", 0) or 0
                summary.total_tokens_output = row.get("total_output", 0) or 0
                summary.record_count = row.get("count", 0)

            # By agent
            agent_results = await conn.query(
                f"""
                SELECT agent, math::sum(cost_usd) as total
                FROM budget_records
                WHERE {where}
                GROUP BY agent
                """,
                params,
            )
            summary.by_agent = {
                r.get("agent", "unknown"): r.get("total", 0) or 0 for r in agent_results
            }

            # By task
            task_filter = f"{where} AND task_id != NONE" if where != "true" else "task_id != NONE"
            task_results = await conn.query(
                f"""
                SELECT task_id, math::sum(cost_usd) as total
                FROM budget_records
                WHERE {task_filter}
                GROUP BY task_id
                """,
                params,
            )
            summary.by_task = {
                r.get("task_id", "unknown"): r.get("total", 0) or 0 for r in task_results
            }

            # By model
            model_filter = f"{where} AND model != NONE" if where != "true" else "model != NONE"
            model_results = await conn.query(
                f"""
                SELECT model, math::sum(cost_usd) as total
                FROM budget_records
                WHERE {model_filter}
                GROUP BY model
                """,
                params,
            )
            summary.by_model = {
                r.get("model", "unknown"): r.get("total", 0) or 0 for r in model_results
            }

            return summary

    async def get_daily_costs(
        self,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """Get daily cost breakdown.

        Args:
            days: Number of days to include

        Returns:
            List of daily cost records
        """
        since = datetime.now() - timedelta(days=days)

        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT
                    time::floor(created_at, 1d) as date,
                    math::sum(cost_usd) as cost,
                    count() as invocations
                FROM budget_records
                WHERE created_at >= $since
                GROUP BY date
                ORDER BY date ASC
                """,
                {"since": since.isoformat()},
            )

            return [
                {
                    "date": r.get("date"),
                    "cost_usd": r.get("cost", 0) or 0,
                    "invocations": r.get("invocations", 0),
                }
                for r in results
            ]

    async def reset_task_spending(self, task_id: str) -> int:
        """Reset (delete) all spending records for a specific task.

        Uses soft delete strategy: creates a reset record with negative cost
        that zeroes out the balance while preserving the audit history.

        Args:
            task_id: Task identifier

        Returns:
            Number of records affected (always 1 if task had spending)
        """
        # Get current task spending
        current_spent = await self.get_task_cost(task_id)

        if current_spent <= 0:
            logger.debug(f"No spending to reset for task {task_id}")
            return 0

        # Create a reset record with negative cost to zero out the balance
        # This preserves audit trail while effectively resetting spending
        reset_record = BudgetRecord(
            task_id=task_id,
            agent="system_reset",
            cost_usd=-current_spent,  # Negative to cancel out
            model=None,
            tokens_input=None,
            tokens_output=None,
            created_at=datetime.now(),
        )

        await self.create(reset_record.to_dict())
        logger.info(f"Reset spending for task {task_id}: ${current_spent:.4f} zeroed out")

        return 1

    async def reset_all_spending(self) -> int:
        """Reset (delete) all spending records.

        Uses soft delete strategy: creates reset records with negative costs
        that zero out all task balances while preserving the audit history.

        Returns:
            Number of tasks reset
        """
        # Get all task spending
        summary = await self.get_summary()

        if not summary.by_task:
            logger.debug("No spending to reset")
            return 0

        reset_count = 0
        for task_id, spent in summary.by_task.items():
            if spent > 0:
                # Create reset record for each task
                reset_record = BudgetRecord(
                    task_id=task_id,
                    agent="system_reset",
                    cost_usd=-spent,
                    model=None,
                    tokens_input=None,
                    tokens_output=None,
                    created_at=datetime.now(),
                )
                await self.create(reset_record.to_dict())
                reset_count += 1

        # Also handle any spending not associated with a task
        total_without_task = summary.total_cost_usd - sum(summary.by_task.values())
        if total_without_task > 0:
            reset_record = BudgetRecord(
                task_id=None,
                agent="system_reset",
                cost_usd=-total_without_task,
                model=None,
                tokens_input=None,
                tokens_output=None,
                created_at=datetime.now(),
            )
            await self.create(reset_record.to_dict())
            reset_count += 1

        logger.info(f"Reset all spending: {reset_count} tasks zeroed out")
        return reset_count

    async def delete_task_records(self, task_id: str) -> int:
        """Permanently delete all spending records for a task (hard delete).

        WARNING: This permanently removes data and cannot be undone.
        Prefer reset_task_spending() for audit trail preservation.

        Args:
            task_id: Task identifier

        Returns:
            Number of records deleted
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                "DELETE FROM budget_records WHERE task_id = $task_id RETURN BEFORE",
                {"task_id": task_id},
            )
            count = len(results) if results else 0
            logger.warning(f"Hard deleted {count} budget records for task {task_id}")
            return count

    async def delete_all_records(self) -> int:
        """Permanently delete all spending records (hard delete).

        WARNING: This permanently removes ALL data and cannot be undone.
        Prefer reset_all_spending() for audit trail preservation.

        Returns:
            Number of records deleted
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query("DELETE FROM budget_records RETURN BEFORE")
            count = len(results) if results else 0
            logger.warning(f"Hard deleted {count} budget records")
            return count


# Global repository cache
_budget_repos: dict[str, BudgetRepository] = {}


def get_budget_repository(project_name: str) -> BudgetRepository:
    """Get or create budget repository for a project.

    Args:
        project_name: Project name

    Returns:
        BudgetRepository instance
    """
    if project_name not in _budget_repos:
        _budget_repos[project_name] = BudgetRepository(project_name)
    return _budget_repos[project_name]
