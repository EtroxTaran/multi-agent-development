"""Repository layer for SurrealDB operations.

Provides typed, domain-specific data access for orchestrator entities.
"""

from .audit import AuditRepository, get_audit_repository
from .workflow import WorkflowRepository, get_workflow_repository
from .tasks import TaskRepository, get_task_repository
from .checkpoints import CheckpointRepository, get_checkpoint_repository
from .sessions import SessionRepository, get_session_repository
from .budget import BudgetRepository, get_budget_repository
from .phase_outputs import PhaseOutputRepository, get_phase_output_repository, OutputType
from .logs import LogsRepository, get_logs_repository, LogType
from .evaluation import EvaluationRepository, get_evaluation_repository
from .prompts import (
    PromptVersionRepository,
    GoldenExampleRepository,
    OptimizationHistoryRepository,
    get_prompt_version_repository,
    get_golden_example_repository,
    get_optimization_history_repository,
    PromptStatus,
    OptimizationMethod,
)

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
