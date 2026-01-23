"""Auto-improvement evaluation system for LangGraph agents.

This module provides:
- G-Eval based evaluation of agent outputs
- Multi-dimensional quality scoring
- Pattern analysis for common failures
- Improvement suggestion generation
"""

from .analyzer import AnalysisResult, OutputAnalyzer
from .config import (
    AutoImprovementConfig,
    DeploymentConfig,
    EvaluationConfig,
    OptimizationConfig,
    clear_config_cache,
    get_config,
)
from .evaluator import AgentEvaluator, EvaluationResult
from .g_eval import GEvalEvaluator
from .metrics import EVALUATION_CRITERIA, EvaluationMetric, MetricWeight, compute_weighted_score

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
