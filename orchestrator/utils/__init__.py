"""Utility modules for the orchestrator."""

# Data models moved to orchestrator.models (DB-only storage)
from orchestrator.models import PhaseState, PhaseStatus, WorkflowState

from .action_log import (
    ActionEntry,
    ActionLog,
    ActionStatus,
    ActionType,
    ErrorInfo,
    get_action_log,
    reset_action_log,
)
from .approval import (
    AgentFeedback,
    ApprovalConfig,
    ApprovalEngine,
    ApprovalPolicy,
    ApprovalResult,
    ApprovalStatus,
)
from .boundaries import (
    ORCHESTRATOR_FORBIDDEN_PATTERNS,
    ORCHESTRATOR_WRITABLE_PATTERNS,
    OrchestratorBoundaryError,
    ensure_orchestrator_can_write,
    get_writable_paths_info,
    is_project_config,
    is_workflow_path,
    validate_orchestrator_write,
)
from .conflict_resolution import (
    Conflict,
    ConflictResolution,
    ConflictResolver,
    ConflictResult,
    ConflictType,
    ResolutionStrategy,
)
from .context import ContextManager, ContextState, DriftResult, FileChecksum
from .error_aggregator import (
    AggregatedError,
    ErrorAggregator,
    ErrorSeverity,
    ErrorSource,
    get_error_aggregator,
    reset_error_aggregator,
)
from .handoff import HandoffBrief, HandoffGenerator, generate_handoff
from .log_manager import CleanupResult, LogManager, LogRotationConfig, should_auto_cleanup
from .log_manager import load_config as load_log_config
from .logging import OrchestrationLogger

# Checkpoint manager removed - using DB-based checkpoints via storage adapters
from .task_config import (
    DEFAULT_AUTO_SPLIT_ENABLED,
    DEFAULT_COMPLEXITY_THRESHOLD,
    DEFAULT_MAX_ACCEPTANCE_CRITERIA,
    DEFAULT_MAX_ESTIMATED_TOKENS,
    DEFAULT_MAX_FILES_TO_CREATE,
    DEFAULT_MAX_FILES_TO_MODIFY,
    DEFAULT_MAX_INPUT_TOKENS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_TIME_MINUTES,
    ComplexityLevel,
    ComplexityScore,
    ComplexityScorer,
    TaskSizeConfig,
    TaskValidationResult,
    validate_task_complexity,
)
from .uat_generator import (
    FileChange,
    TestResults,
    UATDocument,
    UATGenerator,
    create_uat_generator,
    generate_uat_from_verification,
)
from .validation import (
    AgentFeedbackSchema,
    AssessmentType,
    FeedbackItem,
    ProductSpecValidator,
    ValidationResult,
    validate_feedback,
)
from .worktree import WorktreeError, WorktreeInfo, WorktreeManager

__all__ = [
    # Data models (from orchestrator.models)
    "PhaseStatus",
    "PhaseState",
    "WorkflowState",
    # Logging
    "OrchestrationLogger",
    # Context management
    "ContextManager",
    "ContextState",
    "FileChecksum",
    "DriftResult",
    # Approval engine
    "ApprovalEngine",
    "ApprovalConfig",
    "ApprovalPolicy",
    "ApprovalStatus",
    "ApprovalResult",
    "AgentFeedback",
    # Conflict resolution
    "ConflictResolver",
    "ResolutionStrategy",
    "ConflictType",
    "Conflict",
    "ConflictResolution",
    "ConflictResult",
    # Validation
    "ProductSpecValidator",
    "AgentFeedbackSchema",
    "AssessmentType",
    "FeedbackItem",
    "ValidationResult",
    "validate_feedback",
    # Action log (observability)
    "ActionLog",
    "ActionEntry",
    "ActionType",
    "ActionStatus",
    "ErrorInfo",
    "get_action_log",
    "reset_action_log",
    # Error aggregator
    "ErrorAggregator",
    "AggregatedError",
    "ErrorSource",
    "ErrorSeverity",
    "get_error_aggregator",
    "reset_error_aggregator",
    # Log manager
    "LogManager",
    "LogRotationConfig",
    "CleanupResult",
    "load_log_config",
    "should_auto_cleanup",
    # Handoff
    "HandoffBrief",
    "HandoffGenerator",
    "generate_handoff",
    # File boundaries
    "OrchestratorBoundaryError",
    "validate_orchestrator_write",
    "ensure_orchestrator_can_write",
    "get_writable_paths_info",
    "is_workflow_path",
    "is_project_config",
    "ORCHESTRATOR_WRITABLE_PATTERNS",
    "ORCHESTRATOR_FORBIDDEN_PATTERNS",
    # Git worktrees
    "WorktreeManager",
    "WorktreeError",
    "WorktreeInfo",
    # UAT generator (GSD pattern)
    "UATDocument",
    "UATGenerator",
    "FileChange",
    "TestResults",
    "create_uat_generator",
    "generate_uat_from_verification",
    # Checkpoint functionality moved to DB-based storage adapters
    # Task size configuration and complexity scoring
    "TaskSizeConfig",
    "TaskValidationResult",
    "ComplexityLevel",
    "ComplexityScore",
    "ComplexityScorer",
    "validate_task_complexity",
    "DEFAULT_MAX_FILES_TO_CREATE",
    "DEFAULT_MAX_FILES_TO_MODIFY",
    "DEFAULT_MAX_ACCEPTANCE_CRITERIA",
    "DEFAULT_MAX_ESTIMATED_TOKENS",
    "DEFAULT_AUTO_SPLIT_ENABLED",
    "DEFAULT_COMPLEXITY_THRESHOLD",
    "DEFAULT_MAX_INPUT_TOKENS",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_MAX_TIME_MINUTES",
]
