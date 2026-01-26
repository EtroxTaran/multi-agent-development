"""Event bridge for real-time workflow monitoring.

This package provides the infrastructure for emitting workflow events
from the orchestrator to the dashboard via SurrealDB live queries.

Architecture:
    LangGraph Node -> EventEmitter -> SurrealDB workflow_events
                                           |
    Dashboard Backend <- Live Query subscription
                                           |
    WebSocket -> Frontend

Usage:
    from orchestrator.events import create_dashboard_callback, EventEmitter

    # In workflow runner
    callback = create_dashboard_callback(project_name)

    # Emit events
    callback.on_node_start("planning", state)
    callback.on_task_start("T1", "Implement feature")
    callback.on_task_complete("T1", success=True)
"""

from .callback import DashboardCallback, create_dashboard_callback
from .emitter import EventEmitter, cleanup_old_events, create_event_emitter
from .types import (
    EventPriority,
    EventType,
    WorkflowEvent,
    agent_complete_event,
    agent_start_event,
    error_event,
    escalation_event,
    metrics_update_event,
    node_end_event,
    node_start_event,
    path_decision_event,
    phase_change_event,
    ralph_iteration_event,
    task_complete_event,
    task_start_event,
    workflow_complete_event,
    workflow_paused_event,
    workflow_start_event,
)

__all__ = [
    # Main classes
    "EventEmitter",
    "DashboardCallback",
    # Factory functions
    "create_event_emitter",
    "create_dashboard_callback",
    "cleanup_old_events",
    # Types
    "EventType",
    "EventPriority",
    "WorkflowEvent",
    # Event factories
    "node_start_event",
    "node_end_event",
    "phase_change_event",
    "task_start_event",
    "task_complete_event",
    "agent_start_event",
    "agent_complete_event",
    "error_event",
    "escalation_event",
    "ralph_iteration_event",
    "metrics_update_event",
    "workflow_start_event",
    "workflow_complete_event",
    "workflow_paused_event",
    "path_decision_event",
]
