"""Auto-improvement evaluation system for LangGraph agents.

This module provides:
- G-Eval based evaluation of agent outputs
- Multi-dimensional quality scoring
- Pattern analysis for common failures
- Improvement suggestion generation
"""

from .evaluator import AgentEvaluator, EvaluationResult
from .metrics import (
    EvaluationMetric,
    MetricWeight,
    EVALUATION_CRITERIA,
    compute_weighted_score,
)
from .g_eval import GEvalEvaluator
from .analyzer import OutputAnalyzer, AnalysisResult
from .config import (
    AutoImprovementConfig,
    EvaluationConfig,
    OptimizationConfig,
    DeploymentConfig,
    get_config,
    clear_config_cache,
)

__all__ = [
    "AgentEvaluator",
    "EvaluationResult",
    "EvaluationMetric",
    "MetricWeight",
    "EVALUATION_CRITERIA",
    "compute_weighted_score",
    "GEvalEvaluator",
    "OutputAnalyzer",
    "AnalysisResult",
    # Configuration
    "AutoImprovementConfig",
    "EvaluationConfig",
    "OptimizationConfig",
    "DeploymentConfig",
    "get_config",
    "clear_config_cache",
]
