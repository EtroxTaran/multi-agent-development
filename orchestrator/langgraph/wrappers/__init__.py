"""Universal node wrappers for global error handling and agent tracking.

This package provides decorators and utilities for wrapping all LangGraph nodes
to ensure:
1. All errors are captured with rich context and routed to the Bugfixer
2. All agent executions are tracked and routed to evaluation
3. Consistent state updates across all nodes
"""

from .node_wrapper import (
    wrapped_node,
    NodeWrapper,
    AGENT_NODES,
    get_node_metadata,
)
from .execution_tracker import (
    ExecutionTracker,
    track_agent_execution,
    get_execution_tracker,
)

__all__ = [
    # Node wrapper
    "wrapped_node",
    "NodeWrapper",
    "AGENT_NODES",
    "get_node_metadata",
    # Execution tracker
    "ExecutionTracker",
    "track_agent_execution",
    "get_execution_tracker",
]
