"""Agent dispatch protocol module."""

from orchestrator.dispatch.protocol import (
    AgentDispatcher,
    DispatchResult,
    Task,
    InvalidTaskAssignment,
    InvalidAgentOutput,
)

__all__ = [
    "AgentDispatcher",
    "DispatchResult",
    "Task",
    "InvalidTaskAssignment",
    "InvalidAgentOutput",
]
