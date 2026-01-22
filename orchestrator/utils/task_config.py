"""Task complexity configuration and scoring.

Implements a multi-dimensional complexity assessment for task granularity:
- File scope (soft limits on files touched)
- Token budget (estimated context consumption)
- Complexity score (0-13 composite scale)
- Time budget (estimated execution time)
- Semantic coherence (single clear purpose)

Research shows file counts alone are insufficient - a task modifying 3 tightly
coupled files may be harder than one modifying 10 isolated files. This module
implements the "Complexity Triangle" principle where tasks must satisfy
multiple constraints simultaneously.

References:
- SWE-Agent research: 87.7% pass@1 with fine-grained interfaces
- Multi-agent task depth/width analysis
- Enterprise AI agent reliability studies
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ComplexityLevel(str, Enum):
    """Task complexity levels based on composite score."""

    LOW = "low"  # Score 0-4: Safe for autonomous execution
    MEDIUM = "medium"  # Score 5-7: Requires monitoring
    HIGH = "high"  # Score 8-10: Consider decomposition
    CRITICAL = "critical"  # Score 11-13: Must decompose


# Default configuration values
DEFAULT_MAX_FILES_TO_CREATE = 5  # Soft limit (guidance)
DEFAULT_MAX_FILES_TO_MODIFY = 8  # Soft limit (guidance)
DEFAULT_MAX_ACCEPTANCE_CRITERIA = 7
DEFAULT_MAX_INPUT_TOKENS = 6000  # 4K-8K range, middle ground
DEFAULT_MAX_OUTPUT_TOKENS = 3000  # 2K-4K range
DEFAULT_MAX_TIME_MINUTES = 5  # 2-5 minute window
DEFAULT_COMPLEXITY_THRESHOLD = 5  # Auto-split above this
DEFAULT_AUTO_SPLIT_ENABLED = True

# Tokens per line estimate (varies by language, ~15-25 typical)
TOKENS_PER_LINE_ESTIMATE = 20
# Average lines per file estimate
LINES_PER_FILE_ESTIMATE = 100


@dataclass
class TaskSizeConfig:
    """Configuration for task complexity assessment.

    Uses multi-dimensional constraints rather than file counts alone.

    Attributes:
        max_files_to_create: Soft limit on files to create (guidance)
        max_files_to_modify: Soft limit on files to modify (guidance)
        max_acceptance_criteria: Soft limit on acceptance criteria
        max_input_tokens: Maximum estimated input context tokens
        max_output_tokens: Maximum estimated output tokens
        max_time_minutes: Maximum estimated execution time
        complexity_threshold: Score threshold for auto-split (0-13 scale)
        auto_split_enabled: Whether to automatically split complex tasks
    """

    # Soft file limits (guidance, not hard failures)
    max_files_to_create: int = DEFAULT_MAX_FILES_TO_CREATE
    max_files_to_modify: int = DEFAULT_MAX_FILES_TO_MODIFY
    max_acceptance_criteria: int = DEFAULT_MAX_ACCEPTANCE_CRITERIA

    # Token budgets
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    # Time budget
    max_time_minutes: float = DEFAULT_MAX_TIME_MINUTES

    # Complexity threshold (0-13 scale)
    # < 5: Safe for autonomous
    # 5-7: Monitor closely
    # 8-10: Consider splitting
    # 11-13: Must split
    complexity_threshold: float = DEFAULT_COMPLEXITY_THRESHOLD

    # Auto-split behavior
    auto_split_enabled: bool = DEFAULT_AUTO_SPLIT_ENABLED

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.max_files_to_create < 1:
            raise ValueError("max_files_to_create must be at least 1")
        if self.max_files_to_modify < 1:
            raise ValueError("max_files_to_modify must be at least 1")
        if self.max_input_tokens < 1000:
            raise ValueError("max_input_tokens must be at least 1000")
        if self.max_output_tokens < 500:
            raise ValueError("max_output_tokens must be at least 500")
        if self.max_time_minutes < 0.5:
            raise ValueError("max_time_minutes must be at least 0.5")
        if not 0 <= self.complexity_threshold <= 13:
            raise ValueError("complexity_threshold must be between 0 and 13")

    @classmethod
    def from_project_config(cls, project_dir: Path) -> "TaskSizeConfig":
        """Load configuration from .project-config.json if present.

        Falls back to defaults for any missing values.

        Args:
            project_dir: Path to the project directory

        Returns:
            TaskSizeConfig instance with merged settings
        """
        config_path = project_dir / ".project-config.json"
        if not config_path.exists():
            logger.debug("No .project-config.json found, using defaults")
            return cls()

        try:
            config = json.loads(config_path.read_text())
            task_limits = config.get("task_size_limits", {})

            return cls(
                max_files_to_create=task_limits.get(
                    "max_files_to_create", DEFAULT_MAX_FILES_TO_CREATE
                ),
                max_files_to_modify=task_limits.get(
                    "max_files_to_modify", DEFAULT_MAX_FILES_TO_MODIFY
                ),
                max_acceptance_criteria=task_limits.get(
                    "max_criteria_per_task", DEFAULT_MAX_ACCEPTANCE_CRITERIA
                ),
                max_input_tokens=task_limits.get(
                    "max_input_tokens", DEFAULT_MAX_INPUT_TOKENS
                ),
                max_output_tokens=task_limits.get(
                    "max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS
                ),
                max_time_minutes=task_limits.get(
                    "max_time_minutes", DEFAULT_MAX_TIME_MINUTES
                ),
                complexity_threshold=task_limits.get(
                    "complexity_threshold", DEFAULT_COMPLEXITY_THRESHOLD
                ),
                auto_split_enabled=task_limits.get(
                    "auto_split", DEFAULT_AUTO_SPLIT_ENABLED
                ),
            )
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse .project-config.json: {e}, using defaults")
            return cls()

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "max_files_to_create": self.max_files_to_create,
            "max_files_to_modify": self.max_files_to_modify,
            "max_acceptance_criteria": self.max_acceptance_criteria,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_time_minutes": self.max_time_minutes,
            "complexity_threshold": self.complexity_threshold,
            "auto_split_enabled": self.auto_split_enabled,
        }


@dataclass
class ComplexityScore:
    """Composite complexity score for a task (0-13 scale).

    Components:
    - file_scope: 0-5 points (files touched, capped)
    - cross_file_deps: 0-2 points (architectural coupling)
    - semantic_complexity: 0-3 points (algorithmic vs structural)
    - requirement_uncertainty: 0-2 points (inference needed)
    - token_penalty: 0-1 point (if exceeds budget)

    Total: 0-13 scale
    - 0-4: LOW - Safe for autonomous execution
    - 5-7: MEDIUM - Requires monitoring
    - 8-10: HIGH - Consider decomposition
    - 11-13: CRITICAL - Must decompose
    """

    file_scope: float = 0.0
    cross_file_deps: float = 0.0
    semantic_complexity: float = 0.0
    requirement_uncertainty: float = 0.0
    token_penalty: float = 0.0

    @property
    def total(self) -> float:
        """Calculate total complexity score."""
        return (
            self.file_scope
            + self.cross_file_deps
            + self.semantic_complexity
            + self.requirement_uncertainty
            + self.token_penalty
        )

    @property
    def level(self) -> ComplexityLevel:
        """Get complexity level from total score."""
        score = self.total
        if score < 5:
            return ComplexityLevel.LOW
        elif score < 8:
            return ComplexityLevel.MEDIUM
        elif score < 11:
            return ComplexityLevel.HIGH
        else:
            return ComplexityLevel.CRITICAL

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "file_scope": self.file_scope,
            "cross_file_deps": self.cross_file_deps,
            "semantic_complexity": self.semantic_complexity,
            "requirement_uncertainty": self.requirement_uncertainty,
            "token_penalty": self.token_penalty,
            "total": self.total,
            "level": self.level.value,
        }


@dataclass
class TaskValidationResult:
    """Result of task complexity validation.

    Attributes:
        should_split: Whether task should be split (primary decision)
        complexity_score: Detailed complexity breakdown
        estimated_tokens: Estimated token consumption
        estimated_time_minutes: Estimated execution time
        warnings: Non-blocking warnings (soft limit violations)
        recommendation: Human-readable recommendation
    """

    should_split: bool
    complexity_score: ComplexityScore
    estimated_tokens: int = 0
    estimated_time_minutes: float = 0.0
    warnings: list[str] = field(default_factory=list)
    recommendation: str = ""

    @property
    def is_valid(self) -> bool:
        """Backwards compatibility: valid means should not split."""
        return not self.should_split

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "should_split": self.should_split,
            "is_valid": self.is_valid,
            "complexity_score": self.complexity_score.to_dict(),
            "estimated_tokens": self.estimated_tokens,
            "estimated_time_minutes": self.estimated_time_minutes,
            "warnings": self.warnings,
            "recommendation": self.recommendation,
        }


class ComplexityScorer:
    """Calculates composite complexity scores for tasks.

    Uses research-backed multi-dimensional assessment:
    1. File scope (0-5 points)
    2. Cross-file dependencies (0-2 points)
    3. Semantic complexity (0-3 points)
    4. Requirement uncertainty (0-2 points)
    5. Token penalty (0-1 point)

    Total: 0-13 scale
    """

    # Keywords indicating high semantic complexity
    HIGH_COMPLEXITY_KEYWORDS = [
        "algorithm", "optimize", "performance", "concurrent", "async",
        "parallel", "distributed", "cache", "index", "migration",
        "refactor", "architecture", "redesign", "security", "encrypt",
        "authentication", "authorization", "state machine", "workflow",
    ]

    # Keywords indicating medium complexity
    MEDIUM_COMPLEXITY_KEYWORDS = [
        "integrate", "api", "database", "query", "validation",
        "transform", "parse", "serialize", "handler", "middleware",
        "configuration", "schema", "model", "entity", "service",
    ]

    # Keywords indicating requirement uncertainty
    UNCERTAINTY_KEYWORDS = [
        "should", "might", "consider", "optional", "if needed",
        "possibly", "maybe", "tbd", "todo", "decide", "unclear",
        "flexible", "configurable", "depends on", "varies",
    ]

    def __init__(self, config: TaskSizeConfig):
        """Initialize scorer with configuration.

        Args:
            config: Task size configuration
        """
        self.config = config

    def score_task(self, task: dict) -> ComplexityScore:
        """Calculate complexity score for a task.

        Args:
            task: Task dictionary with standard fields

        Returns:
            ComplexityScore with breakdown
        """
        files_to_create = task.get("files_to_create", [])
        files_to_modify = task.get("files_to_modify", [])
        acceptance_criteria = task.get("acceptance_criteria", [])
        title = task.get("title", "")
        user_story = task.get("user_story", "")

        # 1. File scope score (0-5 points)
        # 0.5 points per file, capped at 5
        total_files = len(files_to_create) + len(files_to_modify)
        file_scope = min(total_files * 0.5, 5.0)

        # 2. Cross-file dependency score (0-2 points)
        cross_file_deps = self._score_cross_file_deps(
            files_to_create, files_to_modify
        )

        # 3. Semantic complexity score (0-3 points)
        text = f"{title} {user_story} {' '.join(acceptance_criteria)}".lower()
        semantic_complexity = self._score_semantic_complexity(text)

        # 4. Requirement uncertainty score (0-2 points)
        requirement_uncertainty = self._score_uncertainty(
            text, acceptance_criteria
        )

        # 5. Token penalty (0-1 point)
        estimated_tokens = self._estimate_tokens(task)
        token_penalty = 0.0
        if estimated_tokens > self.config.max_input_tokens:
            token_penalty = 1.0
        elif estimated_tokens > self.config.max_input_tokens * 0.8:
            token_penalty = 0.5

        return ComplexityScore(
            file_scope=file_scope,
            cross_file_deps=cross_file_deps,
            semantic_complexity=semantic_complexity,
            requirement_uncertainty=requirement_uncertainty,
            token_penalty=token_penalty,
        )

    def _score_cross_file_deps(
        self,
        files_to_create: list[str],
        files_to_modify: list[str],
    ) -> float:
        """Score cross-file dependencies (0-2 points).

        Higher score if files span multiple directories or architectural layers.
        """
        all_files = files_to_create + files_to_modify
        if len(all_files) <= 1:
            return 0.0

        # Get unique directories
        directories = set()
        for f in all_files:
            parent = str(Path(f).parent)
            # Normalize to top-level directory
            parts = parent.split("/")
            if parts:
                directories.add(parts[0])

        # More directories = more coupling
        if len(directories) >= 4:
            return 2.0
        elif len(directories) >= 3:
            return 1.5
        elif len(directories) >= 2:
            return 1.0

        # Check for architectural layer mixing
        layer_keywords = {
            "models": "data",
            "views": "presentation",
            "controllers": "presentation",
            "services": "business",
            "repositories": "data",
            "handlers": "presentation",
            "utils": "infrastructure",
            "api": "presentation",
            "core": "business",
        }

        layers_touched = set()
        for f in all_files:
            f_lower = f.lower()
            for keyword, layer in layer_keywords.items():
                if keyword in f_lower:
                    layers_touched.add(layer)

        if len(layers_touched) >= 3:
            return 2.0
        elif len(layers_touched) >= 2:
            return 1.0

        return 0.5 if len(all_files) > 3 else 0.0

    def _score_semantic_complexity(self, text: str) -> float:
        """Score semantic complexity (0-3 points).

        Based on presence of complexity-indicating keywords.
        """
        high_count = sum(1 for kw in self.HIGH_COMPLEXITY_KEYWORDS if kw in text)
        medium_count = sum(1 for kw in self.MEDIUM_COMPLEXITY_KEYWORDS if kw in text)

        if high_count >= 3:
            return 3.0
        elif high_count >= 2:
            return 2.5
        elif high_count >= 1:
            return 2.0
        elif medium_count >= 3:
            return 1.5
        elif medium_count >= 2:
            return 1.0
        elif medium_count >= 1:
            return 0.5

        return 0.0

    def _score_uncertainty(
        self,
        text: str,
        acceptance_criteria: list[str],
    ) -> float:
        """Score requirement uncertainty (0-2 points).

        Based on vague language and criteria clarity.
        """
        uncertainty_count = sum(
            1 for kw in self.UNCERTAINTY_KEYWORDS if kw in text
        )

        score = 0.0

        # Uncertainty keywords
        if uncertainty_count >= 3:
            score += 1.5
        elif uncertainty_count >= 2:
            score += 1.0
        elif uncertainty_count >= 1:
            score += 0.5

        # Vague criteria (too short or too long)
        if acceptance_criteria:
            avg_len = sum(len(c) for c in acceptance_criteria) / len(acceptance_criteria)
            if avg_len < 20:  # Too vague
                score += 0.5
            elif avg_len > 200:  # Too complex
                score += 0.5

        return min(score, 2.0)

    def _estimate_tokens(self, task: dict) -> int:
        """Estimate input token consumption for a task.

        Rough estimation based on:
        - Task description and criteria
        - Files to read for context
        - Expected code context
        """
        # Base tokens for task specification
        title = task.get("title", "")
        user_story = task.get("user_story", "")
        criteria = task.get("acceptance_criteria", [])

        spec_text = f"{title}\n{user_story}\n" + "\n".join(criteria)
        spec_tokens = len(spec_text.split()) * 1.3  # ~1.3 tokens per word

        # Estimate tokens for file context
        files_to_create = task.get("files_to_create", [])
        files_to_modify = task.get("files_to_modify", [])

        # Files to modify need to be read first
        file_context_tokens = len(files_to_modify) * LINES_PER_FILE_ESTIMATE * TOKENS_PER_LINE_ESTIMATE

        # New files need examples/patterns
        new_file_tokens = len(files_to_create) * 50  # Template overhead

        return int(spec_tokens + file_context_tokens + new_file_tokens)

    def estimate_time_minutes(self, task: dict) -> float:
        """Estimate execution time in minutes.

        Based on file count, complexity, and typical agent performance.
        """
        files_to_create = task.get("files_to_create", [])
        files_to_modify = task.get("files_to_modify", [])
        total_files = len(files_to_create) + len(files_to_modify)

        # Base time: 0.5 min per file
        base_time = total_files * 0.5

        # Complexity multiplier
        score = self.score_task(task)
        if score.level == ComplexityLevel.LOW:
            multiplier = 1.0
        elif score.level == ComplexityLevel.MEDIUM:
            multiplier = 1.5
        elif score.level == ComplexityLevel.HIGH:
            multiplier = 2.0
        else:
            multiplier = 3.0

        # Minimum 1 minute, account for overhead
        return max(1.0, base_time * multiplier)


def validate_task_complexity(
    task: dict,
    config: TaskSizeConfig,
) -> TaskValidationResult:
    """Validate task complexity using multi-dimensional assessment.

    Primary decision is based on complexity score, not file counts.
    File limits generate warnings but don't force splits.

    Args:
        task: Task dictionary
        config: Configuration with thresholds

    Returns:
        TaskValidationResult with split decision and details
    """
    scorer = ComplexityScorer(config)
    complexity_score = scorer.score_task(task)
    estimated_tokens = scorer._estimate_tokens(task)
    estimated_time = scorer.estimate_time_minutes(task)

    warnings = []
    files_to_create = task.get("files_to_create", [])
    files_to_modify = task.get("files_to_modify", [])
    acceptance_criteria = task.get("acceptance_criteria", [])

    # Soft limit warnings (don't force splits)
    if len(files_to_create) > config.max_files_to_create:
        warnings.append(
            f"files_to_create ({len(files_to_create)}) exceeds guidance of {config.max_files_to_create}"
        )

    if len(files_to_modify) > config.max_files_to_modify:
        warnings.append(
            f"files_to_modify ({len(files_to_modify)}) exceeds guidance of {config.max_files_to_modify}"
        )

    if len(acceptance_criteria) > config.max_acceptance_criteria:
        warnings.append(
            f"acceptance_criteria ({len(acceptance_criteria)}) exceeds guidance of {config.max_acceptance_criteria}"
        )

    if estimated_tokens > config.max_input_tokens:
        warnings.append(
            f"estimated_tokens ({estimated_tokens}) exceeds budget of {config.max_input_tokens}"
        )

    if estimated_time > config.max_time_minutes:
        warnings.append(
            f"estimated_time ({estimated_time:.1f}min) exceeds budget of {config.max_time_minutes}min"
        )

    # Primary split decision: based on complexity score
    should_split = complexity_score.total > config.complexity_threshold

    # Build recommendation
    if should_split:
        recommendation = (
            f"Task '{task.get('id', 'unknown')}' has complexity score "
            f"{complexity_score.total:.1f} (threshold: {config.complexity_threshold}). "
            f"Level: {complexity_score.level.value.upper()}. "
            f"Recommendation: Split into smaller tasks."
        )
    elif warnings:
        recommendation = (
            f"Task '{task.get('id', 'unknown')}' is within complexity threshold "
            f"({complexity_score.total:.1f}/{config.complexity_threshold}) but has warnings: "
            f"{'; '.join(warnings)}"
        )
    else:
        recommendation = (
            f"Task '{task.get('id', 'unknown')}' is well-sized. "
            f"Complexity: {complexity_score.total:.1f} ({complexity_score.level.value})"
        )

    return TaskValidationResult(
        should_split=should_split,
        complexity_score=complexity_score,
        estimated_tokens=estimated_tokens,
        estimated_time_minutes=estimated_time,
        warnings=warnings,
        recommendation=recommendation,
    )


# Backwards compatibility aliases
def _validate_task_granularity(task: dict, config: TaskSizeConfig) -> TaskValidationResult:
    """Backwards compatible alias for validate_task_complexity."""
    return validate_task_complexity(task, config)


# Keep old defaults available for backwards compatibility
DEFAULT_MAX_ESTIMATED_TOKENS = DEFAULT_MAX_INPUT_TOKENS
