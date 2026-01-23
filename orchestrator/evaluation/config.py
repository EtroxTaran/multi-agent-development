"""Configuration for auto-improvement system.

Provides dataclasses for configuring evaluation, optimization,
and deployment behavior. Configuration is loaded from .project-config.json.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EvaluationConfig:
    """Configuration for agent evaluation.

    Attributes:
        enabled: Whether to run evaluations
        model: Model to use for evaluation (haiku recommended)
        min_samples_for_optimization: Minimum evaluations before optimization
        sampling_rate: Rate of evaluations to run (0.0-1.0)
        max_cost_per_eval: Maximum cost per evaluation in USD
    """

    enabled: bool = True
    model: str = "haiku"
    min_samples_for_optimization: int = 10
    sampling_rate: float = 1.0  # Evaluate 100% by default
    max_cost_per_eval: float = 0.05  # ~$0.05 per full evaluation


@dataclass
class OptimizationConfig:
    """Configuration for prompt optimization.

    Attributes:
        enabled: Whether to run optimizations
        method: Optimization method (opro, bootstrap, auto)
        optimization_threshold: Score below which to trigger optimization
        improvement_threshold: Minimum improvement to accept new prompt
        max_attempts: Maximum optimization attempts per template
        cooldown_hours: Hours between optimization attempts
    """

    enabled: bool = True
    method: str = "auto"  # auto, opro, bootstrap
    optimization_threshold: float = 7.0
    improvement_threshold: float = 0.5
    max_attempts: int = 3
    cooldown_hours: int = 24


@dataclass
class DeploymentConfig:
    """Configuration for prompt deployment.

    Attributes:
        shadow_test_count: Number of shadow tests before promotion
        canary_percentage: Percentage of traffic for canary
        canary_test_count: Number of canary tests before promotion
        rollback_threshold: Score drop that triggers rollback
        minimum_score: Minimum score to maintain
        auto_promote: Whether to auto-promote successful versions
    """

    shadow_test_count: int = 10
    canary_percentage: float = 0.1
    canary_test_count: int = 10
    rollback_threshold: float = -0.5
    minimum_score: float = 5.0
    auto_promote: bool = True


@dataclass
class AutoImprovementConfig:
    """Top-level configuration for auto-improvement system.

    Attributes:
        evaluation: Evaluation configuration
        optimization: Optimization configuration
        deployment: Deployment configuration
    """

    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    optimization: OptimizationConfig = field(default_factory=OptimizationConfig)
    deployment: DeploymentConfig = field(default_factory=DeploymentConfig)

    @classmethod
    def load(cls, project_dir: str | Path) -> "AutoImprovementConfig":
        """Load configuration from .project-config.json.

        Args:
            project_dir: Project directory containing config file

        Returns:
            AutoImprovementConfig with loaded or default values
        """
        config_path = Path(project_dir) / ".project-config.json"

        if not config_path.exists():
            logger.debug(f"No config file at {config_path}, using defaults")
            return cls()

        try:
            with open(config_path) as f:
                data = json.load(f)

            ai_config = data.get("auto_improvement", {})

            return cls(
                evaluation=EvaluationConfig(
                    **{
                        k: v
                        for k, v in ai_config.get("evaluation", {}).items()
                        if k in EvaluationConfig.__dataclass_fields__
                    }
                ),
                optimization=OptimizationConfig(
                    **{
                        k: v
                        for k, v in ai_config.get("optimization", {}).items()
                        if k in OptimizationConfig.__dataclass_fields__
                    }
                ),
                deployment=DeploymentConfig(
                    **{
                        k: v
                        for k, v in ai_config.get("deployment", {}).items()
                        if k in DeploymentConfig.__dataclass_fields__
                    }
                ),
            )
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in config file: {e}")
            return cls()
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")
            return cls()

    def to_dict(self) -> dict:
        """Convert to dictionary for storage/transmission.

        Returns:
            Dictionary representation
        """
        return {
            "evaluation": {
                "enabled": self.evaluation.enabled,
                "model": self.evaluation.model,
                "min_samples_for_optimization": self.evaluation.min_samples_for_optimization,
                "sampling_rate": self.evaluation.sampling_rate,
                "max_cost_per_eval": self.evaluation.max_cost_per_eval,
            },
            "optimization": {
                "enabled": self.optimization.enabled,
                "method": self.optimization.method,
                "optimization_threshold": self.optimization.optimization_threshold,
                "improvement_threshold": self.optimization.improvement_threshold,
                "max_attempts": self.optimization.max_attempts,
                "cooldown_hours": self.optimization.cooldown_hours,
            },
            "deployment": {
                "shadow_test_count": self.deployment.shadow_test_count,
                "canary_percentage": self.deployment.canary_percentage,
                "canary_test_count": self.deployment.canary_test_count,
                "rollback_threshold": self.deployment.rollback_threshold,
                "minimum_score": self.deployment.minimum_score,
                "auto_promote": self.deployment.auto_promote,
            },
        }


# Singleton for caching loaded config
_config_cache: dict[str, AutoImprovementConfig] = {}


def get_config(project_dir: str | Path) -> AutoImprovementConfig:
    """Get auto-improvement configuration for a project.

    Caches configuration to avoid repeated file reads.

    Args:
        project_dir: Project directory

    Returns:
        AutoImprovementConfig for the project
    """
    project_dir = str(Path(project_dir).resolve())

    if project_dir not in _config_cache:
        _config_cache[project_dir] = AutoImprovementConfig.load(project_dir)

    return _config_cache[project_dir]


def clear_config_cache(project_dir: Optional[str | Path] = None) -> None:
    """Clear configuration cache.

    Args:
        project_dir: Specific project to clear, or None to clear all
    """
    if project_dir is None:
        _config_cache.clear()
    else:
        project_dir = str(Path(project_dir).resolve())
        _config_cache.pop(project_dir, None)
