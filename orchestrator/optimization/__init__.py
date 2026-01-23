"""Prompt optimization engine for auto-improvement.

This module provides:
- OPRO-style optimization using LLM to generate better prompts
- Few-shot bootstrapping from golden examples
- Optimization scheduling and triggering
- Safe deployment with progressive rollout
"""

from .optimizer import PromptOptimizer, OptimizationResult
from .opro import OPROOptimizer
from .bootstrap import BootstrapOptimizer
from .scheduler import OptimizationScheduler
from .deployer import DeploymentController, DeploymentResult

__all__ = [
    "PromptOptimizer",
    "OptimizationResult",
    "OPROOptimizer",
    "BootstrapOptimizer",
    "OptimizationScheduler",
    "DeploymentController",
    "DeploymentResult",
]
