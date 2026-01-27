"""Budget control for CLI invocations.

Tracks and limits API costs per:
- Invocation (via --max-budget-usd flag)
- Task (accumulated across invocations)
- Project (total project budget)

NOTE: This module is a thin wrapper around the storage adapter layer.
All budget data is stored in SurrealDB. There is no file-based fallback.

Usage:
    manager = BudgetManager(project_dir)

    # Check if invocation is within budget
    if manager.can_spend(task_id="T1", amount_usd=0.50):
        # Run the invocation
        result = agent.run(...)
        # Record the actual cost
        manager.record_spend(task_id="T1", amount_usd=actual_cost)

    # Get budget status
    status = manager.get_budget_status()
    print(f"Remaining: ${status['remaining_usd']:.2f}")

    # Set budget limits
    manager.set_task_budget("T1", max_usd=2.00)
    manager.set_project_budget(max_usd=50.00)

For direct access to storage, use:
    from orchestrator.storage import get_budget_storage
    budget_storage = get_budget_storage(project_dir)
"""

import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from orchestrator.storage.budget_adapter import BudgetStorageAdapter

logger = logging.getLogger(__name__)

# Default limits - set reasonable values to prevent runaway costs
DEFAULT_TASK_BUDGET_USD = 5.00  # $5 per task
DEFAULT_PROJECT_BUDGET_USD = 50.00  # $50 per workflow run
DEFAULT_INVOCATION_BUDGET_USD = 1.00  # Safety limit per invocation


@dataclass
class SpendRecord:
    """Record of a single spend event.

    Attributes:
        id: Unique record identifier
        timestamp: When the spend occurred
        task_id: Task that incurred the cost
        agent: Agent that incurred the cost
        amount_usd: Cost in USD
        model: Model used
        prompt_tokens: Input tokens (if known)
        completion_tokens: Output tokens (if known)
        metadata: Additional metadata
    """

    id: str
    timestamp: str
    task_id: str
    agent: str
    amount_usd: float
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SpendRecord":
        """Deserialize from storage."""
        return cls(**data)


@dataclass
class BudgetConfig:
    """Budget configuration.

    Attributes:
        project_budget_usd: Total project budget (None = unlimited)
        task_budget_usd: Default per-task budget (None = unlimited)
        invocation_budget_usd: Default per-invocation budget
        task_budgets: Per-task budget overrides
        warn_at_percent: Warn when budget reaches this percentage
        enabled: Whether budget tracking is enabled
    """

    project_budget_usd: Optional[float] = DEFAULT_PROJECT_BUDGET_USD
    task_budget_usd: Optional[float] = DEFAULT_TASK_BUDGET_USD
    invocation_budget_usd: float = DEFAULT_INVOCATION_BUDGET_USD
    task_budgets: dict[str, float] = field(default_factory=dict)
    warn_at_percent: float = 80.0
    enabled: bool = True

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BudgetConfig":
        """Deserialize from storage."""
        return cls(**data)


@dataclass
class BudgetState:
    """Current budget state.

    Attributes:
        total_spent_usd: Total amount spent
        task_spent: Spending by task
        records: Spend records
        config: Budget configuration
        updated_at: Last update timestamp
    """

    total_spent_usd: float = 0.0
    task_spent: dict[str, float] = field(default_factory=dict)
    records: list[dict] = field(default_factory=list)
    config: BudgetConfig = field(default_factory=BudgetConfig)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "total_spent_usd": self.total_spent_usd,
            "task_spent": self.task_spent,
            "records": self.records,
            "config": self.config.to_dict(),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BudgetState":
        """Deserialize from storage."""
        config = BudgetConfig.from_dict(data.get("config", {}))
        return cls(
            total_spent_usd=data.get("total_spent_usd", 0.0),
            task_spent=data.get("task_spent", {}),
            records=data.get("records", []),
            config=config,
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )


class BudgetExceeded(Exception):
    """Raised when an operation would exceed budget limits."""

    def __init__(
        self,
        limit_type: str,
        limit_usd: float,
        current_usd: float,
        requested_usd: float,
    ):
        self.limit_type = limit_type
        self.limit_usd = limit_usd
        self.current_usd = current_usd
        self.requested_usd = requested_usd
        super().__init__(
            f"{limit_type} budget exceeded: "
            f"limit=${limit_usd:.2f}, current=${current_usd:.2f}, "
            f"requested=${requested_usd:.2f}"
        )


@dataclass
class BudgetEnforcementResult:
    """Result of budget enforcement check.

    Used for workflow integration to decide whether to proceed,
    escalate, or abort based on budget status.

    Attributes:
        allowed: Whether the operation is allowed
        exceeded_type: Type of budget that was exceeded (None if allowed)
        limit_usd: The budget limit
        current_usd: Current spending
        requested_usd: Amount requested
        remaining_usd: Remaining budget (None if unlimited)
        should_escalate: Whether to escalate to human (soft limit)
        should_abort: Whether to abort workflow (hard limit)
        message: Human-readable message
    """

    allowed: bool
    exceeded_type: Optional[str] = None
    limit_usd: Optional[float] = None
    current_usd: float = 0.0
    requested_usd: float = 0.0
    remaining_usd: Optional[float] = None
    should_escalate: bool = False
    should_abort: bool = False
    message: str = ""

    def to_dict(self) -> dict:
        """Serialize for workflow state."""
        return asdict(self)


class BudgetManager:
    """Manages budget tracking and limits.

    Thread-safe budget tracking with SurrealDB persistence.
    All spend data is stored in SurrealDB via the storage adapter layer.
    Configuration is kept in memory and can be passed at construction.

    NOTE: This class is a thin wrapper around BudgetStorageAdapter.
    For new code, consider using the storage adapter directly:
        from orchestrator.storage import get_budget_storage
    """

    def __init__(
        self,
        project_dir: Path | str,
        budget_file: Optional[str] = None,  # Deprecated, ignored
        config: Optional[BudgetConfig] = None,
    ):
        """Initialize budget manager.

        Args:
            project_dir: Project directory
            budget_file: DEPRECATED - ignored, kept for backwards compatibility
            config: Optional configuration override
        """
        self.project_dir = Path(project_dir)
        self._lock = threading.Lock()
        self._record_counter = 0

        # Configuration is in-memory only
        self._config = config or BudgetConfig()

        # Lazily initialized storage adapter
        self._storage: Optional["BudgetStorageAdapter"] = None

        # Track task budgets in-memory (config overrides)
        self._task_budgets: dict[str, float] = {}

    def _get_storage(self) -> "BudgetStorageAdapter":
        """Get or create the storage adapter."""
        if self._storage is None:
            from orchestrator.storage import get_budget_storage

            self._storage = get_budget_storage(
                self.project_dir,
                project_name=self.project_dir.name,
            )
            # Apply our config to the adapter
            self._storage.project_budget_usd = (
                self._config.project_budget_usd or DEFAULT_PROJECT_BUDGET_USD
            )
            self._storage.task_budget_usd = self._config.task_budget_usd or DEFAULT_TASK_BUDGET_USD
            self._storage.invocation_budget_usd = self._config.invocation_budget_usd
        return self._storage

    @property
    def config(self) -> BudgetConfig:
        """Get current configuration."""
        return self._config

    def set_project_budget(self, max_usd: Optional[float]) -> None:
        """Set the project-wide budget limit.

        Args:
            max_usd: Maximum budget in USD (None = unlimited)
        """
        with self._lock:
            self._config.project_budget_usd = max_usd
            if self._storage:
                self._storage.project_budget_usd = max_usd or DEFAULT_PROJECT_BUDGET_USD
            logger.info(
                f"Set project budget: ${max_usd:.2f}"
                if max_usd
                else "Set project budget: unlimited"
            )

    def set_task_budget(self, task_id: str, max_usd: Optional[float]) -> None:
        """Set budget limit for a specific task.

        Args:
            task_id: Task identifier
            max_usd: Maximum budget in USD (None = remove limit)
        """
        with self._lock:
            if max_usd is None:
                self._task_budgets.pop(task_id, None)
            else:
                self._task_budgets[task_id] = max_usd
            logger.info(
                f"Set task {task_id} budget: ${max_usd:.2f}"
                if max_usd
                else f"Removed task {task_id} budget limit"
            )

    def set_default_task_budget(self, max_usd: Optional[float]) -> None:
        """Set default budget for all tasks.

        Args:
            max_usd: Default maximum budget in USD (None = unlimited)
        """
        with self._lock:
            self._config.task_budget_usd = max_usd
            if self._storage:
                self._storage.task_budget_usd = max_usd or DEFAULT_TASK_BUDGET_USD

    def set_invocation_budget(self, max_usd: float) -> None:
        """Set default per-invocation budget limit.

        This is the value passed to --max-budget-usd.

        Args:
            max_usd: Maximum budget per invocation in USD
        """
        with self._lock:
            self._config.invocation_budget_usd = max_usd
            if self._storage:
                self._storage.invocation_budget_usd = max_usd

    def get_task_budget(self, task_id: str) -> Optional[float]:
        """Get budget limit for a task.

        Args:
            task_id: Task identifier

        Returns:
            Budget limit in USD, or None if unlimited
        """
        # Check for task-specific override
        if task_id in self._task_budgets:
            return self._task_budgets[task_id]
        # Fall back to default
        return self._config.task_budget_usd

    def get_invocation_budget(self, task_id: Optional[str] = None) -> float:
        """Get the budget for a single invocation.

        Args:
            task_id: Optional task ID for context

        Returns:
            Budget limit in USD for --max-budget-usd
        """
        storage = self._get_storage()
        if task_id:
            return storage.get_invocation_budget(task_id)
        return self._config.invocation_budget_usd

    def get_task_spent(self, task_id: str) -> float:
        """Get amount spent on a task.

        Args:
            task_id: Task identifier

        Returns:
            Total spent in USD
        """
        storage = self._get_storage()
        return storage.get_task_spent(task_id)

    def get_task_remaining(self, task_id: str) -> Optional[float]:
        """Get remaining budget for a task.

        Args:
            task_id: Task identifier

        Returns:
            Remaining budget in USD, or None if unlimited
        """
        budget = self.get_task_budget(task_id)
        if budget is None:
            return None
        spent = self.get_task_spent(task_id)
        return max(0, budget - spent)

    def get_project_remaining(self) -> Optional[float]:
        """Get remaining project budget.

        Returns:
            Remaining budget in USD, or None if unlimited
        """
        budget = self._config.project_budget_usd
        if budget is None:
            return None
        storage = self._get_storage()
        return storage.get_project_remaining()

    def can_spend(
        self,
        task_id: str,
        amount_usd: float,
        raise_on_exceeded: bool = False,
    ) -> bool:
        """Check if an amount can be spent.

        Args:
            task_id: Task identifier
            amount_usd: Amount to spend
            raise_on_exceeded: Whether to raise BudgetExceeded

        Returns:
            True if spend is within budget

        Raises:
            BudgetExceeded: If raise_on_exceeded and budget would be exceeded
        """
        storage = self._get_storage()

        # Check project budget
        project_budget = self._config.project_budget_usd
        if project_budget is not None:
            total_spent = storage.get_total_spent()
            if total_spent + amount_usd > project_budget:
                if raise_on_exceeded:
                    raise BudgetExceeded(
                        "project",
                        project_budget,
                        total_spent,
                        amount_usd,
                    )
                return False

        # Check task budget
        task_budget = self.get_task_budget(task_id)
        if task_budget is not None:
            task_spent = self.get_task_spent(task_id)
            if task_spent + amount_usd > task_budget:
                if raise_on_exceeded:
                    raise BudgetExceeded(
                        f"task:{task_id}",
                        task_budget,
                        task_spent,
                        amount_usd,
                    )
                return False

        return True

    def require_budget(self, task_id: str, amount_usd: float) -> None:
        """Require budget to be available, raising if exceeded.

        Use this for hard enforcement - will always raise BudgetExceeded
        if the budget would be exceeded.

        Args:
            task_id: Task identifier
            amount_usd: Amount to spend

        Raises:
            BudgetExceeded: If budget would be exceeded
        """
        self.can_spend(task_id, amount_usd, raise_on_exceeded=True)

    def enforce_budget(
        self,
        task_id: str,
        amount_usd: float,
        soft_limit_percent: float = 90.0,
    ) -> BudgetEnforcementResult:
        """Check budget with detailed result for workflow decisions.

        This method provides a structured result that can be used by
        the workflow to decide how to proceed:
        - allowed=True: Proceed normally
        - should_escalate=True: Escalate to human for approval
        - should_abort=True: Hard stop, workflow should not continue

        Args:
            task_id: Task identifier
            amount_usd: Amount to spend
            soft_limit_percent: Percentage at which to escalate (default 90%)

        Returns:
            BudgetEnforcementResult with detailed status
        """
        storage = self._get_storage()

        # Check project budget
        project_budget = self._config.project_budget_usd
        if project_budget is not None:
            project_spent = storage.get_total_spent()
            project_remaining = project_budget - project_spent

            if project_spent + amount_usd > project_budget:
                return BudgetEnforcementResult(
                    allowed=False,
                    exceeded_type="project",
                    limit_usd=project_budget,
                    current_usd=project_spent,
                    requested_usd=amount_usd,
                    remaining_usd=max(0, project_remaining),
                    should_escalate=True,
                    should_abort=project_remaining <= 0,  # Hard abort if nothing left
                    message=(
                        f"Project budget exceeded: ${project_spent:.2f} spent "
                        f"of ${project_budget:.2f} limit, "
                        f"requested ${amount_usd:.2f}"
                    ),
                )

            # Check if approaching soft limit (escalate for approval)
            if (project_spent / project_budget * 100) >= soft_limit_percent:
                return BudgetEnforcementResult(
                    allowed=True,
                    limit_usd=project_budget,
                    current_usd=project_spent,
                    requested_usd=amount_usd,
                    remaining_usd=project_remaining,
                    should_escalate=True,  # Ask human for approval
                    should_abort=False,
                    message=(
                        f"Project budget at {project_spent/project_budget*100:.1f}%: "
                        f"${project_remaining:.2f} remaining"
                    ),
                )

        # Check task budget
        task_budget = self.get_task_budget(task_id)
        if task_budget is not None:
            task_spent = self.get_task_spent(task_id)
            task_remaining = task_budget - task_spent

            if task_spent + amount_usd > task_budget:
                return BudgetEnforcementResult(
                    allowed=False,
                    exceeded_type=f"task:{task_id}",
                    limit_usd=task_budget,
                    current_usd=task_spent,
                    requested_usd=amount_usd,
                    remaining_usd=max(0, task_remaining),
                    should_escalate=True,
                    should_abort=task_remaining <= 0,
                    message=(
                        f"Task {task_id} budget exceeded: ${task_spent:.2f} spent "
                        f"of ${task_budget:.2f} limit, "
                        f"requested ${amount_usd:.2f}"
                    ),
                )

        # All checks passed
        project_remaining = self.get_project_remaining()
        total_spent = storage.get_total_spent()
        return BudgetEnforcementResult(
            allowed=True,
            current_usd=total_spent,
            requested_usd=amount_usd,
            remaining_usd=project_remaining,
            should_escalate=False,
            should_abort=False,
            message="Budget check passed",
        )

    def is_budget_exceeded(self, task_id: Optional[str] = None) -> bool:
        """Quick check if any budget is currently exceeded.

        Args:
            task_id: Optional task ID to also check task budget

        Returns:
            True if any budget limit is exceeded
        """
        storage = self._get_storage()

        project_budget = self._config.project_budget_usd
        if project_budget is not None:
            total_spent = storage.get_total_spent()
            if total_spent >= project_budget:
                return True

        if task_id:
            task_budget = self.get_task_budget(task_id)
            if task_budget is not None:
                task_spent = self.get_task_spent(task_id)
                if task_spent >= task_budget:
                    return True

        return False

    def get_enforcement_status(self) -> dict[str, Any]:
        """Get current enforcement status for workflow state.

        Returns summary suitable for including in workflow state updates.

        Returns:
            Enforcement status dictionary
        """
        storage = self._get_storage()

        project_budget = self._config.project_budget_usd
        total_spent = storage.get_total_spent()
        project_remaining = self.get_project_remaining()

        return {
            "budget_enabled": self._config.enabled,
            "project_budget_usd": project_budget,
            "project_spent_usd": total_spent,
            "project_remaining_usd": project_remaining,
            "project_exceeded": (project_budget is not None and total_spent >= project_budget),
            "project_percent_used": (total_spent / project_budget * 100 if project_budget else 0),
            "task_budgets_set": len(self._task_budgets),
            "default_task_budget_usd": self._config.task_budget_usd,
            "invocation_budget_usd": self._config.invocation_budget_usd,
        }

    def record_spend(
        self,
        task_id: str,
        agent: str,
        amount_usd: float,
        model: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> SpendRecord:
        """Record a spend event.

        Args:
            task_id: Task that incurred the cost
            agent: Agent that incurred the cost
            amount_usd: Cost in USD
            model: Model used
            prompt_tokens: Input tokens
            completion_tokens: Output tokens
            metadata: Additional metadata

        Returns:
            Created SpendRecord
        """
        with self._lock:
            storage = self._get_storage()

            # Record via storage adapter (persisted to SurrealDB)
            storage.record_spend(
                task_id=task_id,
                agent=agent,
                cost_usd=amount_usd,
                tokens_input=prompt_tokens,
                tokens_output=completion_tokens,
                model=model,
            )

            # Create SpendRecord for return value (backwards compatibility)
            self._record_counter += 1
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            record = SpendRecord(
                id=f"spend-{timestamp}-{self._record_counter:04d}",
                timestamp=datetime.now().isoformat(),
                task_id=task_id,
                agent=agent,
                amount_usd=amount_usd,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                metadata=metadata or {},
            )

            logger.debug(f"Recorded spend: ${amount_usd:.4f} for {task_id}")

            # Check for warning threshold
            self._check_warning_thresholds(task_id)

            return record

    def _check_warning_thresholds(self, task_id: str) -> None:
        """Check and log warning if approaching budget limits."""
        storage = self._get_storage()
        warn_percent = self._config.warn_at_percent / 100

        # Check project budget
        project_budget = self._config.project_budget_usd
        total_spent = storage.get_total_spent()
        if project_budget and total_spent >= project_budget * warn_percent:
            remaining = project_budget - total_spent
            logger.warning(
                f"Project budget warning: ${remaining:.2f} remaining "
                f"({100 - total_spent / project_budget * 100:.1f}% left)"
            )

        # Check task budget
        task_budget = self.get_task_budget(task_id)
        task_spent = self.get_task_spent(task_id)
        if task_budget and task_spent >= task_budget * warn_percent:
            remaining = task_budget - task_spent
            logger.warning(
                f"Task {task_id} budget warning: ${remaining:.2f} remaining "
                f"({100 - task_spent / task_budget * 100:.1f}% left)"
            )

    def get_budget_status(self) -> dict[str, Any]:
        """Get comprehensive budget status.

        Returns:
            Budget status dictionary
        """
        storage = self._get_storage()
        summary = storage.get_summary()

        project_budget = self._config.project_budget_usd
        project_remaining = self.get_project_remaining()

        return {
            "total_spent_usd": summary.total_cost_usd,
            "project_budget_usd": project_budget,
            "project_remaining_usd": project_remaining,
            "project_used_percent": (
                summary.total_cost_usd / project_budget * 100 if project_budget else None
            ),
            "task_count": len(summary.by_task),
            "record_count": summary.record_count,
            "task_spent": dict(summary.by_task),
            "updated_at": datetime.now().isoformat(),
            "enabled": self._config.enabled,
        }

    def get_task_spending_report(self) -> list[dict[str, Any]]:
        """Get spending report by task.

        Returns:
            List of task spending summaries
        """
        storage = self._get_storage()
        summary = storage.get_summary()

        report = []
        for task_id, spent in summary.by_task.items():
            budget = self.get_task_budget(task_id)
            remaining = budget - spent if budget else None

            report.append(
                {
                    "task_id": task_id,
                    "spent_usd": spent,
                    "budget_usd": budget,
                    "remaining_usd": remaining,
                    "used_percent": spent / budget * 100 if budget else None,
                }
            )

        return sorted(report, key=lambda x: x["spent_usd"], reverse=True)

    def reset_task_spending(self, task_id: str, hard_delete: bool = False) -> bool:
        """Reset spending for a specific task.

        By default uses soft delete strategy: creates a reset record with
        negative cost that zeros out the balance while preserving audit history.

        Args:
            task_id: Task identifier
            hard_delete: If True, permanently delete records (no audit trail)

        Returns:
            True if spending was reset, False if no spending existed
        """
        from orchestrator.storage.async_utils import run_async

        with self._lock:
            storage = self._get_storage()
            db = storage._get_db_backend()

            if hard_delete:
                count = run_async(db.delete_task_records(task_id))
                logger.info(f"Hard deleted {count} budget records for task {task_id}")
            else:
                count = run_async(db.reset_task_spending(task_id))
                logger.info(f"Reset spending for task {task_id} (soft delete)")

            return count > 0

    def reset_all(self, hard_delete: bool = False) -> int:
        """Reset all spending records.

        By default uses soft delete strategy: creates reset records with
        negative costs that zero out all balances while preserving audit history.

        Args:
            hard_delete: If True, permanently delete all records (no audit trail)

        Returns:
            Number of tasks/records reset
        """
        from orchestrator.storage.async_utils import run_async

        with self._lock:
            storage = self._get_storage()
            db = storage._get_db_backend()

            if hard_delete:
                count = run_async(db.delete_all_records())
                logger.warning(f"Hard deleted {count} budget records")
            else:
                count = run_async(db.reset_all_spending())
                logger.info(f"Reset spending for {count} tasks (soft delete)")

            return count


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    agent: str = "claude",
) -> float:
    """Estimate cost for an API call.

    Supports Claude, Cursor, and Gemini models with 2026 pricing.

    Args:
        model: Model name
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        agent: Agent type (claude, cursor, gemini)

    Returns:
        Estimated cost in USD
    """
    # Pricing per 1M tokens (approximate 2026 rates)
    pricing = {
        # Claude models
        "claude-opus-4": {"input": 15.0, "output": 75.0},
        "claude-opus-4-5": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4": {"input": 3.0, "output": 15.0},
        "claude-haiku-3.5": {"input": 0.80, "output": 4.0},
        # Claude fallbacks
        "opus": {"input": 15.0, "output": 75.0},
        "sonnet": {"input": 3.0, "output": 15.0},
        "haiku": {"input": 0.80, "output": 4.0},
        # Cursor models
        "codex-5.2": {"input": 5.0, "output": 15.0},
        "composer": {"input": 3.0, "output": 10.0},
        # Gemini models
        "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.0-pro": {"input": 1.25, "output": 5.0},
        "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
        "gemini-2.5-pro": {"input": 2.50, "output": 10.0},
    }

    # Normalize model name
    model_lower = model.lower() if model else ""
    model_prices = None

    for key, prices in pricing.items():
        if key in model_lower:
            model_prices = prices
            break

    if model_prices is None:
        # Default based on agent type
        agent_defaults = {
            "claude": pricing["sonnet"],
            "cursor": pricing["codex-5.2"],
            "gemini": pricing["gemini-2.0-flash"],
        }
        model_prices = agent_defaults.get(agent.lower(), pricing["sonnet"])

    input_cost = (prompt_tokens / 1_000_000) * model_prices["input"]
    output_cost = (completion_tokens / 1_000_000) * model_prices["output"]

    return input_cost + output_cost


# Agent pricing lookup table for quick access
AGENT_PRICING = {
    "claude": {
        "sonnet": {"input": 3.0, "output": 15.0},
        "opus": {"input": 15.0, "output": 75.0},
        "haiku": {"input": 0.80, "output": 4.0},
    },
    "cursor": {
        "codex-5.2": {"input": 5.0, "output": 15.0},
        "composer": {"input": 3.0, "output": 10.0},
    },
    "gemini": {
        "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.0-pro": {"input": 1.25, "output": 5.0},
    },
}


def get_model_pricing(agent: str, model: str) -> dict[str, float]:
    """Get pricing for a specific agent and model.

    Args:
        agent: Agent type (claude, cursor, gemini)
        model: Model name

    Returns:
        Dict with 'input' and 'output' costs per 1M tokens
    """
    agent_prices = AGENT_PRICING.get(agent.lower(), {})
    model_prices = agent_prices.get(model.lower())

    if model_prices:
        return model_prices

    # Fall back to first model in agent's pricing
    if agent_prices:
        return next(iter(agent_prices.values()))

    # Ultimate fallback to Claude sonnet
    return AGENT_PRICING["claude"]["sonnet"]
