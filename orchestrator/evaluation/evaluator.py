"""Core evaluation logic for agent outputs.

Provides the main AgentEvaluator class that orchestrates
G-Eval evaluation and integrates with the storage layer.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .g_eval import GEvalEvaluator, GEvalResult
from .metrics import (
    EvaluationMetric,
    compute_weighted_score,
    DEFAULT_THRESHOLDS,
    ScoreThresholds,
)

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Complete evaluation result for an agent execution.

    Attributes:
        evaluation_id: Unique evaluation identifier
        agent: Agent name (claude, cursor, gemini)
        node: LangGraph node name
        task_id: Task ID if applicable
        session_id: Session ID if applicable
        scores: Per-metric scores (1-10 scale)
        overall_score: Weighted overall score
        feedback: Detailed feedback string
        suggestions: List of improvement suggestions
        prompt_hash: Hash of the evaluated prompt
        prompt_version: Version of the prompt template
        evaluator_model: Model used for evaluation
        timestamp: Evaluation timestamp
        metadata: Additional metadata
    """

    evaluation_id: str
    agent: str
    node: str
    task_id: Optional[str]
    session_id: Optional[str]
    scores: dict[str, float]
    overall_score: float
    feedback: str
    suggestions: list[str]
    prompt_hash: str
    prompt_version: Optional[str] = None
    evaluator_model: str = "haiku"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "evaluation_id": self.evaluation_id,
            "agent": self.agent,
            "node": self.node,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "scores": self.scores,
            "overall_score": self.overall_score,
            "feedback": self.feedback,
            "suggestions": self.suggestions,
            "prompt_hash": self.prompt_hash,
            "prompt_version": self.prompt_version,
            "evaluator_model": self.evaluator_model,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvaluationResult":
        """Create from dictionary."""
        return cls(
            evaluation_id=data["evaluation_id"],
            agent=data["agent"],
            node=data["node"],
            task_id=data.get("task_id"),
            session_id=data.get("session_id"),
            scores=data["scores"],
            overall_score=data["overall_score"],
            feedback=data["feedback"],
            suggestions=data.get("suggestions", []),
            prompt_hash=data["prompt_hash"],
            prompt_version=data.get("prompt_version"),
            evaluator_model=data.get("evaluator_model", "haiku"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            metadata=data.get("metadata", {}),
        )

    def needs_optimization(self, thresholds: ScoreThresholds = DEFAULT_THRESHOLDS) -> bool:
        """Check if this result indicates prompt optimization is needed.

        Args:
            thresholds: Score thresholds for decisions

        Returns:
            True if optimization should be triggered
        """
        return self.overall_score < thresholds.optimization_threshold

    def is_golden_example(self, thresholds: ScoreThresholds = DEFAULT_THRESHOLDS) -> bool:
        """Check if this result qualifies as a golden example.

        Args:
            thresholds: Score thresholds for decisions

        Returns:
            True if this is a high-quality example worth saving
        """
        return self.overall_score >= thresholds.golden_example_threshold

    def indicates_failure(self, thresholds: ScoreThresholds = DEFAULT_THRESHOLDS) -> bool:
        """Check if this result indicates task failure.

        Args:
            thresholds: Score thresholds for decisions

        Returns:
            True if the output should be considered failed
        """
        return self.overall_score < thresholds.failure_threshold


class AgentEvaluator:
    """Main evaluator for agent outputs.

    Orchestrates G-Eval evaluation and provides high-level
    methods for evaluating different types of agent outputs.

    Supports cost controls via sampling_rate and max_cost_per_eval.
    """

    def __init__(
        self,
        project_dir: Optional[str | Path] = None,
        evaluator_model: str = "haiku",
        thresholds: Optional[ScoreThresholds] = None,
        enable_storage: bool = True,
        sampling_rate: float = 1.0,
        max_cost_per_eval: float = 0.05,
    ):
        """Initialize the evaluator.

        Args:
            project_dir: Project directory for context
            evaluator_model: Model to use for evaluation (haiku recommended)
            thresholds: Score thresholds for decisions
            enable_storage: Whether to store evaluations in DB
            sampling_rate: Rate of evaluations to run (0.0-1.0)
            max_cost_per_eval: Maximum cost per evaluation in USD
        """
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.evaluator_model = evaluator_model
        self.thresholds = thresholds or DEFAULT_THRESHOLDS
        self.enable_storage = enable_storage
        self.sampling_rate = max(0.0, min(1.0, sampling_rate))
        self.max_cost_per_eval = max_cost_per_eval

        # Initialize G-Eval evaluator
        self._g_eval = GEvalEvaluator(
            evaluator_model=evaluator_model,
            project_dir=str(self.project_dir),
        )

        # Lazy-loaded storage
        self._storage = None

        # Cost tracking
        self._eval_count = 0
        self._skipped_count = 0

    @property
    def storage(self):
        """Get or create evaluation storage."""
        if self._storage is None and self.enable_storage:
            try:
                from ..db.repositories import get_evaluation_repository
                project_name = self.project_dir.name
                self._storage = get_evaluation_repository(project_name)
            except ImportError:
                logger.debug("Evaluation storage not available")
        return self._storage

    async def evaluate(
        self,
        agent: str,
        node: str,
        prompt: str,
        output: str,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        requirements: Optional[list[str]] = None,
        prompt_version: Optional[str] = None,
        metadata: Optional[dict] = None,
        force: bool = False,
    ) -> Optional[EvaluationResult]:
        """Evaluate an agent output.

        Respects sampling_rate for probabilistic evaluation. Use force=True
        to bypass sampling for critical evaluations.

        Args:
            agent: Agent name (claude, cursor, gemini)
            node: LangGraph node name
            prompt: Original prompt
            output: Agent's output
            task_id: Optional task ID
            session_id: Optional session ID
            requirements: Optional acceptance criteria
            prompt_version: Optional prompt version identifier
            metadata: Optional additional metadata
            force: Bypass sampling rate check

        Returns:
            EvaluationResult with scores and feedback, or None if skipped
        """
        import random

        # Apply sampling unless forced
        if not force and self.sampling_rate < 1.0:
            if random.random() > self.sampling_rate:
                self._skipped_count += 1
                logger.debug(
                    f"Skipping evaluation due to sampling "
                    f"(rate={self.sampling_rate:.2f}, skipped={self._skipped_count})"
                )
                return None

        self._eval_count += 1

        # Determine metrics to evaluate based on cost
        metrics = self._select_metrics_for_cost()

        # Run G-Eval (async)
        g_eval_result = await self._g_eval.evaluate(
            agent=agent,
            node=node,
            prompt=prompt,
            output=output,
            task_id=task_id,
            requirements=requirements,
            metrics=metrics,
        )

        # Build feedback string from evaluations
        feedback_parts = []
        for evaluation in g_eval_result.evaluations:
            feedback_parts.append(
                f"**{evaluation.criterion}** ({evaluation.score}/10): {evaluation.feedback}"
            )
        feedback = "\n".join(feedback_parts)

        # Generate evaluation ID
        timestamp = datetime.now()
        evaluation_id = f"eval-{agent}-{timestamp.strftime('%Y%m%d%H%M%S')}-{g_eval_result.prompt_hash[:8]}"

        # Build result
        result = EvaluationResult(
            evaluation_id=evaluation_id,
            agent=agent,
            node=node,
            task_id=task_id,
            session_id=session_id,
            scores=g_eval_result.scores,
            overall_score=g_eval_result.overall_score,
            feedback=feedback,
            suggestions=g_eval_result.suggestions,
            prompt_hash=g_eval_result.prompt_hash,
            prompt_version=prompt_version,
            evaluator_model=g_eval_result.evaluator_model,
            timestamp=timestamp.isoformat(),
            metadata=metadata or {},
        )

        # Store evaluation if enabled
        if self.storage:
            try:
                await self._store_evaluation(result)
            except Exception as e:
                logger.warning(f"Failed to store evaluation: {e}")

        return result

    def _select_metrics_for_cost(self) -> Optional[list[EvaluationMetric]]:
        """Select metrics to evaluate based on cost constraints.

        If max_cost_per_eval is below the full evaluation cost (~$0.007),
        returns a subset of the most important metrics.

        Returns:
            List of metrics to evaluate, or None for all metrics
        """
        # Approximate cost per criterion evaluation (~$0.001 with haiku)
        COST_PER_CRITERION = 0.001

        # Full evaluation has 7 criteria
        full_eval_cost = 7 * COST_PER_CRITERION

        if self.max_cost_per_eval >= full_eval_cost:
            return None  # Evaluate all metrics

        # Calculate how many criteria we can afford
        max_criteria = max(1, int(self.max_cost_per_eval / COST_PER_CRITERION))

        # Priority order of metrics (most important first)
        priority_metrics = [
            EvaluationMetric.TASK_COMPLETION,    # Most important
            EvaluationMetric.OUTPUT_QUALITY,
            EvaluationMetric.REASONING_QUALITY,
            EvaluationMetric.TOOL_UTILIZATION,
            EvaluationMetric.TOKEN_EFFICIENCY,
            EvaluationMetric.CONTEXT_RETENTION,
            EvaluationMetric.SAFETY,             # Least weighted
        ]

        selected = priority_metrics[:max_criteria]
        logger.debug(
            f"Cost-constrained evaluation: {len(selected)}/{len(priority_metrics)} metrics "
            f"(max_cost=${self.max_cost_per_eval:.3f})"
        )

        return selected

    def get_stats(self) -> dict:
        """Get evaluation statistics.

        Returns:
            Dict with eval_count, skipped_count, and sampling_rate
        """
        return {
            "eval_count": self._eval_count,
            "skipped_count": self._skipped_count,
            "sampling_rate": self.sampling_rate,
            "max_cost_per_eval": self.max_cost_per_eval,
        }

    async def _store_evaluation(self, result: EvaluationResult) -> None:
        """Store evaluation in database.

        Args:
            result: Evaluation result to store
        """
        if self.storage:
            await self.storage.save(result)

    async def evaluate_implementation(
        self,
        agent: str,
        prompt: str,
        output: str,
        task_id: str,
        acceptance_criteria: list[str],
        files_created: Optional[list[str]] = None,
        files_modified: Optional[list[str]] = None,
        test_results: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> EvaluationResult:
        """Evaluate an implementation task output.

        Specialized evaluation for implementation outputs that includes
        consideration of files changed and test results.

        Args:
            agent: Agent name
            prompt: Implementation prompt
            output: Agent's output
            task_id: Task being implemented
            acceptance_criteria: Task's acceptance criteria
            files_created: List of files created
            files_modified: List of files modified
            test_results: Test execution results
            session_id: Session ID

        Returns:
            EvaluationResult
        """
        # Build enhanced requirements
        requirements = list(acceptance_criteria)

        # Add file expectations to requirements
        if files_created:
            requirements.append(f"Expected to create files: {', '.join(files_created)}")
        if files_modified:
            requirements.append(f"Expected to modify files: {', '.join(files_modified)}")

        # Add test expectations
        if test_results:
            if test_results.get("passed"):
                requirements.append("All tests should pass")
            if test_results.get("coverage"):
                requirements.append(f"Test coverage: {test_results['coverage']}%")

        # Build metadata
        metadata = {
            "files_created": files_created,
            "files_modified": files_modified,
            "test_results": test_results,
        }

        return await self.evaluate(
            agent=agent,
            node="implement_task",
            prompt=prompt,
            output=output,
            task_id=task_id,
            session_id=session_id,
            requirements=requirements,
            metadata=metadata,
        )

    async def evaluate_validation(
        self,
        agent: str,
        prompt: str,
        output: str,
        plan_summary: str,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> EvaluationResult:
        """Evaluate a validation/review output.

        Specialized evaluation for Cursor/Gemini validation outputs.

        Args:
            agent: Agent name (cursor or gemini)
            prompt: Validation prompt
            output: Agent's validation output
            plan_summary: Summary of the plan being validated
            task_id: Optional task ID
            session_id: Session ID

        Returns:
            EvaluationResult
        """
        requirements = [
            "Provide clear approval/rejection decision",
            "List specific concerns with severity levels",
            "Identify blocking issues if any",
            "Give constructive feedback",
            f"Review the plan: {plan_summary[:200]}...",
        ]

        node = f"{agent}_validate" if "validate" in agent else f"{agent}_review"

        return await self.evaluate(
            agent=agent,
            node=node,
            prompt=prompt,
            output=output,
            task_id=task_id,
            session_id=session_id,
            requirements=requirements,
        )

    async def get_evaluation_history(
        self,
        agent: Optional[str] = None,
        node: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[EvaluationResult]:
        """Get historical evaluations.

        Args:
            agent: Filter by agent
            node: Filter by node
            task_id: Filter by task ID
            limit: Maximum results

        Returns:
            List of EvaluationResults
        """
        if not self.storage:
            return []

        try:
            return await self.storage.get_history(
                agent=agent,
                node=node,
                task_id=task_id,
                limit=limit,
            )
        except Exception as e:
            logger.warning(f"Failed to get evaluation history: {e}")
            return []

    async def get_prompt_performance(
        self,
        prompt_hash: str,
        min_samples: int = 5,
    ) -> Optional[dict]:
        """Get performance metrics for a prompt.

        Args:
            prompt_hash: Hash of the prompt
            min_samples: Minimum samples required

        Returns:
            Performance metrics or None if insufficient data
        """
        if not self.storage:
            return None

        try:
            evaluations = await self.storage.get_by_prompt_hash(prompt_hash)
            if len(evaluations) < min_samples:
                return None

            scores = [e.overall_score for e in evaluations]
            return {
                "prompt_hash": prompt_hash,
                "sample_count": len(evaluations),
                "avg_score": sum(scores) / len(scores),
                "min_score": min(scores),
                "max_score": max(scores),
                "std_dev": self._std_dev(scores),
            }
        except Exception as e:
            logger.warning(f"Failed to get prompt performance: {e}")
            return None

    def _std_dev(self, values: list[float]) -> float:
        """Calculate standard deviation.

        Args:
            values: List of values

        Returns:
            Standard deviation
        """
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
