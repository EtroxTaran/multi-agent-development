"""LangGraph integrations with existing utilities.

Adapters that wrap existing orchestrator utilities for use
within LangGraph workflow nodes.
"""

from .approval import LangGraphApprovalAdapter
from .conflict import LangGraphConflictAdapter
from .state import LangGraphStateAdapter
from .resilience import AsyncCircuitBreaker, async_retry_with_backoff
from .linear import (
    LinearAdapter,
    LinearConfig,
    create_linear_adapter,
    load_linear_config,
    save_issue_mapping,
    load_issue_mapping,
)
from .ralph_loop import (
    RalphLoopConfig,
    RalphLoopResult,
    run_ralph_loop,
    detect_test_framework,
    COMPLETION_PROMISE,
)

__all__ = [
    "LangGraphApprovalAdapter",
    "LangGraphConflictAdapter",
    "LangGraphStateAdapter",
    "AsyncCircuitBreaker",
    "async_retry_with_backoff",
    # Linear integration
    "LinearAdapter",
    "LinearConfig",
    "create_linear_adapter",
    "load_linear_config",
    "save_issue_mapping",
    "load_issue_mapping",
    # Ralph Wiggum loop integration
    "RalphLoopConfig",
    "RalphLoopResult",
    "run_ralph_loop",
    "detect_test_framework",
    "COMPLETION_PROMISE",
]
