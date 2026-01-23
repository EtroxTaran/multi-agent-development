"""LangGraph workflow orchestration.

Provides graph-based workflow orchestration with native parallelism,
checkpointing, and human-in-the-loop support.

Main components:
- WorkflowState: TypedDict state schema with reducers
- Nodes: Async functions that process workflow steps
- Routers: Decision functions for conditional edges
- Integrations: Adapters for existing utilities
- Workflow: Complete graph assembly and runner
"""

from .integrations import (  # LangGraphStateAdapter deprecated - use WorkflowStorageAdapter
    AsyncCircuitBreaker,
    LangGraphApprovalAdapter,
    LangGraphConflictAdapter,
    async_retry_with_backoff,
)
from .routers import (
    completion_router,
    human_escalation_router,
    implementation_router,
    planning_router,
    prerequisites_router,
    validation_router,
    verification_router,
)
from .state import (
    AgentFeedback,
    PhaseState,
    PhaseStatus,
    WorkflowDecision,
    WorkflowState,
    can_proceed_to_phase,
    create_initial_state,
    get_phase_state,
    get_workflow_summary,
    update_phase_state,
)
from .workflow import (
    WorkflowRunner,
    create_workflow_graph,
    get_workflow_runner,
    resume_workflow,
    run_workflow,
)

__all__ = [
    # State
    "WorkflowState",
    "PhaseStatus",
    "PhaseState",
    "WorkflowDecision",
    "AgentFeedback",
    "create_initial_state",
    "get_phase_state",
    "update_phase_state",
    "can_proceed_to_phase",
    "get_workflow_summary",
    # Workflow
    "create_workflow_graph",
    "WorkflowRunner",
    "get_workflow_runner",
    "run_workflow",
    "resume_workflow",
    # Routers
    "validation_router",
    "verification_router",
    "prerequisites_router",
    "planning_router",
    "implementation_router",
    "completion_router",
    "human_escalation_router",
    # Integrations
    "LangGraphApprovalAdapter",
    "LangGraphConflictAdapter",
    # LangGraphStateAdapter deprecated
    "AsyncCircuitBreaker",
    "async_retry_with_backoff",
]
