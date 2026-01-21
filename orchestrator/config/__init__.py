"""Configuration package for workflow settings.

Provides configurable thresholds, feature flags, and project-type
specific defaults.
"""

from .thresholds import (
    ProjectConfig,
    ValidationConfig,
    QualityConfig,
    SecurityConfig,
    WorkflowConfig,
    DEFAULT_CONFIGS,
    get_project_config,
    load_project_config,
)

__all__ = [
    "ProjectConfig",
    "ValidationConfig",
    "QualityConfig",
    "SecurityConfig",
    "WorkflowConfig",
    "DEFAULT_CONFIGS",
    "get_project_config",
    "load_project_config",
]
