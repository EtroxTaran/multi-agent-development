"""Repository layer for SurrealDB operations.

Provides typed, domain-specific data access for orchestrator entities.
"""

from .audit import AuditRepository, get_audit_repository
from .budget import BudgetRepository, get_budget_repository
from .checkpoints import CheckpointRepository, get_checkpoint_repository
from .evaluation import EvaluationRepository, get_evaluation_repository
from .logs import LogsRepository, LogType, get_logs_repository
from .phase_outputs import OutputType, PhaseOutputRepository, get_phase_output_repository
from .prompts import (
    GoldenExampleRepository,
    OptimizationHistoryRepository,
    OptimizationMethod,
    PromptStatus,
    PromptVersionRepository,
    get_golden_example_repository,
    get_optimization_history_repository,
    get_prompt_version_repository,
)
from .sessions import SessionRepository, get_session_repository
from .tasks import TaskRepository, get_task_repository
from .workflow import WorkflowRepository, get_workflow_repository

__all__ = [
    "AuditRepository",
    "get_audit_repository",
    "WorkflowRepository",
    "get_workflow_repository",
    "TaskRepository",
    "get_task_repository",
    "CheckpointRepository",
    "get_checkpoint_repository",
    "SessionRepository",
    "get_session_repository",
    "BudgetRepository",
    "get_budget_repository",
    "PhaseOutputRepository",
    "get_phase_output_repository",
    "OutputType",
    "LogsRepository",
    "get_logs_repository",
    "LogType",
    # Auto-improvement repositories
    "EvaluationRepository",
    "get_evaluation_repository",
    "PromptVersionRepository",
    "get_prompt_version_repository",
    "GoldenExampleRepository",
    "get_golden_example_repository",
    "OptimizationHistoryRepository",
    "get_optimization_history_repository",
    "PromptStatus",
    "OptimizationMethod",
]
