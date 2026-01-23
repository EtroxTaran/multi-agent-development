"""Agent dispatch protocol module."""

from orchestrator.dispatch.protocol import (
    AgentDispatcher,
    DispatchResult,
    InvalidAgentOutput,
    InvalidTaskAssignment,
    Task,
)

__all__ = [
    "AgentDispatcher",
    "DispatchResult",
    "Task",
    "InvalidTaskAssignment",
    "InvalidAgentOutput",
]
