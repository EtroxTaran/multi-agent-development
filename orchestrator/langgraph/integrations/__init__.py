"""LangGraph integrations with existing utilities.

Adapters that wrap existing orchestrator utilities for use
within LangGraph workflow nodes.
"""

from .action_logging import NodeActionLogger, get_node_logger
from .approval import LangGraphApprovalAdapter
from .conflict import LangGraphConflictAdapter
from .hooks import HookManager, HookResult, create_hook_manager
from .linear import (
    LinearAdapter,
    LinearConfig,
    create_linear_adapter,
    load_issue_mapping,
    load_linear_config,
    save_issue_mapping,
)
from .markdown_tracker import (
    MarkdownTracker,
    MarkdownTrackerConfig,
    create_markdown_tracker,
    load_tracker_config,
)
from .ralph_loop import (  # New: Execution modes and token tracking
    COMPLETION_PROMISE,
    ExecutionMode,
    HookConfig,
    RalphLoopConfig,
    RalphLoopResult,
    TokenMetrics,
    TokenUsageTracker,
    create_ralph_config,
    detect_test_framework,
    run_ralph_loop,
)

# LangGraphStateAdapter deprecated - use WorkflowStorageAdapter instead
from .resilience import AsyncCircuitBreaker, async_retry_with_backoff
from .unified_loop import (
    LoopContext,
    UnifiedLoopConfig,
    UnifiedLoopResult,
    UnifiedLoopRunner,
    create_runner_from_task,
    create_unified_runner,
    should_use_unified_loop,
)
from .verification import (
    CompositeVerification,
    LintVerification,
    NoVerification,
    SecurityVerification,
    TestVerification,
    VerificationContext,
    VerificationResult,
    VerificationStrategy,
    VerificationType,
    create_composite_verifier,
    create_verifier,
)

__all__ = [
    "LangGraphApprovalAdapter",
    "LangGraphConflictAdapter",
    # LangGraphStateAdapter deprecated - use WorkflowStorageAdapter
    "AsyncCircuitBreaker",
    "async_retry_with_backoff",
    # Linear integration
    "LinearAdapter",
    "LinearConfig",
    "create_linear_adapter",
    "load_linear_config",
    "save_issue_mapping",
    "load_issue_mapping",
    # Markdown task tracker
    "MarkdownTracker",
    "MarkdownTrackerConfig",
    "create_markdown_tracker",
    "load_tracker_config",
    # Ralph Wiggum loop integration (Claude only - legacy)
    "RalphLoopConfig",
    "RalphLoopResult",
    "run_ralph_loop",
    "detect_test_framework",
    "COMPLETION_PROMISE",
    "ExecutionMode",
    "HookConfig",
    "TokenMetrics",
    "TokenUsageTracker",
    "create_ralph_config",
    # Unified loop integration (all agents)
    "UnifiedLoopRunner",
    "UnifiedLoopConfig",
    "UnifiedLoopResult",
    "LoopContext",
    "create_unified_runner",
    "create_runner_from_task",
    "should_use_unified_loop",
    # Verification strategies
    "VerificationType",
    "VerificationStrategy",
    "VerificationContext",
    "VerificationResult",
    "TestVerification",
    "LintVerification",
    "SecurityVerification",
    "CompositeVerification",
    "NoVerification",
    "create_verifier",
    "create_composite_verifier",
    # Hook integration
    "HookManager",
    "HookResult",
    "create_hook_manager",
    # Action logging integration
    "NodeActionLogger",
    "get_node_logger",
]
