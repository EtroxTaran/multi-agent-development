"""Optimization scheduling and triggering.

Determines when to run optimization based on evaluation data
and coordinates the optimization lifecycle.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .optimizer import OptimizationResult, PromptOptimizer

logger = logging.getLogger(__name__)


@dataclass
class OptimizationTrigger:
    """Trigger for optimization."""

    agent: str
    template_name: str
    reason: str
    priority: int  # Higher = more urgent
    triggered_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SchedulerConfig:
    """Configuration for the optimization scheduler."""

    # Score threshold for optimization trigger
    score_threshold: float = 7.0

    # Minimum samples before optimization
    min_samples: int = 10

    # Minimum samples per template before optimization
    min_samples_per_template: int = 3

    # Cooldown between optimization attempts (hours)
    optimization_cooldown_hours: int = 24

    # Maximum concurrent optimizations
    max_concurrent: int = 2

    # Check interval (seconds)
    check_interval_seconds: int = 300  # 5 minutes

    # Enable automatic optimization
    auto_optimize: bool = True


class OptimizationScheduler:
    """Schedules and coordinates prompt optimization.

    Monitors evaluation data and triggers optimization when:
    - Average score drops below threshold
    - Recent performance declines
    - Sufficient new samples available
    """

    def __init__(
        self,
        project_dir: str,
        project_name: str,
        config: Optional[SchedulerConfig] = None,
    ):
        """Initialize the scheduler.

        Args:
            project_dir: Project directory
            project_name: Project name
            config: Scheduler configuration
        """
        self.project_dir = project_dir
        self.project_name = project_name
        self.config = config or SchedulerConfig()

        # State
        self._queue: list[OptimizationTrigger] = []
        self._running: set[str] = set()
        self._last_optimization: dict[str, datetime] = {}
        self._running_task: Optional[asyncio.Task] = None

        # Optimizer
        self._optimizer = None

    @property
    def optimizer(self) -> PromptOptimizer:
        if self._optimizer is None:
            self._optimizer = PromptOptimizer(
                project_dir=self.project_dir,
                project_name=self.project_name,
                min_samples_for_optimization=self.config.min_samples,
            )
        return self._optimizer

    def queue_optimization(
        self,
        agent: str,
        template_name: str,
        reason: str,
        priority: int = 5,
    ) -> bool:
        """Queue an optimization for later execution.

        Args:
            agent: Agent name
            template_name: Template to optimize
            reason: Reason for optimization
            priority: Priority level (higher = more urgent)

        Returns:
            True if queued successfully
        """
        key = f"{agent}:{template_name}"

        # Check cooldown
        if key in self._last_optimization:
            cooldown = timedelta(hours=self.config.optimization_cooldown_hours)
            if datetime.now() - self._last_optimization[key] < cooldown:
                logger.info(f"Optimization for {key} in cooldown")
                return False

        # Check if already queued
        for trigger in self._queue:
            if trigger.agent == agent and trigger.template_name == template_name:
                # Update priority if higher
                if priority > trigger.priority:
                    trigger.priority = priority
                    trigger.reason = reason
                return True

        # Add to queue
        trigger = OptimizationTrigger(
            agent=agent,
            template_name=template_name,
            reason=reason,
            priority=priority,
        )
        self._queue.append(trigger)
        self._queue.sort(key=lambda t: t.priority, reverse=True)

        logger.info(f"Queued optimization for {key}: {reason}")
        return True

    async def check_and_queue(self) -> list[OptimizationTrigger]:
        """Check evaluation data and queue optimizations if needed.

        Returns:
            List of new triggers added
        """
        new_triggers = []

        # Get all agents that have evaluations
        from ..db.repositories import get_evaluation_repository

        eval_repo = get_evaluation_repository(self.project_name)

        # Check statistics
        stats = await eval_repo.get_statistics(days=7)
        by_agent = stats.get("by_agent", [])

        for agent_stats in by_agent:
            agent = agent_stats.get("agent")
            avg_score = agent_stats.get("avg_score", 10.0)
            total = agent_stats.get("total", 0)

            if not agent or total < self.config.min_samples:
                continue

            # Check if below threshold - queue for per-template optimization
            if avg_score < self.config.score_threshold:
                # Get template-specific statistics for this agent
                template_stats = await eval_repo.get_statistics_by_template(
                    agent=agent,
                    days=7,
                )

                if not template_stats:
                    # Fall back to default template if no template-specific data
                    template_stats = [
                        {"template_name": "default", "total": total, "avg_score": avg_score}
                    ]

                for tmpl_stat in template_stats:
                    template_name = tmpl_stat.get("template_name") or "default"
                    tmpl_total = tmpl_stat.get("total", 0)
                    tmpl_avg_score = tmpl_stat.get("avg_score", 10.0)

                    # Skip templates with insufficient samples
                    if tmpl_total < self.config.min_samples_per_template:
                        logger.debug(
                            f"Skipping {agent}:{template_name} - insufficient samples "
                            f"({tmpl_total} < {self.config.min_samples_per_template})"
                        )
                        continue

                    # Skip templates above threshold
                    if tmpl_avg_score >= self.config.score_threshold:
                        continue

                    should_optimize, reason = await self.optimizer.should_optimize(
                        agent=agent,
                        template_name=template_name,
                        threshold=self.config.score_threshold,
                    )

                    if should_optimize:
                        trigger = OptimizationTrigger(
                            agent=agent,
                            template_name=template_name,
                            reason=reason,
                            priority=int((self.config.score_threshold - tmpl_avg_score) * 10),
                        )

                        if self.queue_optimization(
                            agent=trigger.agent,
                            template_name=trigger.template_name,
                            reason=trigger.reason,
                            priority=trigger.priority,
                        ):
                            new_triggers.append(trigger)

        return new_triggers

    async def process_queue(self) -> list[OptimizationResult]:
        """Process pending optimization queue.

        Returns:
            List of optimization results
        """
        results = []

        while self._queue and len(self._running) < self.config.max_concurrent:
            trigger = self._queue.pop(0)
            key = f"{trigger.agent}:{trigger.template_name}"

            if key in self._running:
                continue

            self._running.add(key)
            try:
                logger.info(f"Starting optimization for {key}: {trigger.reason}")

                result = await self.optimizer.optimize(
                    agent=trigger.agent,
                    template_name=trigger.template_name,
                )

                results.append(result)

                if result.success:
                    logger.info(f"Optimization succeeded for {key}")
                else:
                    logger.warning(f"Optimization failed for {key}: {result.error}")

                self._last_optimization[key] = datetime.now()

            except Exception as e:
                logger.error(f"Optimization error for {key}: {e}")
                results.append(
                    OptimizationResult(
                        success=False,
                        method="unknown",
                        error=str(e),
                    )
                )

            finally:
                self._running.discard(key)

        return results

    async def run_background(self) -> None:
        """Run scheduler in background.

        Periodically checks for optimization opportunities
        and processes the queue.
        """
        if not self.config.auto_optimize:
            logger.info("Auto-optimization disabled")
            return

        logger.info("Starting optimization scheduler")

        while True:
            try:
                # Check for new optimization opportunities
                await self.check_and_queue()

                # Process queue
                if self._queue:
                    await self.process_queue()

                # Wait for next check
                await asyncio.sleep(self.config.check_interval_seconds)

            except asyncio.CancelledError:
                logger.info("Scheduler cancelled")
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)  # Wait longer on error

    def start(self) -> None:
        """Start the background scheduler."""
        if self._running_task is not None:
            return

        self._running_task = asyncio.create_task(self.run_background())

    def stop(self) -> None:
        """Stop the background scheduler."""
        if self._running_task is not None:
            self._running_task.cancel()
            self._running_task = None

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return len(self._queue)

    @property
    def running_count(self) -> int:
        """Get number of running optimizations."""
        return len(self._running)

    def get_queue_status(self) -> list[dict]:
        """Get current queue status.

        Returns:
            List of pending optimizations
        """
        return [
            {
                "agent": t.agent,
                "template": t.template_name,
                "reason": t.reason,
                "priority": t.priority,
                "triggered_at": t.triggered_at,
            }
            for t in self._queue
        ]
