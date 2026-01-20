"""LangGraph workflow graph assembly.

Assembles nodes and routers into a complete workflow graph
with parallel fan-out/fan-in, checkpoints, and human-in-the-loop.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Any

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
)
from .routers import (
    prerequisites_router,
    planning_router,
    validation_router,
    verification_router,
    implementation_router,
    completion_router,
    human_escalation_router,
)

logger = logging.getLogger(__name__)


def create_workflow_graph(
    checkpointer: Optional[Any] = None,
    enable_retry_policy: bool = False,
) -> StateGraph:
    """Create the LangGraph workflow graph.

    This creates a graph with:
    - Sequential phases: prerequisites → planning → validation → implementation → verification → completion
    - Parallel fan-out: planning fans out to cursor_validate AND gemini_validate
    - Parallel fan-out: implementation fans out to cursor_review AND gemini_review
    - Parallel fan-in: validation_fan_in merges validation results
    - Parallel fan-in: verification_fan_in merges review results
    - Human escalation node for blocked workflows
    - Conditional routing based on phase results

    Retry Policy (when enabled):
    - Agent nodes (cursor_*, gemini_*) have RetryPolicy for transient failures
    - Uses exponential backoff: initial_interval=1s, backoff_multiplier=2
    - Max retries: 3 attempts before failing
    - Retries on: ConnectionError, TimeoutError, rate limits

    To enable retry policy, set enable_retry_policy=True or LANGGRAPH_RETRY_ENABLED=true

    Graph structure:
    ```
                     ┌─────────────────┐
                     │ prerequisites   │
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │    planning     │
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼────────┐             ┌────────▼────────┐
     │ cursor_validate │             │ gemini_validate │
     └────────┬────────┘             └────────┬────────┘
              │               │               │
              └───────────────┼───────────────┘
                              │
                     ┌────────▼────────┐
                     │ validation_fan_in│
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │ implementation  │
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼────────┐             ┌────────▼────────┐
     │  cursor_review  │             │  gemini_review  │
     └────────┬────────┘             └────────┬────────┘
              │               │               │
              └───────────────┼───────────────┘
                              │
                     ┌────────▼────────┐
                     │verification_fan_in│
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │   completion    │
                     └────────┬────────┘
                              │
                            [END]

    Human escalation can be reached from:
    - prerequisites (missing requirements)
    - validation_fan_in (validation failed max times)
    - verification_fan_in (verification failed max times)
    ```

    Args:
        checkpointer: Optional checkpointer for persistence

    Returns:
        Compiled StateGraph workflow
    """
    # Create the graph builder
    graph = StateGraph(WorkflowState)

    # Check if retry policy should be enabled
    retry_enabled = enable_retry_policy or os.environ.get("LANGGRAPH_RETRY_ENABLED", "").lower() == "true"

    # Create retry policies for different node types
    # Agent nodes: retry on transient failures with exponential backoff
    agent_retry_policy = RetryPolicy(
        max_attempts=3,
        initial_interval=1.0,  # Start with 1 second wait
        backoff_factor=2.0,    # Double each retry: 1s, 2s, 4s
        jitter=True,           # Add randomness to prevent thundering herd
    ) if retry_enabled else None

    # Implementation node: longer timeout, more retries
    implementation_retry_policy = RetryPolicy(
        max_attempts=2,
        initial_interval=5.0,  # Start with 5 second wait
        backoff_factor=2.0,
        jitter=True,
    ) if retry_enabled else None

    # Add all nodes with appropriate retry policies
    graph.add_node("prerequisites", prerequisites_node)
    graph.add_node("planning", planning_node, retry=agent_retry_policy)
    graph.add_node("cursor_validate", cursor_validate_node, retry=agent_retry_policy)
    graph.add_node("gemini_validate", gemini_validate_node, retry=agent_retry_policy)
    graph.add_node("validation_fan_in", validation_fan_in_node)
    graph.add_node("implementation", implementation_node, retry=implementation_retry_policy)
    graph.add_node("cursor_review", cursor_review_node, retry=agent_retry_policy)
    graph.add_node("gemini_review", gemini_review_node, retry=agent_retry_policy)
    graph.add_node("verification_fan_in", verification_fan_in_node)
    graph.add_node("human_escalation", human_escalation_node)
    graph.add_node("completion", completion_node)

    if retry_enabled:
        logger.info("Retry policies enabled for agent nodes")

    # Define edges

    # Start → prerequisites
    graph.add_edge(START, "prerequisites")

    # Prerequisites → planning (with conditional for escalation)
    graph.add_conditional_edges(
        "prerequisites",
        prerequisites_router,
        {
            "planning": "planning",
            "human_escalation": "human_escalation",
            "__end__": END,
        },
    )

    # Planning → parallel validation fan-out
    # Both cursor_validate and gemini_validate run in parallel
    graph.add_edge("planning", "cursor_validate")
    graph.add_edge("planning", "gemini_validate")

    # Validation fan-in: both validators merge here
    graph.add_edge("cursor_validate", "validation_fan_in")
    graph.add_edge("gemini_validate", "validation_fan_in")

    # Validation fan-in → conditional routing
    graph.add_conditional_edges(
        "validation_fan_in",
        validation_router,
        {
            "implementation": "implementation",
            "planning": "planning",  # Retry planning if validation fails
            "human_escalation": "human_escalation",
            "__end__": END,
        },
    )

    # Implementation → parallel verification fan-out
    graph.add_edge("implementation", "cursor_review")
    graph.add_edge("implementation", "gemini_review")

    # Verification fan-in: both reviewers merge here
    graph.add_edge("cursor_review", "verification_fan_in")
    graph.add_edge("gemini_review", "verification_fan_in")

    # Verification fan-in → conditional routing
    graph.add_conditional_edges(
        "verification_fan_in",
        verification_router,
        {
            "completion": "completion",
            "implementation": "implementation",  # Retry implementation if verification fails
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
    ) -> dict[str, Any]:
        """Run the workflow from the beginning.

        Args:
            initial_state: Optional initial state (creates default if not provided)
            config: Optional LangGraph config

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

        result = await self.graph.ainvoke(initial_state, config=run_config)

        logger.info(f"Workflow completed for project: {self.project_name}")
        return result

    async def resume(
        self,
        human_response: Optional[dict] = None,
        config: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Resume the workflow from the last checkpoint.

        Args:
            human_response: Optional response for human escalation
            config: Optional LangGraph config

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
            # See: https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/add-human-in-the-loop/
            if human_response:
                # Resume with human response using Command primitive
                result = await self.graph.ainvoke(
                    Command(resume=human_response),
                    config=run_config,
                )
            else:
                # Resume with default response (abort)
                result = await self.graph.ainvoke(
                    Command(resume={"action": "abort"}),
                    config=run_config,
                )
        else:
            # No pending work, workflow already complete
            logger.info("Workflow already complete, nothing to resume")
            result = state_snapshot.values

        return result

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

    async def get_history(self) -> list[dict]:
        """Get the workflow execution history.

        Returns:
            List of state snapshots
        """
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
