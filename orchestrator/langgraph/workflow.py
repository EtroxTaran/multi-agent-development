"""LangGraph workflow graph assembly.

Assembles nodes and routers into a complete workflow graph
with parallel fan-out/fan-in, checkpoints, and human-in-the-loop.
"""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..ui.callbacks import ProgressCallback

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy

from .nodes import (  # New risk mitigation nodes; Quality infrastructure nodes; Discussion and Research nodes (GSD pattern); Handoff node (GSD pattern); Error dispatch node
    approval_gate_node,
    build_verification_node,
    completion_node,
    coverage_check_node,
    cursor_review_node,
    cursor_validate_node,
    dependency_check_node,
    discuss_phase_node,
    error_dispatch_node,
    fixer_apply_node,
    fixer_research_node,
    fixer_validate_node,
    fixer_verify_node,
    gemini_review_node,
    gemini_validate_node,
    generate_handoff_node,
    human_escalation_node,
    implementation_node,
    planning_node,
    pre_implementation_node,
    prerequisites_node,
    product_validation_node,
    quality_gate_node,
    research_phase_node,
    review_gate_node,
    security_scan_node,
    validation_fan_in_node,
    verification_fan_in_node,
)
from .routers import (  # New risk mitigation routers; Quality infrastructure routers; Discussion and Research routers (GSD pattern); Error dispatch router
    approval_gate_router,
    coverage_check_router,
    dependency_check_router,
    discuss_router,
    error_dispatch_router,
    human_escalation_router,
    pre_implementation_router,
    prerequisites_router,
    product_validation_router,
    quality_gate_router,
    research_router,
    security_scan_router,
    validation_router,
    verification_router,
)
from .state import WorkflowState, create_initial_state
from .subgraphs import create_fixer_subgraph, create_task_subgraph
from .surrealdb_saver import SurrealDBSaver

logger = logging.getLogger(__name__)


def subgraph_router(state: WorkflowState) -> str:
    """Route based on subgraph exit state.

    Args:
        state: Workflow state

    Returns:
        Next node name
    """
    decision = state.get("next_decision")
    if decision == "escalate":
        return "human_escalation"
    return "continue"


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
    - Discussion and Research phases for informed planning (GSD pattern)
    - Modular subgraphs for Task Loop and Fixer logic

    Retry Policy (when enabled):
    - Agent nodes (cursor_*, gemini_*) have RetryPolicy for transient failures
    - Uses exponential backoff: initial_interval=1s, backoff_multiplier=2
    - Max retries: 3 attempts before failing

    Args:
        checkpointer: Optional checkpointer for persistence
        enable_retry_policy: Enable retry policies for agent nodes

    Returns:
        Compiled StateGraph workflow
    """
    # Create the graph builder
    graph = StateGraph(WorkflowState)

    # Check if retry policy should be enabled
    retry_enabled = (
        enable_retry_policy or os.environ.get("LANGGRAPH_RETRY_ENABLED", "").lower() == "true"
    )

    # Create retry policies for different node types
    agent_retry_policy = (
        RetryPolicy(
            max_attempts=3,
            initial_interval=1.0,
            backoff_factor=2.0,
            jitter=True,
        )
        if retry_enabled
        else None
    )

    implementation_retry_policy = (
        RetryPolicy(
            max_attempts=2,
            initial_interval=5.0,
            backoff_factor=2.0,
            jitter=True,
        )
        if retry_enabled
        else None
    )

    # Add all nodes with appropriate retry policies
    # Core workflow nodes
    graph.add_node("prerequisites", prerequisites_node)

    # Discussion and Research nodes (GSD pattern)
    graph.add_node("discuss", discuss_phase_node)
    graph.add_node("research", research_phase_node)

    graph.add_node("product_validation", product_validation_node)
    graph.add_node("planning", planning_node, retry=agent_retry_policy)
    graph.add_node("cursor_validate", cursor_validate_node, retry=agent_retry_policy)
    graph.add_node("gemini_validate", gemini_validate_node, retry=agent_retry_policy)
    graph.add_node("validation_fan_in", validation_fan_in_node)
    graph.add_node("approval_gate", approval_gate_node)
    graph.add_node("pre_implementation", pre_implementation_node)

    # Subgraphs
    graph.add_node("task_subgraph", create_task_subgraph(retry_enabled))
    graph.add_node("fixer_subgraph", create_fixer_subgraph())

    # Legacy implementation node (kept for compatibility)
    graph.add_node("implementation", implementation_node, retry=implementation_retry_policy)

    # Post-implementation nodes
    graph.add_node("build_verification", build_verification_node)
    graph.add_node("quality_gate", quality_gate_node)  # A13: TypeScript/ESLint checks
    graph.add_node("review_gate", review_gate_node)
    graph.add_node("cursor_review", cursor_review_node, retry=agent_retry_policy)
    graph.add_node("gemini_review", gemini_review_node, retry=agent_retry_policy)
    graph.add_node("verification_fan_in", verification_fan_in_node)
    graph.add_node("coverage_check", coverage_check_node)
    graph.add_node("security_scan", security_scan_node)
    graph.add_node("dependency_check", dependency_check_node)  # A14: Dependency analysis
    graph.add_node("human_escalation", human_escalation_node)
    graph.add_node("completion", completion_node)

    # Error dispatch node (routes to fixer or human escalation)
    graph.add_node("error_dispatch", error_dispatch_node)

    graph.add_node("fixer_validate", fixer_validate_node)
    graph.add_node("fixer_apply", fixer_apply_node)
    graph.add_node("fixer_verify", fixer_verify_node)
    graph.add_node("fixer_research", fixer_research_node)

    # Handoff node (GSD pattern) - generates session brief before END
    graph.add_node("generate_handoff", generate_handoff_node)

    if retry_enabled:
        logger.info("Retry policies enabled for agent nodes")

    # Define edges

    # Start → prerequisites
    graph.add_edge(START, "prerequisites")

    # Prerequisites → discuss (with conditional for escalation)
    graph.add_conditional_edges(
        "prerequisites",
        prerequisites_router,
        {
            "planning": "discuss",  # Changed: go to discuss phase first (GSD pattern)
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "__end__": END,
        },
    )

    # Discuss → research (mandatory discussion phase, GSD pattern)
    graph.add_conditional_edges(
        "discuss",
        discuss_router,
        {
            "discuss_complete": "research",
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "discuss_retry": "discuss",
        },
    )

    # Research → product_validation (2 parallel agents run internally)
    graph.add_conditional_edges(
        "research",
        research_router,
        {
            "research_complete": "product_validation",
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "research_retry": "research",
        },
    )

    # Product validation → planning (with conditional for escalation)
    graph.add_conditional_edges(
        "product_validation",
        product_validation_router,
        {
            "planning": "planning",
            "human_escalation": "error_dispatch",  # Route through error_dispatch
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
            "human_escalation": "error_dispatch",  # Route through error_dispatch
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
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "__end__": END,
        },
    )

    # Pre-implementation → task_subgraph (with conditional routing)
    # Replaces routing to task_breakdown
    graph.add_conditional_edges(
        "pre_implementation",
        pre_implementation_router,
        {
            "implementation": "task_subgraph",  # Use subgraph
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "__end__": END,
        },
    )

    # ========== TASK SUBGRAPH ROUTING ==========

    graph.add_conditional_edges(
        "task_subgraph",
        subgraph_router,
        {
            "continue": "build_verification",  # Success path
            "human_escalation": "error_dispatch",
        },
    )

    # Legacy: Implementation → build_verification (for backward compatibility)
    graph.add_edge("implementation", "build_verification")

    # Build verification → quality_gate → review gate → parallel verification fan-out
    # Quality gate runs TypeScript/ESLint checks before human code review
    graph.add_edge("build_verification", "quality_gate")

    # Quality gate → review gate (with conditional routing for failures)
    graph.add_conditional_edges(
        "quality_gate",
        quality_gate_router,
        {
            "cursor_review": "review_gate",  # Passed, proceed to review
            "implementation": "implementation",  # Failed, retry implementation
            "human_escalation": "error_dispatch",
            "__end__": END,
        },
    )

    # Both review nodes run in parallel after quality gate passes
    graph.add_edge("review_gate", "cursor_review")
    graph.add_edge("review_gate", "gemini_review")

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
            "human_escalation": "error_dispatch",  # Route through error_dispatch
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
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "__end__": END,
        },
    )

    # Security scan → dependency_check (with conditional routing)
    graph.add_conditional_edges(
        "security_scan",
        security_scan_router,
        {
            "completion": "dependency_check",  # Changed: go to dependency_check first
            "implementation": "implementation",
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "__end__": END,
        },
    )

    # Dependency check → completion (with conditional routing)
    graph.add_conditional_edges(
        "dependency_check",
        dependency_check_router,
        {
            "completion": "completion",
            "implementation": "implementation",
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "__end__": END,
        },
    )

    # Completion → generate_handoff → END (GSD pattern)
    graph.add_edge("completion", "generate_handoff")
    graph.add_edge("generate_handoff", END)

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

    # ========== ERROR DISPATCH ==========
    # Error dispatch intercepts errors and routes to fixer or human escalation
    graph.add_conditional_edges(
        "error_dispatch",
        error_dispatch_router,
        {
            "fixer_triage": "fixer_subgraph",  # Use subgraph
            "human_escalation": "human_escalation",
        },
    )

    # ========== FIXER SUBGRAPH ROUTING ==========

    graph.add_conditional_edges(
        "fixer_subgraph",
        subgraph_router,
        {
            "continue": "task_subgraph",  # Default retry logic
            "human_escalation": "human_escalation",
        },
    )

    # Compile the graph
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info("LangGraph workflow compiled successfully")
    return compiled


class WorkflowRunner:
    """Runner for executing LangGraph workflows.

    Handles workflow execution with checkpointing, resume,
    and state management. Use as an async context manager:

        async with WorkflowRunner(project_dir) as runner:
            await runner.run()

    Checkpointing Options:
    - MemorySaver: Fast but loses state on restart (LANGGRAPH_CHECKPOINTER=memory)
    - SurrealDBSaver: Persistent checkpoints in SurrealDB (default)

    Set LANGGRAPH_CHECKPOINTER=memory for in-memory (testing) mode.
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
            checkpoint_dir: Optional checkpoint directory (deprecated)
            use_persistent_checkpointer: Use persistence (defaults to True unless configured otherwise)
        """
        self.project_dir = Path(project_dir)
        self.project_name = self.project_dir.name

        # Check environment for checkpointer preference
        # Default to surrealdb for persistence
        self.checkpointer_type = os.environ.get("LANGGRAPH_CHECKPOINTER", "surrealdb")

        # Graph will be created in __aenter__
        self.graph = None
        self.checkpointer = None

        # Thread/run configuration
        self.thread_id = f"workflow-{self.project_name}"

    async def __aenter__(self) -> "WorkflowRunner":
        """Enter async context, creating checkpointer and graph."""
        if self.checkpointer_type == "memory":
            self.checkpointer = MemorySaver()
            logger.warning(
                "Using MemorySaver - state will be lost on restart. "
                "This should only be used for testing. "
                "Set LANGGRAPH_CHECKPOINTER=surrealdb for persistence."
            )
        else:
            # SurrealDB persistence
            self.checkpointer = SurrealDBSaver(self.project_name)
            logger.info(f"Using SurrealDBSaver for project: {self.project_name}")

        self.graph = create_workflow_graph(checkpointer=self.checkpointer)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        self.checkpointer = None
        self.graph = None
        return False

    async def run(
        self,
        initial_state: Optional[WorkflowState] = None,
        config: Optional[dict] = None,
        progress_callback: Optional["ProgressCallback"] = None,
    ) -> dict[str, Any]:
        """Run the workflow from the beginning.

        Must be called within async context manager:
            async with WorkflowRunner(project_dir) as runner:
                await runner.run()

        Args:
            initial_state: Optional initial state (creates default if not provided)
            config: Optional LangGraph config (may contain execution_mode: "hitl" or "afk")
            progress_callback: Optional callback for progress updates

        Returns:
            Final workflow state
        """
        if self.graph is None:
            raise RuntimeError(
                "WorkflowRunner must be used as async context manager: "
                "async with WorkflowRunner(project_dir) as runner: await runner.run()"
            )

        # Extract execution_mode from config if provided
        execution_mode = config.get("execution_mode", "hitl") if config else "hitl"

        if initial_state is None:
            initial_state = create_initial_state(
                project_dir=str(self.project_dir),
                project_name=self.project_name,
                execution_mode=execution_mode,
            )
        elif config and "execution_mode" in config:
            # Update existing state with new execution_mode
            initial_state["execution_mode"] = execution_mode

        run_config = {
            "configurable": {
                "thread_id": self.thread_id,
            },
        }
        if progress_callback:

            def path_emitter(router, decision, state):
                if hasattr(progress_callback, "on_path_decision"):
                    progress_callback.on_path_decision(router, decision, state)

            run_config["configurable"]["path_emitter"] = path_emitter

        if config:
            run_config.update(config)

        # Bootstrap prompt versions if needed (first run)
        await self._ensure_prompt_versions()

        logger.info(f"Starting workflow for project: {self.project_name}")

        if progress_callback:
            result = await self._run_with_callbacks(
                self.graph, initial_state, run_config, progress_callback
            )
        else:
            result = await self.graph.ainvoke(initial_state, config=run_config)

        logger.info(f"Workflow completed for project: {self.project_name}")
        return result

    async def _ensure_prompt_versions(self) -> None:
        """Ensure initial prompt versions exist in database.

        Bootstraps prompt versions from template files if they don't exist.
        This is a non-blocking operation - if it fails, the workflow continues.
        """
        try:
            # Import bootstrap function
            import sys
            from pathlib import Path

            scripts_dir = Path(__file__).parent.parent.parent / "scripts"
            if str(scripts_dir) not in sys.path:
                sys.path.insert(0, str(scripts_dir))

            from bootstrap_prompts import bootstrap_prompts, verify_bootstrap

            # Check if bootstrap is needed
            needs_bootstrap = not await verify_bootstrap(self.project_name)

            if needs_bootstrap:
                logger.info("Bootstrapping initial prompt versions...")
                results = await bootstrap_prompts(self.project_name, force=False)
                if results["created"] > 0:
                    logger.info(f"Bootstrapped {results['created']} prompt versions")
                if results["errors"] > 0:
                    logger.warning(f"Bootstrap had {results['errors']} errors")
            else:
                logger.debug("Prompt versions already exist, skipping bootstrap")

        except ImportError as e:
            logger.debug(f"Bootstrap script not available: {e}")
        except Exception as e:
            # Non-fatal error - workflow can continue without prompt optimization
            logger.warning(f"Prompt bootstrap failed (non-fatal): {e}")

    async def _run_with_callbacks(
        self,
        graph: Any,
        initial_state: WorkflowState,
        run_config: dict,
        callback: "ProgressCallback",
    ) -> dict[str, Any]:
        """Run workflow with progress callbacks using event streaming.

        Args:
            graph: Compiled workflow graph
            initial_state: Initial workflow state
            run_config: LangGraph run configuration
            callback: Progress callback handler

        Returns:
            Final workflow state
        """
        result = None
        current_node = None

        # Use astream_events for detailed event tracking
        async for event in graph.astream_events(
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

        Must be called within async context manager.

        Args:
            human_response: Optional response for human escalation
            config: Optional LangGraph config (may contain execution_mode: "hitl" or "afk")
            progress_callback: Optional callback for progress updates

        Returns:
            Final workflow state
        """
        if self.graph is None:
            raise RuntimeError(
                "WorkflowRunner must be used as async context manager: "
                "async with WorkflowRunner(project_dir) as runner: await runner.resume()"
            )

        run_config = {
            "configurable": {
                "thread_id": self.thread_id,
            },
        }
        if progress_callback:

            def path_emitter(router, decision, state):
                if hasattr(progress_callback, "on_path_decision"):
                    progress_callback.on_path_decision(router, decision, state)

            run_config["configurable"]["path_emitter"] = path_emitter

        if config:
            run_config.update(config)

        # If execution_mode is specified in config, include it in human_response
        # so it can be used to update the state when resuming
        execution_mode = config.get("execution_mode") if config else None

        logger.info(f"Resuming workflow for project: {self.project_name}")
        if execution_mode:
            logger.info(f"Execution mode: {execution_mode}")

        # Get current state from checkpoint
        state_snapshot = await self.graph.aget_state(run_config)

        # Update execution_mode in the state if a new one was provided
        if execution_mode and state_snapshot.values:
            current_values = dict(state_snapshot.values)
            if current_values.get("execution_mode") != execution_mode:
                logger.info(
                    f"Updating execution mode from {current_values.get('execution_mode')} to {execution_mode}"
                )
                await self.graph.aupdate_state(
                    run_config,
                    {"execution_mode": execution_mode},
                )
                state_snapshot = await self.graph.aget_state(run_config)

        if state_snapshot.next:
            # Workflow is paused (likely at human escalation)
            # Use Command(resume=...) to resume from interrupt
            resume_input = human_response if human_response else {"action": "abort"}
            command = Command(resume=resume_input)

            if progress_callback:
                # Use streaming to capture node events
                result = await self._resume_with_callbacks(command, run_config, progress_callback)
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

        Must be called within async context manager.

        Returns:
            Current state or None if no checkpoint exists
        """
        if self.graph is None:
            raise RuntimeError("WorkflowRunner must be used as async context manager")

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
            history.append(
                {
                    "values": snapshot.values,
                    "next": snapshot.next,
                    "config": snapshot.config,
                }
            )
            # Stop collecting after limit to prevent unbounded memory
            if len(history) >= limit:
                break

        return history

    async def get_pending_interrupt_async(self) -> Optional[dict]:
        """Check if workflow is paused for human input (async version).

        Must be called within async context manager.

        Returns:
            Interrupt details if paused, None otherwise
        """
        if self.graph is None:
            raise RuntimeError("WorkflowRunner must be used as async context manager")

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

    def get_pending_interrupt(self) -> Optional[dict]:
        """Check if workflow is paused for human input (sync wrapper).

        Note: This creates a temporary async context and should only
        be used outside of async code. Use get_pending_interrupt_async
        inside async code.

        Returns:
            Interrupt details if paused, None otherwise
        """
        import asyncio

        async def _get():
            async with WorkflowRunner(self.project_dir) as runner:
                return await runner.get_pending_interrupt_async()

        return asyncio.run(_get())


def get_workflow_runner(
    project_dir: str | Path,
    checkpoint_dir: Optional[str | Path] = None,
    use_persistent_checkpointer: bool = False,
) -> WorkflowRunner:
    """Factory function to create a workflow runner.

    Args:
        project_dir: Project directory path
        checkpoint_dir: Optional checkpoint directory (deprecated)
        use_persistent_checkpointer: Use persistent SurrealDB checkpoints

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
    async with WorkflowRunner(project_dir) as runner:
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
    async with WorkflowRunner(project_dir) as runner:
        return await runner.resume(human_response)
