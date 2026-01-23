"""G-Eval implementation for agent output evaluation.

Uses LLM-as-Judge pattern with chain-of-thought evaluation
per criterion, then normalizes scores.
"""

import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Optional

from .metrics import (
    EvaluationMetric,
    EVALUATION_CRITERIA,
    compute_weighted_score,
)

logger = logging.getLogger(__name__)


# Meta-prompt template for G-Eval
G_EVAL_PROMPT_TEMPLATE = """You are an expert evaluator assessing AI agent outputs.

## Task Context
Agent: {agent}
Task ID: {task_id}
Node: {node}

## Original Prompt
{prompt}

## Agent Output
{output}

## Requirements
{requirements}

## Evaluation Criterion: {criterion_name}
{criterion_description}

## Scoring Rubric
{rubric}

## Instructions
1. Analyze the agent output against the criterion above
2. Think step-by-step about how well the output meets the criterion
3. Provide a score from 1-10 based on the rubric
4. Give a brief explanation for your score

Respond in JSON format:
{{
    "reasoning": "Your step-by-step analysis...",
    "score": <1-10>,
    "feedback": "Brief explanation of the score"
}}"""


@dataclass
class CriterionEvaluation:
    """Evaluation result for a single criterion."""

    criterion: str
    score: float
    reasoning: str
    feedback: str


@dataclass
class GEvalResult:
    """Complete G-Eval result across all criteria."""

    scores: dict[str, float]
    overall_score: float
    evaluations: list[CriterionEvaluation]
    suggestions: list[str]
    prompt_hash: str
    evaluator_model: str


class GEvalEvaluator:
    """G-Eval evaluator using LLM-as-Judge pattern.

    Evaluates agent outputs across multiple quality dimensions
    using chain-of-thought reasoning per criterion.
    """

    def __init__(
        self,
        evaluator_model: str = "haiku",
        timeout: int = 60,
        project_dir: Optional[str] = None,
    ):
        """Initialize the G-Eval evaluator.

        Args:
            evaluator_model: Model to use for evaluation (haiku for speed/cost)
            timeout: Timeout per criterion evaluation in seconds
            project_dir: Project directory for context
        """
        self.evaluator_model = evaluator_model
        self.timeout = timeout
        self.project_dir = project_dir or os.getcwd()

    def evaluate(
        self,
        agent: str,
        node: str,
        prompt: str,
        output: str,
        task_id: Optional[str] = None,
        requirements: Optional[list[str]] = None,
        metrics: Optional[list[EvaluationMetric]] = None,
    ) -> GEvalResult:
        """Evaluate an agent output using G-Eval.

        Args:
            agent: Agent name (claude, cursor, gemini)
            node: LangGraph node name
            prompt: Original prompt given to agent
            output: Agent's output
            task_id: Optional task ID for context
            requirements: Optional list of requirements/acceptance criteria
            metrics: Optional list of metrics to evaluate (all by default)

        Returns:
            GEvalResult with scores and feedback
        """
        if metrics is None:
            metrics = list(EvaluationMetric)

        evaluations: list[CriterionEvaluation] = []
        scores: dict[str, float] = {}

        # Evaluate each criterion
        for metric in metrics:
            try:
                evaluation = self._evaluate_criterion(
                    agent=agent,
                    node=node,
                    prompt=prompt,
                    output=output,
                    task_id=task_id,
                    requirements=requirements,
                    metric=metric,
                )
                evaluations.append(evaluation)
                scores[metric.value] = evaluation.score
            except Exception as e:
                logger.warning(f"Failed to evaluate criterion {metric.value}: {e}")
                # Use neutral score on failure
                scores[metric.value] = 5.0
                evaluations.append(CriterionEvaluation(
                    criterion=metric.value,
                    score=5.0,
                    reasoning=f"Evaluation failed: {e}",
                    feedback="Unable to evaluate this criterion",
                ))

        # Compute weighted overall score
        overall_score = compute_weighted_score(scores)

        # Generate improvement suggestions
        suggestions = self._generate_suggestions(evaluations, overall_score)

        # Hash the prompt for tracking
        prompt_hash = self._hash_prompt(prompt)

        return GEvalResult(
            scores=scores,
            overall_score=overall_score,
            evaluations=evaluations,
            suggestions=suggestions,
            prompt_hash=prompt_hash,
            evaluator_model=self.evaluator_model,
        )

    def _evaluate_criterion(
        self,
        agent: str,
        node: str,
        prompt: str,
        output: str,
        task_id: Optional[str],
        requirements: Optional[list[str]],
        metric: EvaluationMetric,
    ) -> CriterionEvaluation:
        """Evaluate a single criterion using LLM-as-Judge.

        Args:
            agent: Agent name
            node: Node name
            prompt: Original prompt
            output: Agent output
            task_id: Task ID
            requirements: Requirements list
            metric: Metric to evaluate

        Returns:
            CriterionEvaluation with score and feedback
        """
        weight_config = EVALUATION_CRITERIA[metric]

        # Build evaluation prompt
        eval_prompt = G_EVAL_PROMPT_TEMPLATE.format(
            agent=agent,
            task_id=task_id or "N/A",
            node=node,
            prompt=self._truncate(prompt, 2000),
            output=self._truncate(output, 4000),
            requirements=self._format_requirements(requirements),
            criterion_name=metric.value.replace("_", " ").title(),
            criterion_description=weight_config.description,
            rubric=weight_config.rubric,
        )

        # Call evaluator model
        result = self._call_evaluator(eval_prompt)

        # Parse response
        try:
            parsed = json.loads(result)
            return CriterionEvaluation(
                criterion=metric.value,
                score=float(parsed.get("score", 5.0)),
                reasoning=parsed.get("reasoning", ""),
                feedback=parsed.get("feedback", ""),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse evaluation result: {e}")
            # Try to extract score from text
            score = self._extract_score_from_text(result)
            return CriterionEvaluation(
                criterion=metric.value,
                score=score,
                reasoning=result,
                feedback="Unable to parse structured response",
            )

    def _call_evaluator(self, prompt: str) -> str:
        """Call the evaluator model.

        Uses Claude CLI with haiku model for fast, cheap evaluation.

        Args:
            prompt: Evaluation prompt

        Returns:
            Model response
        """
        try:
            # Use Claude CLI for evaluation
            cmd = [
                "claude",
                "-p", prompt,
                "--output-format", "text",
                "--max-turns", "1",
            ]

            # Add model specification if not default
            if self.evaluator_model != "sonnet":
                # Haiku is faster and cheaper for evaluation
                cmd.extend(["--model", self.evaluator_model])

            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={**os.environ, "TERM": "dumb"},
            )

            if result.returncode != 0:
                logger.warning(f"Evaluator returned non-zero: {result.stderr}")
                return "{}"

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            logger.warning(f"Evaluator timed out after {self.timeout}s")
            return "{}"
        except FileNotFoundError:
            logger.warning("Claude CLI not found, using default scores")
            return "{}"
        except Exception as e:
            logger.warning(f"Evaluator call failed: {e}")
            return "{}"

    def _generate_suggestions(
        self,
        evaluations: list[CriterionEvaluation],
        overall_score: float,
    ) -> list[str]:
        """Generate improvement suggestions based on evaluations.

        Args:
            evaluations: List of criterion evaluations
            overall_score: Overall weighted score

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        # Find low-scoring criteria
        for evaluation in evaluations:
            if evaluation.score < 6.0:
                weight_config = EVALUATION_CRITERIA.get(
                    EvaluationMetric(evaluation.criterion)
                )
                if weight_config:
                    suggestions.append(
                        f"Improve {evaluation.criterion}: {evaluation.feedback}"
                    )

        # Add overall suggestions based on patterns
        low_scores = [e for e in evaluations if e.score < 5.0]
        if len(low_scores) >= 3:
            suggestions.append(
                "Multiple criteria scored poorly - consider prompt restructuring"
            )

        if overall_score < 5.0:
            suggestions.append(
                "Overall score very low - fundamental prompt issues likely"
            )

        return suggestions

    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to maximum length.

        Args:
            text: Text to truncate
            max_length: Maximum length

        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
        return text[:max_length] + "... [truncated]"

    def _format_requirements(self, requirements: Optional[list[str]]) -> str:
        """Format requirements list for prompt.

        Args:
            requirements: List of requirements

        Returns:
            Formatted string
        """
        if not requirements:
            return "No specific requirements provided"
        return "\n".join(f"- {req}" for req in requirements)

    def _hash_prompt(self, prompt: str) -> str:
        """Generate hash of prompt for tracking.

        Args:
            prompt: Prompt to hash

        Returns:
            SHA256 hash prefix
        """
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    def _extract_score_from_text(self, text: str) -> float:
        """Extract score from unstructured text.

        Args:
            text: Text that may contain a score

        Returns:
            Extracted score or default 5.0
        """
        import re

        # Look for patterns like "score: 7" or "7/10"
        patterns = [
            r'"score":\s*(\d+(?:\.\d+)?)',
            r'score[:\s]+(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)/10',
            r'(\d+(?:\.\d+)?)\s+out\s+of\s+10',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    score = float(match.group(1))
                    if 1 <= score <= 10:
                        return score
                except ValueError:
                    continue

        return 5.0  # Default neutral score
