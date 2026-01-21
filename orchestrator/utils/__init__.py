"""Utility modules for the orchestrator."""

from .state import StateManager, PhaseStatus, PhaseState, WorkflowState
from .logging import OrchestrationLogger
from .context import ContextManager, ContextState, FileChecksum, DriftResult
from .approval import (
    ApprovalEngine,
    ApprovalConfig,
    ApprovalPolicy,
    ApprovalStatus,
    ApprovalResult,
    AgentFeedback,
)
from .conflict_resolution import (
    ConflictResolver,
    ResolutionStrategy,
    ConflictType,
    Conflict,
    ConflictResolution,
    ConflictResult,
)
from .validation import (
    ProductSpecValidator,
    AgentFeedbackSchema,
    AssessmentType,
    FeedbackItem,
    ValidationResult,
    validate_feedback,
)
from .action_log import (
    ActionLog,
    ActionEntry,
    ActionType,
    ActionStatus,
    ErrorInfo,
    get_action_log,
    reset_action_log,
)
from .error_aggregator import (
    ErrorAggregator,
    AggregatedError,
    ErrorSource,
    ErrorSeverity,
    get_error_aggregator,
    reset_error_aggregator,
)
from .log_manager import (
    LogManager,
    LogRotationConfig,
    CleanupResult,
    load_config as load_log_config,
    should_auto_cleanup,
)
from .handoff import (
    HandoffBrief,
    HandoffGenerator,
    generate_handoff,
)
from .boundaries import (
    OrchestratorBoundaryError,
    validate_orchestrator_write,
    ensure_orchestrator_can_write,
    get_writable_paths_info,
    is_workflow_path,
    is_project_config,
    ORCHESTRATOR_WRITABLE_PATTERNS,
    ORCHESTRATOR_FORBIDDEN_PATTERNS,
)
from .worktree import (
    WorktreeManager,
    WorktreeError,
    WorktreeInfo,
)

__all__ = [
    # State management
    "StateManager",
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
]
