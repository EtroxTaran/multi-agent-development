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

from .state import (
    WorkflowState,
    PhaseStatus,
    PhaseState,
    WorkflowDecision,
    AgentFeedback,
    create_initial_state,
    get_phase_state,
    update_phase_state,
    can_proceed_to_phase,
    get_workflow_summary,
)

from .workflow import (
    create_workflow_graph,
    WorkflowRunner,
    get_workflow_runner,
    run_workflow,
    resume_workflow,
)

from .routers import (
    validation_router,
    verification_router,
    prerequisites_router,
    planning_router,
    implementation_router,
    completion_router,
    human_escalation_router,
)

from .integrations import (
    LangGraphApprovalAdapter,
    LangGraphConflictAdapter,
    LangGraphStateAdapter,
    AsyncCircuitBreaker,
    async_retry_with_backoff,
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
    "LangGraphStateAdapter",
    "AsyncCircuitBreaker",
    "async_retry_with_backoff",
]
