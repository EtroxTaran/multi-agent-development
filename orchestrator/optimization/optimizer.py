"""Core prompt optimization logic.

Provides the main PromptOptimizer class that coordinates
different optimization strategies.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result from a prompt optimization attempt.

    Attributes:
        success: Whether optimization produced an improved prompt
        new_prompt: The optimized prompt content
        source_version: Version ID of the source prompt
        expected_improvement: Expected score improvement
        validation_score: Score from validation testing
        method: Optimization method used
        samples_used: Number of samples used for optimization
        error: Error message if failed
        metadata: Additional metadata
    """

    success: bool
    new_prompt: Optional[str] = None
    source_version: Optional[str] = None
    expected_improvement: float = 0.0
    validation_score: Optional[float] = None
    method: str = "unknown"
    samples_used: int = 0
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "new_prompt": self.new_prompt[:500] if self.new_prompt else None,
            "source_version": self.source_version,
            "expected_improvement": self.expected_improvement,
            "validation_score": self.validation_score,
            "method": self.method,
            "samples_used": self.samples_used,
            "error": self.error,
            "metadata": self.metadata,
        }


class PromptOptimizer:
    """Main optimizer that coordinates different optimization strategies.

    Supports multiple optimization methods:
    - OPRO: Uses LLM to generate improved prompts from examples
    - Bootstrap: Generates few-shot examples from golden outputs
    - Instruction: Refines instructions based on feedback

    The optimizer selects the appropriate method based on available data
    and configuration.
    """

    def __init__(
        self,
        project_dir: Optional[str | Path] = None,
        project_name: Optional[str] = None,
        min_samples_for_optimization: int = 10,
        improvement_threshold: float = 0.5,
    ):
        """Initialize the optimizer.

        Args:
            project_dir: Project directory
            project_name: Project name for DB access
            min_samples_for_optimization: Minimum evaluations needed
            improvement_threshold: Minimum improvement to accept
        """
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.project_name = project_name or self.project_dir.name
        self.min_samples = min_samples_for_optimization
        self.improvement_threshold = improvement_threshold

        # Lazy-loaded optimizers
        self._opro = None
        self._bootstrap = None

        # Lazy-loaded repositories
        self._eval_repo = None
        self._prompt_repo = None
        self._golden_repo = None
        self._history_repo = None

    @property
    def eval_repo(self):
        if self._eval_repo is None:
            from ..db.repositories import get_evaluation_repository
            self._eval_repo = get_evaluation_repository(self.project_name)
        return self._eval_repo

    @property
    def prompt_repo(self):
        if self._prompt_repo is None:
            from ..db.repositories import get_prompt_version_repository
            self._prompt_repo = get_prompt_version_repository(self.project_name)
        return self._prompt_repo

    @property
    def golden_repo(self):
        if self._golden_repo is None:
            from ..db.repositories import get_golden_example_repository
            self._golden_repo = get_golden_example_repository(self.project_name)
        return self._golden_repo

    @property
    def history_repo(self):
        if self._history_repo is None:
            from ..db.repositories import get_optimization_history_repository
            self._history_repo = get_optimization_history_repository(self.project_name)
        return self._history_repo

    @property
    def opro(self):
        if self._opro is None:
            from .opro import OPROOptimizer
            self._opro = OPROOptimizer(
                project_dir=str(self.project_dir),
                project_name=self.project_name,
            )
        return self._opro

    @property
    def bootstrap(self):
        if self._bootstrap is None:
            from .bootstrap import BootstrapOptimizer
            self._bootstrap = BootstrapOptimizer(
                project_dir=str(self.project_dir),
                project_name=self.project_name,
            )
        return self._bootstrap

    async def optimize(
        self,
        agent: str,
        template_name: str,
        method: Optional[str] = None,
        force: bool = False,
    ) -> OptimizationResult:
        """Optimize a prompt template.

        Args:
            agent: Agent name
            template_name: Template to optimize
            method: Specific method to use (opro, bootstrap, auto)
            force: Force optimization even with insufficient data

        Returns:
            OptimizationResult
        """
        # Check prerequisites
        evaluations = await self.eval_repo.get_by_agent(agent, limit=100)
        if len(evaluations) < self.min_samples and not force:
            return OptimizationResult(
                success=False,
                method="none",
                error=f"Insufficient samples: {len(evaluations)} < {self.min_samples}",
            )

        # Get current prompt version
        current_version = await self.prompt_repo.get_production_version(
            agent, template_name
        )
        if not current_version:
            return OptimizationResult(
                success=False,
                method="none",
                error=f"No production prompt found for {agent}/{template_name}",
            )

        # Select optimization method
        if method is None:
            method = await self._select_method(agent, template_name)

        # Run optimization
        if method == "opro":
            result = await self._optimize_with_opro(
                agent, template_name, current_version, evaluations
            )
        elif method == "bootstrap":
            result = await self._optimize_with_bootstrap(
                agent, template_name, current_version
            )
        else:
            return OptimizationResult(
                success=False,
                method=method,
                error=f"Unknown optimization method: {method}",
            )

        # Record attempt
        await self._record_optimization(agent, template_name, result, current_version)

        return result

    async def _select_method(self, agent: str, template_name: str) -> str:
        """Select the best optimization method based on available data.

        Args:
            agent: Agent name
            template_name: Template name

        Returns:
            Optimization method name
        """
        # Check if we have enough golden examples for bootstrap
        golden_count = await self.golden_repo.count_by_template(agent, template_name)

        if golden_count >= 3:
            return "bootstrap"
        else:
            return "opro"

    async def _optimize_with_opro(
        self,
        agent: str,
        template_name: str,
        current_version: dict,
        evaluations: list[dict],
    ) -> OptimizationResult:
        """Run OPRO optimization.

        Args:
            agent: Agent name
            template_name: Template name
            current_version: Current prompt version
            evaluations: Historical evaluations

        Returns:
            OptimizationResult
        """
        try:
            result = await self.opro.optimize(
                template_name=template_name,
                current_prompt=current_version.get("content", ""),
                evaluation_history=evaluations,
            )

            if result.success and result.new_prompt:
                # Validate the new prompt
                validation_score = await self._validate_prompt(
                    agent, template_name, result.new_prompt
                )

                current_score = self._get_avg_score(evaluations)
                improvement = (validation_score or 0) - current_score

                if improvement >= self.improvement_threshold:
                    # Save new version
                    next_version = await self.prompt_repo.get_next_version_number(
                        agent, template_name
                    )
                    await self.prompt_repo.save_version(
                        agent=agent,
                        template_name=template_name,
                        content=result.new_prompt,
                        version=next_version,
                        parent_version=current_version.get("version_id"),
                        optimization_method="opro",
                        status="draft",
                        metrics={"validation_score": validation_score},
                    )

                    return OptimizationResult(
                        success=True,
                        new_prompt=result.new_prompt,
                        source_version=current_version.get("version_id"),
                        expected_improvement=improvement,
                        validation_score=validation_score,
                        method="opro",
                        samples_used=len(evaluations),
                    )
                else:
                    return OptimizationResult(
                        success=False,
                        method="opro",
                        samples_used=len(evaluations),
                        error=f"Improvement {improvement:.2f} below threshold {self.improvement_threshold}",
                    )

            return OptimizationResult(
                success=False,
                method="opro",
                error=result.error or "OPRO optimization failed",
            )

        except Exception as e:
            logger.error(f"OPRO optimization failed: {e}")
            return OptimizationResult(
                success=False,
                method="opro",
                error=str(e),
            )

    async def _optimize_with_bootstrap(
        self,
        agent: str,
        template_name: str,
        current_version: dict,
    ) -> OptimizationResult:
        """Run bootstrap optimization.

        Args:
            agent: Agent name
            template_name: Template name
            current_version: Current prompt version

        Returns:
            OptimizationResult
        """
        try:
            result = await self.bootstrap.optimize(
                agent=agent,
                template_name=template_name,
                current_prompt=current_version.get("content", ""),
            )

            if result.success and result.new_prompt:
                # Validate the new prompt
                validation_score = await self._validate_prompt(
                    agent, template_name, result.new_prompt
                )

                # Get current score from golden examples
                golden_examples = await self.golden_repo.get_by_template(
                    agent, template_name, limit=10
                )
                current_score = sum(g["score"] for g in golden_examples) / len(golden_examples) if golden_examples else 5.0

                improvement = (validation_score or 0) - current_score

                if improvement >= self.improvement_threshold:
                    # Save new version
                    next_version = await self.prompt_repo.get_next_version_number(
                        agent, template_name
                    )
                    await self.prompt_repo.save_version(
                        agent=agent,
                        template_name=template_name,
                        content=result.new_prompt,
                        version=next_version,
                        parent_version=current_version.get("version_id"),
                        optimization_method="bootstrap",
                        status="draft",
                        metrics={"validation_score": validation_score},
                    )

                    return OptimizationResult(
                        success=True,
                        new_prompt=result.new_prompt,
                        source_version=current_version.get("version_id"),
                        expected_improvement=improvement,
                        validation_score=validation_score,
                        method="bootstrap",
                        samples_used=len(golden_examples),
                    )
                else:
                    return OptimizationResult(
                        success=False,
                        method="bootstrap",
                        error=f"Improvement {improvement:.2f} below threshold {self.improvement_threshold}",
                    )

            return OptimizationResult(
                success=False,
                method="bootstrap",
                error=result.error or "Bootstrap optimization failed",
            )

        except Exception as e:
            logger.error(f"Bootstrap optimization failed: {e}")
            return OptimizationResult(
                success=False,
                method="bootstrap",
                error=str(e),
            )

    async def _validate_prompt(
        self,
        agent: str,
        template_name: str,
        prompt: str,
        holdout_count: int = 3,
    ) -> Optional[float]:
        """Validate a prompt on holdout set by running test evaluations.

        Uses golden examples as a holdout set to validate the new prompt.
        Falls back to heuristic validation if no golden examples are available.

        Args:
            agent: Agent name
            template_name: Template name
            prompt: Prompt to validate
            holdout_count: Number of test cases to run

        Returns:
            Validation score or None if validation failed
        """
        try:
            # Get recent golden examples as holdout set
            golden_examples = await self.golden_repo.get_by_template(
                agent, template_name, limit=holdout_count
            )

            if len(golden_examples) < holdout_count:
                # Fall back to recent high-scoring evaluations
                evaluations = await self.eval_repo.get_by_agent(agent, limit=50)
                golden_examples = [
                    e for e in evaluations
                    if e.get("overall_score", 0) >= 8.0
                ][:holdout_count]

            if not golden_examples:
                # No holdout data, use heuristic validation
                return self._heuristic_validate(prompt)

            # Run evaluations with the new prompt on holdout inputs
            from ..evaluation import AgentEvaluator

            evaluator = AgentEvaluator(
                project_dir=self.project_dir,
                evaluator_model="haiku",
                enable_storage=False,  # Don't store validation evals
            )

            scores = []
            for example in golden_examples:
                # Evaluate prompt quality using the new G-Eval method
                result = await evaluator._g_eval.evaluate_prompt_quality(
                    prompt=prompt,
                    reference_input=example.get("input", example.get("input_prompt", "")),
                    reference_output=example.get("output", ""),
                )
                scores.append(result.overall_score)

            return sum(scores) / len(scores) if scores else None

        except Exception as e:
            logger.warning(f"Prompt validation failed: {e}")
            return self._heuristic_validate(prompt)

    def _heuristic_validate(self, prompt: str) -> float:
        """Basic heuristic validation when no holdout data available.

        Analyzes prompt structure and content to estimate quality.

        Args:
            prompt: Prompt to validate

        Returns:
            Estimated quality score (1-10)
        """
        score = 5.0  # Base score

        # Length check (not too short, not too long)
        if 500 <= len(prompt) <= 5000:
            score += 1.0
        elif len(prompt) < 200:
            score -= 1.0
        elif len(prompt) > 8000:
            score -= 0.5  # Penalize very long prompts

        # Structure check (has sections)
        if "##" in prompt or "**" in prompt:
            score += 0.5

        # Has output format specification
        if "output" in prompt.lower() and ("format" in prompt.lower() or "json" in prompt.lower()):
            score += 0.5

        # Has clear instructions
        instruction_keywords = ["must", "should", "ensure", "always", "never"]
        if any(kw in prompt.lower() for kw in instruction_keywords):
            score += 0.5

        # Has examples or code blocks
        if "example" in prompt.lower() or "```" in prompt:
            score += 0.5

        # Has step-by-step instructions
        if any(f"{i}." in prompt for i in range(1, 6)):
            score += 0.5

        # Penalize if too generic
        generic_phrases = ["do the task", "complete the work", "as needed"]
        if any(phrase in prompt.lower() for phrase in generic_phrases):
            score -= 0.5

        return min(10.0, max(1.0, score))

    def _get_avg_score(self, evaluations: list[dict]) -> float:
        """Calculate average score from evaluations.

        Args:
            evaluations: List of evaluations

        Returns:
            Average score
        """
        if not evaluations:
            return 5.0
        scores = [e.get("overall_score", 5.0) for e in evaluations]
        return sum(scores) / len(scores)

    async def _record_optimization(
        self,
        agent: str,
        template_name: str,
        result: OptimizationResult,
        current_version: dict,
    ) -> None:
        """Record optimization attempt in history.

        Args:
            agent: Agent name
            template_name: Template name
            result: Optimization result
            current_version: Source version
        """
        await self.history_repo.record_attempt(
            agent=agent,
            template_name=template_name,
            method=result.method,
            source_version=current_version.get("version_id"),
            target_version=result.source_version,
            success=result.success,
            source_score=current_version.get("metrics", {}).get("avg_score"),
            target_score=result.validation_score,
            samples_used=result.samples_used,
            validation_results={"score": result.validation_score},
            error=result.error,
        )

    async def should_optimize(
        self,
        agent: str,
        template_name: str,
        threshold: float = 7.0,
    ) -> tuple[bool, str]:
        """Check if a template should be optimized.

        Args:
            agent: Agent name
            template_name: Template name
            threshold: Score threshold for optimization

        Returns:
            Tuple of (should_optimize, reason)
        """
        # Get recent evaluations
        evaluations = await self.eval_repo.get_by_agent(agent, limit=50)
        if len(evaluations) < self.min_samples:
            return False, f"Insufficient samples ({len(evaluations)})"

        avg_score = self._get_avg_score(evaluations)
        if avg_score < threshold:
            return True, f"Average score {avg_score:.2f} below threshold {threshold}"

        # Check for recent decline
        recent = evaluations[:10]
        older = evaluations[10:30]
        if recent and older:
            recent_avg = self._get_avg_score(recent)
            older_avg = self._get_avg_score(older)
            if recent_avg < older_avg - 0.5:
                return True, f"Recent decline: {recent_avg:.2f} vs {older_avg:.2f}"

        return False, "Performance is acceptable"
