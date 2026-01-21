"""LangGraph workflow graph assembly.

Assembles nodes and routers into a complete workflow graph
with parallel fan-out/fan-in, checkpoints, and human-in-the-loop.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..ui.callbacks import ProgressCallback

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, RetryPolicy

from .state import WorkflowState, create_initial_state
from .nodes import (
    prerequisites_node,
    planning_node,
    cursor_validate_node,
    gemini_validate_node,
    validation_fan_in_node,
    implementation_node,
    cursor_review_node,
    gemini_review_node,
    verification_fan_in_node,
    human_escalation_node,
    completion_node,
    # New risk mitigation nodes
    product_validation_node,
    pre_implementation_node,
    build_verification_node,
    coverage_check_node,
    security_scan_node,
    approval_gate_node,
    # Task loop nodes
    task_breakdown_node,
    select_next_task_node,
    implement_task_node,
    verify_task_node,
)
from .routers import (
    prerequisites_router,
    planning_router,
    validation_router,
    verification_router,
    implementation_router,
    completion_router,
    human_escalation_router,
    # New risk mitigation routers
    product_validation_router,
    pre_implementation_router,
    build_verification_router,
    coverage_check_router,
    security_scan_router,
    approval_gate_router,
    # Task loop routers
    task_breakdown_router,
    select_task_router,
    implement_task_router,
    verify_task_router,
)

logger = logging.getLogger(__name__)


def create_workflow_graph(
    checkpointer: Optional[Any] = None,
    enable_retry_policy: bool = False,
) -> StateGraph:
    """Create the LangGraph workflow graph.

    This creates a graph with:
    - Sequential phases with risk mitigation checks
    - Parallel fan-out/fan-in for validation and verification
    - Human escalation and approval gates
    - Configurable feature flags for optional nodes

    Enhanced workflow path with task loop:
    ```
    prerequisites → product_validation → planning →
    [cursor_validate || gemini_validate] → validation_fan_in →
    approval_gate → pre_implementation → task_breakdown →
    ┌─────────────────────────────────────────┐
    │            TASK LOOP                    │
    │  select_task → implement_task →         │
    │       ↑         verify_task ────────────┼──┐
    │       └─────────────────────────────────┘  │
    │              (loop back)                   │
    └────────────────────────────────────────────┘
                        │ (all tasks complete)
                        ↓
    build_verification →
    [cursor_review || gemini_review] → verification_fan_in →
    coverage_check → security_scan → completion
    ```

    Retry Policy (when enabled):
    - Agent nodes (cursor_*, gemini_*) have RetryPolicy for transient failures
    - Uses exponential backoff: initial_interval=1s, backoff_multiplier=2
    - Max retries: 3 attempts before failing

    Graph structure:
    ```
                     ┌─────────────────┐
                     │  prerequisites  │
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │product_validation│  ← NEW: Validates PRODUCT.md
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │    planning     │
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              │                               │
     ┌────────▼────────┐             ┌────────▼────────┐
     │ cursor_validate │             │ gemini_validate │
     └────────┬────────┘             └────────┬────────┘
              │                               │
              └───────────────┬───────────────┘
                              │
                     ┌────────▼────────┐
                     │validation_fan_in│
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │  approval_gate  │  ← NEW: Human approval (optional)
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │pre_implementation│  ← Environment checks
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │  task_breakdown │  ← NEW: Break into tasks
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │   select_task   │  ← TASK LOOP START
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │  implement_task │  ← Single task impl
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │   verify_task   │
                     └────────┬────────┘
                              │
                     (loop back to select_task)
                              │
                     (when all tasks done)
                              │
                     ┌────────▼────────┐
                     │build_verification│  ← Build check
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              │                               │
     ┌────────▼────────┐             ┌────────▼────────┐
     │  cursor_review  │             │  gemini_review  │
     └────────┬────────┘             └────────┬────────┘
              │                               │
              └───────────────┬───────────────┘
                              │
                     ┌────────▼────────┐
                     │verification_fan_in│
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │  coverage_check │  ← NEW: Coverage enforcement
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │  security_scan  │  ← NEW: Security scanning
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │   completion    │
                     └────────┬────────┘
                              │
                            [END]
    ```

    Human escalation can be reached from multiple nodes when issues occur.

    Args:
        checkpointer: Optional checkpointer for persistence
        enable_retry_policy: Enable retry policies for agent nodes

    Returns:
        Compiled StateGraph workflow
    """
    # Create the graph builder
    graph = StateGraph(WorkflowState)

    # Check if retry policy should be enabled
    retry_enabled = enable_retry_policy or os.environ.get("LANGGRAPH_RETRY_ENABLED", "").lower() == "true"

    # Create retry policies for different node types
    agent_retry_policy = RetryPolicy(
        max_attempts=3,
        initial_interval=1.0,
        backoff_factor=2.0,
        jitter=True,
    ) if retry_enabled else None

    implementation_retry_policy = RetryPolicy(
        max_attempts=2,
        initial_interval=5.0,
        backoff_factor=2.0,
        jitter=True,
    ) if retry_enabled else None

    # Add all nodes with appropriate retry policies
    # Core workflow nodes
    graph.add_node("prerequisites", prerequisites_node)
    graph.add_node("product_validation", product_validation_node)
    graph.add_node("planning", planning_node, retry=agent_retry_policy)
    graph.add_node("cursor_validate", cursor_validate_node, retry=agent_retry_policy)
    graph.add_node("gemini_validate", gemini_validate_node, retry=agent_retry_policy)
    graph.add_node("validation_fan_in", validation_fan_in_node)
    graph.add_node("approval_gate", approval_gate_node)
    graph.add_node("pre_implementation", pre_implementation_node)

    # Task loop nodes (incremental execution)
    graph.add_node("task_breakdown", task_breakdown_node)
    graph.add_node("select_task", select_next_task_node)
    graph.add_node("implement_task", implement_task_node, retry=implementation_retry_policy)
    graph.add_node("verify_task", verify_task_node)

    # Legacy implementation node (kept for compatibility)
    graph.add_node("implementation", implementation_node, retry=implementation_retry_policy)

    # Post-implementation nodes
    graph.add_node("build_verification", build_verification_node)
    graph.add_node("cursor_review", cursor_review_node, retry=agent_retry_policy)
    graph.add_node("gemini_review", gemini_review_node, retry=agent_retry_policy)
    graph.add_node("verification_fan_in", verification_fan_in_node)
    graph.add_node("coverage_check", coverage_check_node)
    graph.add_node("security_scan", security_scan_node)
    graph.add_node("human_escalation", human_escalation_node)
    graph.add_node("completion", completion_node)

    if retry_enabled:
        logger.info("Retry policies enabled for agent nodes")

    # Define edges

    # Start → prerequisites
    graph.add_edge(START, "prerequisites")

    # Prerequisites → product_validation (with conditional for escalation)
    graph.add_conditional_edges(
        "prerequisites",
        prerequisites_router,
        {
            "planning": "product_validation",  # Changed: go to product_validation first
            "human_escalation": "human_escalation",
            "__end__": END,
        },
    )

    # Product validation → planning (with conditional for escalation)
    graph.add_conditional_edges(
        "product_validation",
        product_validation_router,
        {
            "planning": "planning",
            "human_escalation": "human_escalation",
            "__end__": END,
        },
    )

    # Planning → parallel validation fan-out
    graph.add_edge("planning", "cursor_validate")
    graph.add_edge("planning", "gemini_validate")

    # Validation fan-in: both validators merge here
    graph.add_edge("cursor_validate", "validation_fan_in")
    graph.add_edge("gemini_validate", "validation_fan_in")

    # Validation fan-in → approval_gate (with conditional routing)
    graph.add_conditional_edges(
        "validation_fan_in",
        validation_router,
        {
            "implementation": "approval_gate",  # Changed: go to approval_gate first
            "planning": "planning",
            "human_escalation": "human_escalation",
            "__end__": END,
        },
    )

    # Approval gate → pre_implementation (with conditional routing)
    graph.add_conditional_edges(
        "approval_gate",
        approval_gate_router,
        {
            "pre_implementation": "pre_implementation",
            "planning": "planning",
            "human_escalation": "human_escalation",
            "__end__": END,
        },
    )

    # Pre-implementation → task_breakdown (with conditional routing)
    graph.add_conditional_edges(
        "pre_implementation",
        pre_implementation_router,
        {
            "implementation": "task_breakdown",  # Changed: go to task_breakdown
            "human_escalation": "human_escalation",
            "__end__": END,
        },
    )

    # ========== TASK LOOP ==========

    # Task breakdown → select_task
    graph.add_conditional_edges(
        "task_breakdown",
        task_breakdown_router,
        {
            "select_task": "select_task",
            "human_escalation": "human_escalation",
            "__end__": END,
        },
    )

    # Select task → implement_task or build_verification (all done)
    graph.add_conditional_edges(
        "select_task",
        select_task_router,
        {
            "implement_task": "implement_task",
            "build_verification": "build_verification",  # All tasks done
            "human_escalation": "human_escalation",
        },
    )

    # Implement task → verify_task
    graph.add_conditional_edges(
        "implement_task",
        implement_task_router,
        {
            "verify_task": "verify_task",
            "implement_task": "implement_task",  # Retry
            "human_escalation": "human_escalation",
        },
    )

    # Verify task → LOOP BACK to select_task or retry/escalate
    graph.add_conditional_edges(
        "verify_task",
        verify_task_router,
        {
            "select_task": "select_task",  # LOOP BACK - get next task
            "implement_task": "implement_task",  # Retry same task
            "human_escalation": "human_escalation",
        },
    )

    # ========== END TASK LOOP ==========

    # Legacy: Implementation → build_verification (for backward compatibility)
    graph.add_edge("implementation", "build_verification")

    # Build verification → parallel verification fan-out
    # Both review nodes run in parallel after build passes
    # Build failures are handled by having build_verification_node set errors in state
    # and verification_fan_in will check for build errors
    graph.add_edge("build_verification", "cursor_review")
    graph.add_edge("build_verification", "gemini_review")

    # Verification fan-in: both reviewers merge here
    graph.add_edge("cursor_review", "verification_fan_in")
    graph.add_edge("gemini_review", "verification_fan_in")

    # Verification fan-in → coverage_check (with conditional routing)
    graph.add_conditional_edges(
        "verification_fan_in",
        verification_router,
        {
            "completion": "coverage_check",  # Changed: go to coverage_check first
            "implementation": "implementation",
            "human_escalation": "human_escalation",
            "__end__": END,
        },
    )

    # Coverage check → security_scan (with conditional routing)
    graph.add_conditional_edges(
        "coverage_check",
        coverage_check_router,
        {
            "security_scan": "security_scan",
            "implementation": "implementation",
            "human_escalation": "human_escalation",
            "__end__": END,
        },
    )

    # Security scan → completion (with conditional routing)
    graph.add_conditional_edges(
        "security_scan",
        security_scan_router,
        {
            "completion": "completion",
            "implementation": "implementation",
            "human_escalation": "human_escalation",
            "__end__": END,
        },
    )

    # Completion → end
    graph.add_edge("completion", END)

    # Human escalation → conditional routing based on human response
    graph.add_conditional_edges(
        "human_escalation",
        human_escalation_router,
        {
            "planning": "planning",
            "implementation": "implementation",
            "completion": "completion",
            "__end__": END,
        },
    )

    # Compile the graph
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info("LangGraph workflow compiled successfully")
    return compiled


class WorkflowRunner:
    """Runner for executing LangGraph workflows.

    Handles workflow execution with checkpointing, resume,
    and state management.

    Checkpointing Options:
    - MemorySaver (default): Fast but loses state on restart
    - AsyncSqliteSaver: Persistent checkpoints in SQLite (requires aiosqlite)
    - PostgresSaver: Production-grade (requires psycopg)

    Set LANGGRAPH_CHECKPOINTER=sqlite for persistent checkpoints.
    """

    def __init__(
        self,
        project_dir: str | Path,
        checkpoint_dir: Optional[str | Path] = None,
        use_persistent_checkpointer: bool = False,
    ):
        """Initialize the workflow runner.

        Args:
            project_dir: Project directory path
            checkpoint_dir: Optional checkpoint directory (defaults to .workflow/checkpoints)
            use_persistent_checkpointer: Use AsyncSqliteSaver for persistent checkpoints
        """
        self.project_dir = Path(project_dir)
        self.project_name = self.project_dir.name

        # Setup checkpoint directory
        if checkpoint_dir:
            self.checkpoint_dir = Path(checkpoint_dir)
        else:
            self.checkpoint_dir = self.project_dir / ".workflow" / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Check environment for checkpointer preference
        checkpointer_type = os.environ.get("LANGGRAPH_CHECKPOINTER", "memory")
        if checkpointer_type == "sqlite" or use_persistent_checkpointer:
            self.checkpointer = self._create_sqlite_checkpointer()
        else:
            # Default: MemorySaver (fast but non-persistent)
            self.checkpointer = MemorySaver()
            logger.info("Using MemorySaver (state lost on restart). Set LANGGRAPH_CHECKPOINTER=sqlite for persistence.")

        # Create the graph
        self.graph = create_workflow_graph(checkpointer=self.checkpointer)

        # Thread/run configuration
        self.thread_id = f"workflow-{self.project_name}"

    def _create_sqlite_checkpointer(self) -> Any:
        """Create AsyncSqliteSaver for persistent checkpoints.

        Returns:
            AsyncSqliteSaver or MemorySaver as fallback
        """
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            import aiosqlite

            db_path = self.checkpoint_dir / "checkpoints.db"
            logger.info(f"Using AsyncSqliteSaver: {db_path}")

            # AsyncSqliteSaver requires async context management
            # For now, fall back to MemorySaver and note the limitation
            # TODO: Properly integrate async checkpointer initialization
            logger.warning(
                "AsyncSqliteSaver requires async initialization. "
                "Using MemorySaver. See LangGraph docs for async setup."
            )
            return MemorySaver()

        except ImportError as e:
            logger.warning(
                f"Could not import AsyncSqliteSaver: {e}. "
                "Install with: pip install aiosqlite. "
                "Falling back to MemorySaver."
            )
            return MemorySaver()

    async def run(
        self,
        initial_state: Optional[WorkflowState] = None,
        config: Optional[dict] = None,
        progress_callback: Optional["ProgressCallback"] = None,
    ) -> dict[str, Any]:
        """Run the workflow from the beginning.

        Args:
            initial_state: Optional initial state (creates default if not provided)
            config: Optional LangGraph config
            progress_callback: Optional callback for progress updates

        Returns:
            Final workflow state
        """
        if initial_state is None:
            initial_state = create_initial_state(
                project_dir=str(self.project_dir),
                project_name=self.project_name,
            )

        run_config = {
            "configurable": {
                "thread_id": self.thread_id,
            },
        }
        if config:
            run_config.update(config)

        logger.info(f"Starting workflow for project: {self.project_name}")

        if progress_callback:
            # Use streaming to capture node events
            result = await self._run_with_callbacks(
                initial_state, run_config, progress_callback
            )
        else:
            result = await self.graph.ainvoke(initial_state, config=run_config)

        logger.info(f"Workflow completed for project: {self.project_name}")
        return result

    async def _run_with_callbacks(
        self,
        initial_state: WorkflowState,
        run_config: dict,
        callback: "ProgressCallback",
    ) -> dict[str, Any]:
        """Run workflow with progress callbacks using event streaming.

        Args:
            initial_state: Initial workflow state
            run_config: LangGraph run configuration
            callback: Progress callback handler

        Returns:
            Final workflow state
        """
        result = None
        current_node = None

        # Use astream_events for detailed event tracking
        async for event in self.graph.astream_events(
            initial_state,
            config=run_config,
            version="v2",
        ):
            event_type = event.get("event")
            event_name = event.get("name", "")

            if event_type == "on_chain_start":
                # Node starting
                if event_name and event_name != "LangGraph":
                    current_node = event_name
                    state = event.get("data", {}).get("input", {})
                    if isinstance(state, dict):
                        try:
                            callback.on_node_start(event_name, state)
                        except Exception as e:
                            logger.warning(f"Callback error on_node_start: {e}")

            elif event_type == "on_chain_end":
                # Node completed
                if event_name and event_name != "LangGraph":
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        result = output
                        try:
                            callback.on_node_end(event_name, output)
                        except Exception as e:
                            logger.warning(f"Callback error on_node_end: {e}")
                    current_node = None

        return result or initial_state

    async def resume(
        self,
        human_response: Optional[dict] = None,
        config: Optional[dict] = None,
        progress_callback: Optional["ProgressCallback"] = None,
    ) -> dict[str, Any]:
        """Resume the workflow from the last checkpoint.

        Args:
            human_response: Optional response for human escalation
            config: Optional LangGraph config
            progress_callback: Optional callback for progress updates

        Returns:
            Final workflow state
        """
        run_config = {
            "configurable": {
                "thread_id": self.thread_id,
            },
        }
        if config:
            run_config.update(config)

        logger.info(f"Resuming workflow for project: {self.project_name}")

        # Get current state from checkpoint
        state_snapshot = await self.graph.aget_state(run_config)

        if state_snapshot.next:
            # Workflow is paused (likely at human escalation)
            # Use Command(resume=...) to resume from interrupt
            resume_input = human_response if human_response else {"action": "abort"}
            command = Command(resume=resume_input)

            if progress_callback:
                # Use streaming to capture node events
                result = await self._resume_with_callbacks(
                    command, run_config, progress_callback
                )
            else:
                result = await self.graph.ainvoke(command, config=run_config)
        else:
            # No pending work, workflow already complete
            logger.info("Workflow already complete, nothing to resume")
            result = state_snapshot.values

        return result

    async def _resume_with_callbacks(
        self,
        command: Command,
        run_config: dict,
        callback: "ProgressCallback",
    ) -> dict[str, Any]:
        """Resume workflow with progress callbacks using event streaming.

        Args:
            command: LangGraph Command for resuming
            run_config: LangGraph run configuration
            callback: Progress callback handler

        Returns:
            Final workflow state
        """
        result = None

        async for event in self.graph.astream_events(
            command,
            config=run_config,
            version="v2",
        ):
            event_type = event.get("event")
            event_name = event.get("name", "")

            if event_type == "on_chain_start":
                if event_name and event_name != "LangGraph":
                    state = event.get("data", {}).get("input", {})
                    if isinstance(state, dict):
                        try:
                            callback.on_node_start(event_name, state)
                        except Exception as e:
                            logger.warning(f"Callback error on_node_start: {e}")

            elif event_type == "on_chain_end":
                if event_name and event_name != "LangGraph":
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        result = output
                        try:
                            callback.on_node_end(event_name, output)
                        except Exception as e:
                            logger.warning(f"Callback error on_node_end: {e}")

        return result or {}

    async def get_state(self) -> Optional[WorkflowState]:
        """Get the current workflow state.

        Returns:
            Current state or None if no checkpoint exists
        """
        run_config = {
            "configurable": {
                "thread_id": self.thread_id,
            },
        }

        try:
            state_snapshot = await self.graph.aget_state(run_config)
            return state_snapshot.values
        except Exception as e:
            logger.warning(f"Could not get state: {e}")
            return None

    # Maximum checkpoints to return in history
    MAX_HISTORY_CHECKPOINTS = 50

    async def get_history(self, limit: int = None) -> list[dict]:
        """Get the workflow execution history with pagination.

        Args:
            limit: Maximum checkpoints to return (default 50)

        Returns:
            List of state snapshots (limited to prevent memory issues)
        """
        limit = limit or self.MAX_HISTORY_CHECKPOINTS
        run_config = {
            "configurable": {
                "thread_id": self.thread_id,
            },
        }

        history = []
        async for snapshot in self.graph.aget_state_history(run_config):
            history.append({
                "values": snapshot.values,
                "next": snapshot.next,
                "config": snapshot.config,
            })
            # Stop collecting after limit to prevent unbounded memory
            if len(history) >= limit:
                break

        return history

    def get_pending_interrupt(self) -> Optional[dict]:
        """Check if workflow is paused for human input.

        Returns:
            Interrupt details if paused, None otherwise
        """
        import asyncio

        async def _get():
            run_config = {
                "configurable": {
                    "thread_id": self.thread_id,
                },
            }
            state_snapshot = await self.graph.aget_state(run_config)

            if state_snapshot.next:
                # Workflow is paused
                return {
                    "paused_at": list(state_snapshot.next),
                    "state": state_snapshot.values,
                }
            return None

        return asyncio.run(_get())


def get_workflow_runner(
    project_dir: str | Path,
    checkpoint_dir: Optional[str | Path] = None,
    use_persistent_checkpointer: bool = False,
) -> WorkflowRunner:
    """Factory function to create a workflow runner.

    Args:
        project_dir: Project directory path
        checkpoint_dir: Optional checkpoint directory
        use_persistent_checkpointer: Use persistent SQLite checkpoints

    Returns:
        WorkflowRunner instance
    """
    return WorkflowRunner(project_dir, checkpoint_dir, use_persistent_checkpointer)


async def run_workflow(
    project_dir: str | Path,
    initial_state: Optional[WorkflowState] = None,
) -> dict[str, Any]:
    """Convenience function to run a workflow.

    Args:
        project_dir: Project directory path
        initial_state: Optional initial state

    Returns:
        Final workflow state
    """
    runner = WorkflowRunner(project_dir)
    return await runner.run(initial_state)


async def resume_workflow(
    project_dir: str | Path,
    human_response: Optional[dict] = None,
) -> dict[str, Any]:
    """Convenience function to resume a workflow.

    Args:
        project_dir: Project directory path
        human_response: Optional human response

    Returns:
        Final workflow state
    """
    runner = WorkflowRunner(project_dir)
    return await runner.resume(human_response)
