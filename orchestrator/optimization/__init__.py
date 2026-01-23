"""Prompt optimization engine for auto-improvement.

This module provides:
- OPRO-style optimization using LLM to generate better prompts
- Few-shot bootstrapping from golden examples
- Optimization scheduling and triggering
- Safe deployment with progressive rollout
"""

from .bootstrap import BootstrapOptimizer
from .deployer import DeploymentController, DeploymentResult
from .opro import OPROOptimizer
from .optimizer import OptimizationResult, PromptOptimizer
from .scheduler import OptimizationScheduler

__all__ = [
    "PromptOptimizer",
    "OptimizationResult",
    "OPROOptimizer",
    "BootstrapOptimizer",
    "OptimizationScheduler",
    "DeploymentController",
    "DeploymentResult",
]
