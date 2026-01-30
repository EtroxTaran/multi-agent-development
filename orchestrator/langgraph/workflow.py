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
from langgraph.types import Command, RetryPolicy, Send

from ..config.thresholds import ProjectConfig, RetryConfig
from .nodes import (  # New risk mitigation nodes; Quality infrastructure nodes; Discussion and Research nodes (GSD pattern); Handoff node (GSD pattern); Error dispatch node; Pause check node; Test pass gate node
    approval_gate_node,
    build_verification_node,
    completion_node,
    coverage_check_node,
    cursor_review_node,
    cursor_validate_node,
    dependency_check_node,
    discuss_phase_node,
    documentation_discovery_node,
    error_dispatch_node,
    fixer_apply_node,
    fixer_research_node,
    fixer_validate_node,
    fixer_verify_node,
    gemini_review_node,
    gemini_validate_node,
    generate_handoff_node,
    guardrails_agent_node,
    human_escalation_node,
    implementation_node,
    pause_check_node,
    planning_node,
    pre_implementation_node,
    prerequisites_node,
    quality_gate_node,
    research_phase_node,
    review_gate_node,
    security_scan_node,
    security_specialist_node,
    test_pass_gate_node,
    validation_fan_in_node,
    verification_fan_in_node,
)
from .routers import (  # New risk mitigation routers; Quality infrastructure routers; Discussion and Research routers (GSD pattern); Error dispatch router; Test pass gate router
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
    test_pass_gate_router,
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
    # Check for pause request first
    if state.get("pause_requested", False):
        return "pause_check"

    decision = state.get("next_decision")
    if decision == "escalate":
        return "human_escalation"

    # After fixer success, resume at task selection (not full task breakdown)
    if decision == "continue" and state.get("fixer_resolved"):
        return "select_task"

    return "continue"


def pause_check_router(state: WorkflowState) -> str:
    """Route after pause check completes.

    Args:
        state: Workflow state

    Returns:
        Next node to resume at
    """
    # If abort was chosen during pause
    if state.get("next_decision") == "abort":
        return "error_dispatch"

    # Otherwise continue to the node we paused before
    paused_at = state.get("paused_at_node")
    paused_at_str = paused_at if isinstance(paused_at, str) else "build_verification"

    # Map pause points to their continuation nodes
    continuation_map = {
        "after_validation": "approval_gate",
        "after_implementation": "build_verification",
        "after_verification": "coverage_check",
    }

    return continuation_map.get(paused_at_str, "build_verification")


def planning_send_router(state: WorkflowState) -> list[Send]:
    """Conditional parallel dispatch after planning phase.

    Uses LangGraph's Send() API to conditionally fan-out to validation nodes
    only if planning succeeded. This prevents validation from running when
    planning failed.

    Also checks end_phase: if end_phase=1, routes to completion instead of
    validation (skip phases 2+).

    Args:
        state: Current workflow state

    Returns:
        List of Send objects:
        - [Send(completion)] if end_phase=1
        - [Send(cursor_validate), Send(gemini_validate)] if plan exists
        - [Send(error_dispatch)] if planning failed
    """
    # Check end_phase: if end_phase=1, skip validation and route to completion
    end_phase = state.get("end_phase", 5)
    if end_phase <= 1:
        plan = state.get("plan")
        if plan and plan.get("plan_name"):
            logger.info(f"end_phase={end_phase} reached after planning - routing to completion")
            return [Send("completion", state)]

    # Check if plan exists and is valid
    plan = state.get("plan")
    has_valid_plan = plan and plan.get("plan_name")

    # Check phase status for explicit failure
    phase_status = state.get("phase_status", {})
    phase_1 = phase_status.get("1")

    # Determine if planning failed
    planning_failed = False
    if phase_1 and hasattr(phase_1, "status"):
        from .state import PhaseStatus

        if phase_1.status == PhaseStatus.FAILED:
            planning_failed = True

    # Check next_decision for explicit escalation/abort
    decision = state.get("next_decision")
    if decision in ("escalate", "abort"):
        planning_failed = True

    if has_valid_plan and not planning_failed:
        # Success: fan-out to both validators in parallel
        logger.info("Planning succeeded - dispatching to parallel validation")
        return [
            Send("cursor_validate", state),
            Send("gemini_validate", state),
        ]
    else:
        # Failure: route to error dispatch
        logger.warning(
            f"Planning failed - routing to error dispatch "
            f"(has_plan={has_valid_plan}, failed={planning_failed}, decision={decision})"
        )
        return [Send("error_dispatch", state)]


def create_workflow_graph(
    checkpointer: Optional[Any] = None,
    enable_retry_policy: bool = False,
    retry_config: Optional[RetryConfig] = None,
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
    - Uses exponential backoff with configurable values from RetryConfig
    - Max retries configurable via retry_config.agent_max_attempts

    Args:
        checkpointer: Optional checkpointer for persistence
        enable_retry_policy: Enable retry policies for agent nodes
        retry_config: Optional RetryConfig with custom retry settings

    Returns:
        Compiled StateGraph workflow
    """
    # Create the graph builder
    graph = StateGraph(WorkflowState)

    # Use provided retry config or defaults
    cfg = retry_config or RetryConfig()

    # Check if retry policy should be enabled
    retry_enabled = cfg.enabled and (
        enable_retry_policy or os.environ.get("LANGGRAPH_RETRY_ENABLED", "").lower() == "true"
    )

    # Create retry policies for different node types using config values
    agent_retry_policy = (
        RetryPolicy(
            max_attempts=cfg.agent_max_attempts,
            initial_interval=cfg.agent_initial_interval,
            backoff_factor=cfg.agent_backoff_factor,
            jitter=cfg.agent_jitter,
        )
        if retry_enabled
        else None
    )

    implementation_retry_policy = (
        RetryPolicy(
            max_attempts=cfg.implementation_max_attempts,
            initial_interval=cfg.implementation_initial_interval,
            backoff_factor=cfg.implementation_backoff_factor,
            jitter=cfg.implementation_jitter,
        )
        if retry_enabled
        else None
    )

    # Add all nodes with appropriate retry policies
    # Core workflow nodes
    graph.add_node("prerequisites", prerequisites_node)

    # Guardrails agent node (applies collection guardrails to project)
    graph.add_node("guardrails_agent", guardrails_agent_node)

    # Discussion and Research nodes (GSD pattern)
    graph.add_node("discuss", discuss_phase_node)
    graph.add_node("research", research_phase_node)

    graph.add_node(
        "product_validation", documentation_discovery_node
    )  # Renamed: uses documentation_discovery
    graph.add_node("planning", planning_node, retry_policy=agent_retry_policy)
    graph.add_node("cursor_validate", cursor_validate_node, retry_policy=agent_retry_policy)
    graph.add_node("gemini_validate", gemini_validate_node, retry_policy=agent_retry_policy)
    graph.add_node("validation_fan_in", validation_fan_in_node)
    graph.add_node(
        "security_specialist", security_specialist_node
    )  # Reviews HIGH severity concerns
    graph.add_node("approval_gate", approval_gate_node)
    graph.add_node("pre_implementation", pre_implementation_node)

    # Subgraphs
    graph.add_node("task_subgraph", create_task_subgraph(retry_enabled))
    graph.add_node("fixer_subgraph", create_fixer_subgraph())

    # Legacy implementation node (kept for compatibility)
    graph.add_node("implementation", implementation_node, retry_policy=implementation_retry_policy)

    # Post-implementation nodes
    graph.add_node("build_verification", build_verification_node)
    graph.add_node("quality_gate", quality_gate_node)  # A13: TypeScript/ESLint checks
    graph.add_node("review_gate", review_gate_node)
    graph.add_node("cursor_review", cursor_review_node, retry_policy=agent_retry_policy)
    graph.add_node("gemini_review", gemini_review_node, retry_policy=agent_retry_policy)
    graph.add_node("verification_fan_in", verification_fan_in_node)
    graph.add_node("coverage_check", coverage_check_node)
    graph.add_node("security_scan", security_scan_node)
    graph.add_node("dependency_check", dependency_check_node)  # A14: Dependency analysis
    graph.add_node("test_pass_gate", test_pass_gate_node)  # Final test verification gate
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

    # Pause check node (dashboard integration) - checks for pause requests at key points
    graph.add_node("pause_check", pause_check_node)

    if retry_enabled:
        logger.info("Retry policies enabled for agent nodes")

    # Define edges

    # Start → prerequisites
    graph.add_edge(START, "prerequisites")

    # Prerequisites → guardrails_agent → discuss (with conditional for escalation)
    graph.add_conditional_edges(
        "prerequisites",
        prerequisites_router,
        {
            "planning": "guardrails_agent",  # Changed: go to guardrails_agent first
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "__end__": END,
        },
    )

    # Guardrails agent → discuss (unconditional - guardrails are non-blocking)
    graph.add_edge("guardrails_agent", "discuss")

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

    # Planning → conditional parallel validation fan-out
    # Uses Send() to dispatch to both validators only if planning succeeded.
    # If planning failed, routes to error_dispatch instead.
    graph.add_conditional_edges("planning", planning_send_router)

    # Validation fan-in: both validators merge here
    graph.add_edge("cursor_validate", "validation_fan_in")
    graph.add_edge("gemini_validate", "validation_fan_in")

    # Validation fan-in → security_specialist (reviews HIGH severity concerns)
    graph.add_edge("validation_fan_in", "security_specialist")

    # Security specialist → approval_gate (with conditional routing)
    # Security specialist reclassifies spec gaps as MEDIUM, keeps real vulnerabilities as HIGH
    graph.add_conditional_edges(
        "security_specialist",
        validation_router,
        {
            "implementation": "approval_gate",  # Changed: go to approval_gate first
            "planning": "planning",
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "__end__": END,
        },
    )

    # Approval gate → pre_implementation (with conditional routing)
    # end_phase check: routes to completion if end_phase <= 2
    graph.add_conditional_edges(
        "approval_gate",
        approval_gate_router,
        {
            "pre_implementation": "pre_implementation",
            "completion": "completion",  # end_phase early stop
            "planning": "planning",
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "__end__": END,
        },
    )

    # Pre-implementation → task_subgraph (with conditional routing)
    # end_phase check: routes to completion if end_phase <= 2
    graph.add_conditional_edges(
        "pre_implementation",
        pre_implementation_router,
        {
            "implementation": "task_subgraph",  # Use subgraph
            "completion": "completion",  # end_phase early stop
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
            "pause_check": "pause_check",  # Dashboard requested pause
        },
    )

    # Pause check → conditional routing back to workflow based on resume state
    graph.add_conditional_edges(
        "pause_check",
        pause_check_router,
        {
            "approval_gate": "approval_gate",
            "build_verification": "build_verification",
            "coverage_check": "coverage_check",
            "error_dispatch": "error_dispatch",  # User chose abort
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

    # Dependency check → test_pass_gate (with conditional routing)
    graph.add_conditional_edges(
        "dependency_check",
        dependency_check_router,
        {
            "completion": "test_pass_gate",  # Changed: go to test_pass_gate first
            "implementation": "implementation",
            "human_escalation": "error_dispatch",  # Route through error_dispatch
            "__end__": END,
        },
    )

    # Test pass gate → completion (final verification before marking complete)
    graph.add_conditional_edges(
        "test_pass_gate",
        test_pass_gate_router,
        {
            "completion": "completion",
            "task_subgraph": "task_subgraph",  # Retry implementation if tests fail
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
            "select_task": "task_subgraph",  # Fixer success: resume at task selection
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
        self.graph: Any = None
        self.checkpointer: Any = None
        self.project_config: Optional[ProjectConfig] = None

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

        # Load project config for retry settings and task loop limits
        self.project_config = self._load_project_config()
        retry_config = self.project_config.retry if self.project_config else None

        self.graph = create_workflow_graph(
            checkpointer=self.checkpointer,
            retry_config=retry_config,
        )
        return self

    def _load_project_config(self) -> Optional[ProjectConfig]:
        """Load project configuration from .project-config.json.

        Returns:
            ProjectConfig if file exists, None otherwise
        """
        config_path = self.project_dir / ".project-config.json"
        if not config_path.exists():
            return None

        try:
            import json

            with open(config_path) as f:
                data = json.load(f)
            return ProjectConfig.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load project config: {e}")
            return None

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

        # Extract execution_mode and end_phase from config if provided
        execution_mode = config.get("execution_mode", "hitl") if config else "hitl"
        end_phase = config.get("end_phase", 5) if config else 5

        if initial_state is None:
            initial_state = create_initial_state(
                project_dir=str(self.project_dir),
                project_name=self.project_name,
                execution_mode=execution_mode,
                end_phase=end_phase,
            )
            # Apply config overrides for task loop limits
            if self.project_config and self.project_config.retry:
                initial_state[
                    "max_task_loop_iterations"
                ] = self.project_config.retry.max_task_loop_iterations
        elif config and "execution_mode" in config:
            # Update existing state with new execution_mode
            initial_state["execution_mode"] = execution_mode

        configurable: dict[str, Any] = {
            "thread_id": self.thread_id,
        }
        if progress_callback:
            # Store callback in configurable for task nodes to emit events
            configurable["progress_callback"] = progress_callback

            def path_emitter(router: Any, decision: Any, state: Any) -> None:
                if hasattr(progress_callback, "on_path_decision"):
                    progress_callback.on_path_decision(router, decision, state)

            configurable["path_emitter"] = path_emitter

        run_config: dict[str, Any] = {
            "configurable": configurable,
            # Increase recursion limit from default 25 to handle complex workflows
            "recursion_limit": 100,
        }

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
        initial_state: WorkflowState | None,
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
        previous_phase: int | None = initial_state.get("current_phase") if initial_state else None

        # Emit phase_start for the initial phase
        if previous_phase is not None and hasattr(callback, "on_phase_start"):
            try:
                callback.on_phase_start(phase=previous_phase)
            except Exception as e:
                logger.warning(f"Callback error on_phase_start (initial): {e}")

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

                        # Detect phase changes and emit phase events
                        current_phase = output.get("current_phase")
                        if current_phase is not None and current_phase != previous_phase:
                            try:
                                # Check if phase ended successfully (no errors for that phase)
                                phase_status = output.get("phase_status", {})
                                prev_phase_status = (
                                    phase_status.get(str(previous_phase), {})
                                    if previous_phase
                                    else {}
                                )
                                # Handle both dict and PhaseState dataclass
                                if hasattr(prev_phase_status, "to_dict"):
                                    prev_phase_status = prev_phase_status.to_dict()
                                elif hasattr(prev_phase_status, "status"):
                                    # PhaseState dataclass - access status attribute directly
                                    status_val = getattr(prev_phase_status, "status", None)
                                    # Status might be a PhaseStatus enum
                                    if status_val is not None and hasattr(status_val, "value"):
                                        status_val = status_val.value
                                    prev_phase_status = {"status": status_val}
                                prev_success = prev_phase_status.get("status") != "failed"

                                # Emit phase_end for the previous phase
                                if previous_phase is not None and hasattr(callback, "on_phase_end"):
                                    callback.on_phase_end(
                                        phase=previous_phase,
                                        success=prev_success,
                                        node_name=event_name,
                                    )

                                # Emit phase_change for the transition
                                if hasattr(callback, "on_phase_change"):
                                    callback.on_phase_change(
                                        from_phase=previous_phase or 0,
                                        to_phase=current_phase,
                                        status="in_progress",
                                    )

                                # Emit phase_start for the new phase
                                if hasattr(callback, "on_phase_start"):
                                    callback.on_phase_start(
                                        phase=current_phase,
                                        node_name=event_name,
                                    )

                                previous_phase = current_phase
                            except Exception as e:
                                logger.warning(f"Callback error on phase change: {e}")

        # Retrieve the full accumulated state from the graph checkpoint,
        # not just the last node's partial output.
        try:
            final_snapshot = await graph.aget_state(run_config)
            if final_snapshot and final_snapshot.values:
                return dict(final_snapshot.values)
        except Exception as e:
            logger.warning(f"Could not retrieve final state from checkpoint: {e}")

        return dict(result or initial_state or {})

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

        resume_configurable: dict[str, Any] = {
            "thread_id": self.thread_id,
        }
        if progress_callback:
            # Store callback in configurable for task nodes to emit events
            resume_configurable["progress_callback"] = progress_callback

            def path_emitter(router: Any, decision: Any, state: Any) -> None:
                if hasattr(progress_callback, "on_path_decision"):
                    progress_callback.on_path_decision(router, decision, state)

            resume_configurable["path_emitter"] = path_emitter

        run_config: dict[str, Any] = {
            "configurable": resume_configurable,
            # Increase recursion limit from default 25 to handle complex workflows
            "recursion_limit": 100,
        }

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
            # Check if there are actual interrupts in the pending tasks
            # Only use Command(resume=...) for interrupted workflows
            # For regular pending tasks (no interrupts), just continue with ainvoke(None)
            has_interrupts = False
            if state_snapshot.tasks:
                for task in state_snapshot.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        has_interrupts = True
                        break

            if has_interrupts:
                # Workflow is paused at an interrupt (human escalation, approval gate, etc.)
                # Use Command(resume=...) to provide human response
                logger.info(f"Resuming from interrupt at: {state_snapshot.next}")
                resume_input = human_response if human_response else {"action": "continue"}
                command = Command(resume=resume_input)

                if progress_callback:
                    result = await self._resume_with_callbacks(
                        command, run_config, progress_callback
                    )
                else:
                    result = await self.graph.ainvoke(command, config=run_config)
            else:
                # Workflow has pending tasks but no interrupts - just continue execution
                logger.info(f"Continuing workflow from: {state_snapshot.next}")
                if progress_callback:
                    result = await self._run_with_callbacks(
                        self.graph, None, run_config, progress_callback
                    )
                else:
                    result = await self.graph.ainvoke(None, config=run_config)
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
        if self.graph is None:
            raise RuntimeError("WorkflowRunner must be used as async context manager")

        result = None

        # Get current state to track phase changes
        state_snapshot = await self.graph.aget_state(run_config)
        previous_phase: int | None = None
        if state_snapshot and state_snapshot.values:
            previous_phase = state_snapshot.values.get("current_phase")

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

                        # Detect phase changes and emit phase events
                        current_phase = output.get("current_phase")
                        if current_phase is not None and current_phase != previous_phase:
                            try:
                                phase_status = output.get("phase_status", {})
                                prev_phase_status = (
                                    phase_status.get(str(previous_phase), {})
                                    if previous_phase
                                    else {}
                                )
                                # Handle both dict and PhaseState dataclass
                                if hasattr(prev_phase_status, "to_dict"):
                                    prev_phase_status = prev_phase_status.to_dict()
                                elif hasattr(prev_phase_status, "status"):
                                    # PhaseState dataclass - access status attribute directly
                                    status_val = getattr(prev_phase_status, "status", None)
                                    # Status might be a PhaseStatus enum
                                    if status_val is not None and hasattr(status_val, "value"):
                                        status_val = status_val.value
                                    prev_phase_status = {"status": status_val}
                                prev_success = prev_phase_status.get("status") != "failed"

                                if previous_phase is not None and hasattr(callback, "on_phase_end"):
                                    callback.on_phase_end(
                                        phase=previous_phase,
                                        success=prev_success,
                                        node_name=event_name,
                                    )

                                if hasattr(callback, "on_phase_change"):
                                    callback.on_phase_change(
                                        from_phase=previous_phase or 0,
                                        to_phase=current_phase,
                                        status="in_progress",
                                    )

                                if hasattr(callback, "on_phase_start"):
                                    callback.on_phase_start(
                                        phase=current_phase,
                                        node_name=event_name,
                                    )

                                previous_phase = current_phase
                            except Exception as e:
                                logger.warning(f"Callback error on phase change: {e}")

        return result or {}

    async def get_state(self) -> Any:
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

    async def get_history(self, limit: Optional[int] = None) -> list[dict]:
        """Get the workflow execution history with pagination.

        Args:
            limit: Maximum checkpoints to return (default 50)

        Returns:
            List of state snapshots (limited to prevent memory issues)
        """
        if self.graph is None:
            raise RuntimeError("WorkflowRunner must be used as async context manager")

        effective_limit = limit or self.MAX_HISTORY_CHECKPOINTS
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
            if len(history) >= effective_limit:
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

        async def _get() -> Optional[dict]:
            async with WorkflowRunner(self.project_dir) as runner:
                return await runner.get_pending_interrupt_async()

        result = asyncio.run(_get())
        return result


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
