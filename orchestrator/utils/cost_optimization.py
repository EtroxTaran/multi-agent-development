"""Cost optimization utilities for multi-agent workflows.

Implements:
- Token usage tracking and budgeting
- Intelligent model routing (route to cheapest capable model)
- Cost forecasting and reporting
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """Task complexity levels for model routing."""

    TRIVIAL = "trivial"  # Simple validation, formatting
    SIMPLE = "simple"  # Basic code review, simple analysis
    MODERATE = "moderate"  # Standard implementation, debugging
    COMPLEX = "complex"  # Architecture design, security analysis
    EXPERT = "expert"  # Critical decisions, novel problems


@dataclass
class ModelSpec:
    """Specification for an LLM model."""

    name: str
    provider: str
    input_cost_per_1k: float  # Cost per 1K input tokens
    output_cost_per_1k: float  # Cost per 1K output tokens
    context_window: int  # Maximum context size
    capabilities: list[str]  # What this model is good at
    complexity_threshold: TaskComplexity  # Minimum complexity it handles well
    latency_ms: int  # Typical response latency

    @property
    def avg_cost_per_1k(self) -> float:
        """Average cost assuming 1:1 input:output ratio."""
        return (self.input_cost_per_1k + self.output_cost_per_1k) / 2


# Model registry with current pricing (Jan 2026)
MODEL_REGISTRY: dict[str, ModelSpec] = {
    # OpenAI / Cursor models
    "gpt-5.2-codex": ModelSpec(
        name="gpt-5.2-codex",
        provider="openai",
        input_cost_per_1k=0.012,
        output_cost_per_1k=0.036,
        context_window=256000,
        capabilities=["code", "security", "debugging", "architecture"],
        complexity_threshold=TaskComplexity.COMPLEX,
        latency_ms=2000,
    ),
    "gpt-5.1-codex": ModelSpec(
        name="gpt-5.1-codex",
        provider="openai",
        input_cost_per_1k=0.008,
        output_cost_per_1k=0.024,
        context_window=256000,
        capabilities=["code", "security", "debugging"],
        complexity_threshold=TaskComplexity.MODERATE,
        latency_ms=1500,
    ),
    "gpt-4.5-turbo": ModelSpec(
        name="gpt-4.5-turbo",
        provider="openai",
        input_cost_per_1k=0.005,
        output_cost_per_1k=0.015,
        context_window=128000,
        capabilities=["code", "general"],
        complexity_threshold=TaskComplexity.SIMPLE,
        latency_ms=1000,
    ),
    # Google / Gemini models
    "gemini-3-pro": ModelSpec(
        name="gemini-3-pro",
        provider="google",
        input_cost_per_1k=0.00125,
        output_cost_per_1k=0.005,
        context_window=1000000,
        capabilities=["architecture", "scalability", "patterns", "reasoning"],
        complexity_threshold=TaskComplexity.COMPLEX,
        latency_ms=2500,
    ),
    "gemini-3-flash": ModelSpec(
        name="gemini-3-flash",
        provider="google",
        input_cost_per_1k=0.000075,
        output_cost_per_1k=0.0003,
        context_window=1000000,
        capabilities=["validation", "formatting", "simple-analysis"],
        complexity_threshold=TaskComplexity.TRIVIAL,
        latency_ms=500,
    ),
    # Anthropic / Claude models
    "claude-opus-4.5": ModelSpec(
        name="claude-opus-4.5",
        provider="anthropic",
        input_cost_per_1k=0.015,
        output_cost_per_1k=0.075,
        context_window=200000,
        capabilities=["planning", "reasoning", "code", "architecture"],
        complexity_threshold=TaskComplexity.EXPERT,
        latency_ms=3000,
    ),
    "claude-sonnet-4": ModelSpec(
        name="claude-sonnet-4",
        provider="anthropic",
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
        context_window=200000,
        capabilities=["code", "analysis", "general"],
        complexity_threshold=TaskComplexity.MODERATE,
        latency_ms=1500,
    ),
}


@dataclass
class TokenUsage:
    """Token usage for a single API call."""

    model: str
    input_tokens: int
    output_tokens: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    task_type: str = "unknown"
    phase: Optional[int] = None
    cost: float = 0.0

    def __post_init__(self):
        if self.cost == 0.0:
            self.cost = self.calculate_cost()

    def calculate_cost(self) -> float:
        """Calculate cost based on model pricing."""
        spec = MODEL_REGISTRY.get(self.model)
        if not spec:
            # Default pricing
            return (self.input_tokens / 1000 * 0.01) + (self.output_tokens / 1000 * 0.03)

        input_cost = (self.input_tokens / 1000) * spec.input_cost_per_1k
        output_cost = (self.output_tokens / 1000) * spec.output_cost_per_1k
        return input_cost + output_cost

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TokenUsage":
        return cls(**data)


@dataclass
class UsageSummary:
    """Summary of token usage over a period."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    total_calls: int = 0
    by_model: dict = field(default_factory=dict)
    by_phase: dict = field(default_factory=dict)
    by_task_type: dict = field(default_factory=dict)
    period_start: Optional[str] = None
    period_end: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class TokenTracker:
    """Tracks token usage across the workflow.

    Provides:
    - Per-call tracking
    - Aggregated statistics
    - Budget enforcement
    - Cost forecasting
    """

    def __init__(
        self,
        storage_dir: str | Path,
        budget_limit: Optional[float] = None,
    ):
        """Initialize token tracker.

        Args:
            storage_dir: Directory to store usage data
            budget_limit: Optional budget limit in dollars
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.budget_limit = budget_limit
        self._usage_log: list[TokenUsage] = []
        self._load_usage()

    def _get_usage_file(self) -> Path:
        return self.storage_dir / "token_usage.json"

    def _load_usage(self) -> None:
        """Load usage history from disk."""
        usage_file = self._get_usage_file()
        if usage_file.exists():
            try:
                with open(usage_file) as f:
                    data = json.load(f)
                self._usage_log = [TokenUsage.from_dict(u) for u in data.get("usage", [])]
            except (json.JSONDecodeError, KeyError):
                self._usage_log = []

    def _save_usage(self) -> None:
        """Persist usage to disk."""
        usage_file = self._get_usage_file()
        data = {
            "usage": [u.to_dict() for u in self._usage_log],
            "saved_at": datetime.now().isoformat(),
        }
        with open(usage_file, "w") as f:
            json.dump(data, f, indent=2)

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_type: str = "unknown",
        phase: Optional[int] = None,
    ) -> TokenUsage:
        """Record token usage for an API call.

        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            task_type: Type of task (validation, implementation, etc.)
            phase: Workflow phase number

        Returns:
            TokenUsage record
        """
        usage = TokenUsage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            task_type=task_type,
            phase=phase,
        )

        self._usage_log.append(usage)
        self._save_usage()

        logger.info(
            f"Token usage: {model} - {input_tokens}in/{output_tokens}out = ${usage.cost:.4f}"
        )

        return usage

    def get_total_cost(self, since: Optional[datetime] = None) -> float:
        """Get total cost, optionally filtered by time.

        Args:
            since: Only count usage after this time

        Returns:
            Total cost in dollars
        """
        if since is None:
            return sum(u.cost for u in self._usage_log)

        return sum(u.cost for u in self._usage_log if datetime.fromisoformat(u.timestamp) >= since)

    def check_budget(self, estimated_cost: float = 0.0) -> tuple[bool, float]:
        """Check if within budget.

        Args:
            estimated_cost: Estimated cost for next call

        Returns:
            Tuple of (within_budget, remaining_budget)
        """
        if self.budget_limit is None:
            return True, float("inf")

        total = self.get_total_cost()
        remaining = self.budget_limit - total

        return (total + estimated_cost) <= self.budget_limit, remaining

    def get_summary(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> UsageSummary:
        """Get usage summary for a period.

        Args:
            since: Start of period
            until: End of period

        Returns:
            UsageSummary with aggregated statistics
        """
        filtered = self._usage_log

        if since:
            filtered = [u for u in filtered if datetime.fromisoformat(u.timestamp) >= since]
        if until:
            filtered = [u for u in filtered if datetime.fromisoformat(u.timestamp) <= until]

        summary = UsageSummary(
            period_start=since.isoformat() if since else None,
            period_end=until.isoformat() if until else None,
        )

        for usage in filtered:
            summary.total_input_tokens += usage.input_tokens
            summary.total_output_tokens += usage.output_tokens
            summary.total_cost += usage.cost
            summary.total_calls += 1

            # By model
            if usage.model not in summary.by_model:
                summary.by_model[usage.model] = {"tokens": 0, "cost": 0.0, "calls": 0}
            summary.by_model[usage.model]["tokens"] += usage.input_tokens + usage.output_tokens
            summary.by_model[usage.model]["cost"] += usage.cost
            summary.by_model[usage.model]["calls"] += 1

            # By phase
            if usage.phase is not None:
                phase_key = str(usage.phase)
                if phase_key not in summary.by_phase:
                    summary.by_phase[phase_key] = {"tokens": 0, "cost": 0.0, "calls": 0}
                summary.by_phase[phase_key]["tokens"] += usage.input_tokens + usage.output_tokens
                summary.by_phase[phase_key]["cost"] += usage.cost
                summary.by_phase[phase_key]["calls"] += 1

            # By task type
            if usage.task_type not in summary.by_task_type:
                summary.by_task_type[usage.task_type] = {"tokens": 0, "cost": 0.0, "calls": 0}
            summary.by_task_type[usage.task_type]["tokens"] += (
                usage.input_tokens + usage.output_tokens
            )
            summary.by_task_type[usage.task_type]["cost"] += usage.cost
            summary.by_task_type[usage.task_type]["calls"] += 1

        return summary

    def get_cost_report(self) -> str:
        """Generate human-readable cost report."""
        summary = self.get_summary()

        lines = [
            "=" * 50,
            "TOKEN USAGE & COST REPORT",
            "=" * 50,
            f"Total Calls: {summary.total_calls}",
            f"Total Tokens: {summary.total_input_tokens + summary.total_output_tokens:,}",
            f"  - Input: {summary.total_input_tokens:,}",
            f"  - Output: {summary.total_output_tokens:,}",
            f"Total Cost: ${summary.total_cost:.4f}",
            "",
            "By Model:",
        ]

        for model, data in sorted(summary.by_model.items(), key=lambda x: -x[1]["cost"]):
            lines.append(f"  {model}: {data['calls']} calls, ${data['cost']:.4f}")

        if summary.by_phase:
            lines.append("")
            lines.append("By Phase:")
            for phase, data in sorted(summary.by_phase.items()):
                lines.append(f"  Phase {phase}: {data['calls']} calls, ${data['cost']:.4f}")

        if self.budget_limit:
            remaining = self.budget_limit - summary.total_cost
            pct_used = (summary.total_cost / self.budget_limit) * 100
            lines.extend(
                [
                    "",
                    f"Budget: ${self.budget_limit:.2f}",
                    f"Used: ${summary.total_cost:.4f} ({pct_used:.1f}%)",
                    f"Remaining: ${remaining:.4f}",
                ]
            )

        lines.append("=" * 50)
        return "\n".join(lines)


class ModelRouter:
    """Intelligent model routing for cost optimization.

    Routes tasks to the cheapest model capable of handling them,
    potentially reducing costs by 10-30x for routine tasks.
    """

    # Task type to complexity mapping
    TASK_COMPLEXITY_MAP = {
        # Trivial tasks - use cheapest model
        "format_check": TaskComplexity.TRIVIAL,
        "syntax_validation": TaskComplexity.TRIVIAL,
        "json_parsing": TaskComplexity.TRIVIAL,
        # Simple tasks
        "code_formatting": TaskComplexity.SIMPLE,
        "basic_review": TaskComplexity.SIMPLE,
        "documentation": TaskComplexity.SIMPLE,
        # Moderate tasks
        "bug_detection": TaskComplexity.MODERATE,
        "test_generation": TaskComplexity.MODERATE,
        "refactoring": TaskComplexity.MODERATE,
        # Complex tasks
        "security_audit": TaskComplexity.COMPLEX,
        "architecture_review": TaskComplexity.COMPLEX,
        "performance_analysis": TaskComplexity.COMPLEX,
        # Expert tasks - use best model
        "system_design": TaskComplexity.EXPERT,
        "critical_decision": TaskComplexity.EXPERT,
        "novel_problem": TaskComplexity.EXPERT,
    }

    def __init__(
        self,
        default_cursor_model: str = "gpt-5.2-codex",
        default_gemini_model: str = "gemini-3-pro",
        cost_optimization_enabled: bool = True,
    ):
        """Initialize model router.

        Args:
            default_cursor_model: Default model for Cursor tasks
            default_gemini_model: Default model for Gemini tasks
            cost_optimization_enabled: Whether to route to cheaper models
        """
        self.default_cursor_model = default_cursor_model
        self.default_gemini_model = default_gemini_model
        self.cost_optimization_enabled = cost_optimization_enabled

    def get_complexity(self, task_type: str) -> TaskComplexity:
        """Determine task complexity.

        Args:
            task_type: Type of task

        Returns:
            TaskComplexity level
        """
        return self.TASK_COMPLEXITY_MAP.get(task_type, TaskComplexity.MODERATE)

    def select_model(
        self,
        agent: str,
        task_type: str,
        required_capabilities: Optional[list[str]] = None,
        context_size: int = 0,
        prefer_speed: bool = False,
    ) -> str:
        """Select optimal model for a task.

        Args:
            agent: Agent type ("cursor" or "gemini")
            task_type: Type of task
            required_capabilities: Required model capabilities
            context_size: Required context window size
            prefer_speed: Prefer faster model over cheaper

        Returns:
            Selected model name
        """
        if not self.cost_optimization_enabled:
            return self.default_cursor_model if agent == "cursor" else self.default_gemini_model

        complexity = self.get_complexity(task_type)
        required_capabilities = required_capabilities or []

        # Filter models by provider
        if agent == "cursor":
            candidates = [m for m in MODEL_REGISTRY.values() if m.provider == "openai"]
        else:  # gemini
            candidates = [m for m in MODEL_REGISTRY.values() if m.provider == "google"]

        # Filter by context window
        candidates = [m for m in candidates if m.context_window >= context_size]

        # Filter by capabilities
        if required_capabilities:
            candidates = [
                m for m in candidates if all(cap in m.capabilities for cap in required_capabilities)
            ]

        # Filter by complexity threshold
        candidates = [m for m in candidates if m.complexity_threshold.value <= complexity.value]

        if not candidates:
            # Fallback to default
            return self.default_cursor_model if agent == "cursor" else self.default_gemini_model

        # Sort by preference
        if prefer_speed:
            candidates.sort(key=lambda m: m.latency_ms)
        else:
            candidates.sort(key=lambda m: m.avg_cost_per_1k)

        selected = candidates[0]

        logger.info(
            f"Model routing: {agent}/{task_type} (complexity={complexity.value}) "
            f"-> {selected.name} (${selected.avg_cost_per_1k:.4f}/1K)"
        )

        return selected.name

    def estimate_cost(
        self,
        model: str,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
    ) -> float:
        """Estimate cost for a model call.

        Args:
            model: Model name
            estimated_input_tokens: Estimated input tokens
            estimated_output_tokens: Estimated output tokens

        Returns:
            Estimated cost in dollars
        """
        spec = MODEL_REGISTRY.get(model)
        if not spec:
            # Default estimate
            return (estimated_input_tokens / 1000 * 0.01) + (estimated_output_tokens / 1000 * 0.03)

        input_cost = (estimated_input_tokens / 1000) * spec.input_cost_per_1k
        output_cost = (estimated_output_tokens / 1000) * spec.output_cost_per_1k
        return input_cost + output_cost

    def get_savings_estimate(
        self,
        task_type: str,
        input_tokens: int,
        output_tokens: int,
    ) -> dict:
        """Estimate savings from model routing.

        Args:
            task_type: Type of task
            input_tokens: Estimated input tokens
            output_tokens: Estimated output tokens

        Returns:
            Dict with default_cost, optimized_cost, savings
        """
        # Cost with default models
        default_cursor = self.estimate_cost(self.default_cursor_model, input_tokens, output_tokens)
        default_gemini = self.estimate_cost(self.default_gemini_model, input_tokens, output_tokens)

        # Cost with optimized routing
        optimized_cursor_model = self.select_model("cursor", task_type)
        optimized_gemini_model = self.select_model("gemini", task_type)

        optimized_cursor = self.estimate_cost(optimized_cursor_model, input_tokens, output_tokens)
        optimized_gemini = self.estimate_cost(optimized_gemini_model, input_tokens, output_tokens)

        return {
            "cursor": {
                "default_model": self.default_cursor_model,
                "default_cost": default_cursor,
                "optimized_model": optimized_cursor_model,
                "optimized_cost": optimized_cursor,
                "savings": default_cursor - optimized_cursor,
                "savings_pct": ((default_cursor - optimized_cursor) / default_cursor * 100)
                if default_cursor > 0
                else 0,
            },
            "gemini": {
                "default_model": self.default_gemini_model,
                "default_cost": default_gemini,
                "optimized_model": optimized_gemini_model,
                "optimized_cost": optimized_gemini,
                "savings": default_gemini - optimized_gemini,
                "savings_pct": ((default_gemini - optimized_gemini) / default_gemini * 100)
                if default_gemini > 0
                else 0,
            },
        }
