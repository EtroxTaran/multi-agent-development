"""Universal node wrapper for global error handling and agent tracking.

Provides a decorator that wraps all LangGraph nodes to:
1. Capture exceptions with rich context (stack trace, stderr, state snapshot)
2. Route ALL errors through error_dispatch → fixer
3. Track agent executions and set last_agent_execution
4. Route to evaluation after agent calls

Usage:
    @wrapped_node
    async def my_node(state: WorkflowState) -> dict[str, Any]:
        ...

    # Or with explicit metadata
    @wrapped_node(agent="claude", template="planning")
    async def planning_node(state: WorkflowState) -> dict[str, Any]:
        ...
"""

import asyncio
import functools
import logging
import time
from datetime import datetime
from typing import Any, Callable, Optional, TypeVar, Union

from ..state import (
    WorkflowState,
    WorkflowDecision,
    ErrorContext,
    AgentExecution,
    create_error_context,
    create_agent_execution,
)

logger = logging.getLogger(__name__)

# Type for node functions
NodeFunc = Callable[[WorkflowState], dict[str, Any]]
AsyncNodeFunc = Callable[[WorkflowState], "asyncio.coroutine"]

T = TypeVar("T", bound=Union[NodeFunc, AsyncNodeFunc])


# Registry of nodes and their metadata
# Maps node_name -> {agent, template, is_agent_node, auto_evaluate}
NODE_REGISTRY: dict[str, dict[str, Any]] = {}


# Nodes that call agents (Claude, Cursor, Gemini)
# These should track executions and route to evaluation
AGENT_NODES: dict[str, dict[str, str]] = {
    # Planning phase
    "planning": {"agent": "claude", "template": "planning"},
    # Validation phase
    "cursor_validate": {"agent": "cursor", "template": "validation"},
    "gemini_validate": {"agent": "gemini", "template": "validation"},
    # Implementation phase
    "implement_task": {"agent": "claude", "template": "task_implementation"},
    "implementation": {"agent": "claude", "template": "implementation"},
    "write_tests": {"agent": "claude", "template": "test_writing"},
    "fix_bug": {"agent": "claude", "template": "bug_fix"},
    # Verification phase
    "cursor_review": {"agent": "cursor", "template": "code_review"},
    "gemini_review": {"agent": "gemini", "template": "architecture_review"},
    # Research phase
    "research": {"agent": "claude", "template": "research"},
    # Fixer
    "fixer_diagnose": {"agent": "claude", "template": "fixer_diagnose"},
    "fixer_apply": {"agent": "claude", "template": "fixer_apply"},
}


def get_node_metadata(node_name: str) -> Optional[dict[str, Any]]:
    """Get metadata for a node from the registry.

    Args:
        node_name: Name of the node

    Returns:
        Node metadata or None if not registered
    """
    return NODE_REGISTRY.get(node_name)


def is_agent_node(node_name: str) -> bool:
    """Check if a node calls an agent.

    Args:
        node_name: Name of the node

    Returns:
        True if node calls an agent
    """
    return node_name in AGENT_NODES


class NodeWrapper:
    """Wrapper class that provides global error handling and execution tracking.

    Wraps any node function to:
    1. Catch all exceptions and create rich ErrorContext
    2. Set next_decision to "escalate" on error for routing to error_dispatch
    3. Track agent executions in execution_history
    4. Set last_agent_execution for evaluation routing
    """

    def __init__(
        self,
        node_func: T,
        node_name: Optional[str] = None,
        agent: Optional[str] = None,
        template: Optional[str] = None,
        auto_evaluate: bool = True,
    ):
        """Initialize the wrapper.

        Args:
            node_func: The node function to wrap
            node_name: Override for node name (defaults to function name)
            agent: Agent name if this node calls an agent
            template: Template name if this node uses a prompt template
            auto_evaluate: Whether to auto-route to evaluation after agent call
        """
        self.node_func = node_func
        self.node_name = node_name or node_func.__name__
        self.agent = agent
        self.template = template
        self.auto_evaluate = auto_evaluate

        # Auto-detect agent info if not provided
        if self.agent is None and self.node_name in AGENT_NODES:
            info = AGENT_NODES[self.node_name]
            self.agent = info["agent"]
            self.template = self.template or info["template"]

        # Register node metadata
        NODE_REGISTRY[self.node_name] = {
            "agent": self.agent,
            "template": self.template,
            "is_agent_node": self.agent is not None,
            "auto_evaluate": self.auto_evaluate,
        }

        # Preserve function metadata
        functools.update_wrapper(self, node_func)

    async def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Execute the wrapped node with error handling and tracking.

        Args:
            state: Current workflow state

        Returns:
            State updates from the node, or error state if exception
        """
        start_time = time.time()
        execution: Optional[AgentExecution] = None

        try:
            # Execute the node
            if asyncio.iscoroutinefunction(self.node_func):
                result = await self.node_func(state)
            else:
                result = self.node_func(state)

            # Track successful agent execution
            if self.agent and self.template:
                duration = time.time() - start_time
                execution = self._create_execution_record(
                    state=state,
                    output=result,
                    success=True,
                    duration=duration,
                )
                result = self._add_execution_to_result(result, execution)

            return result

        except Exception as e:
            # Create rich error context
            duration = time.time() - start_time
            error_context = create_error_context(
                source_node=self.node_name,
                exception=e,
                state=dict(state) if state else None,
                last_execution=execution,
                recoverable=self._is_recoverable_error(e),
            )

            # Track failed agent execution if this was an agent node
            if self.agent and self.template:
                execution = self._create_execution_record(
                    state=state,
                    output={"error": str(e)},
                    success=False,
                    duration=duration,
                    error_context=error_context,
                )

            logger.error(
                f"Node {self.node_name} failed with {type(e).__name__}: {e}",
                extra={
                    "error_id": error_context.get("error_id"),
                    "node": self.node_name,
                    "recoverable": error_context.get("recoverable"),
                },
            )

            # Return error state for routing to error_dispatch
            error_result = {
                "errors": [{
                    "type": error_context.get("error_type"),
                    "message": error_context.get("error_message"),
                    "source_node": self.node_name,
                    "timestamp": datetime.now().isoformat(),
                    "error_id": error_context.get("error_id"),
                }],
                "error_context": error_context,
                "next_decision": WorkflowDecision.ESCALATE,
                "updated_at": datetime.now().isoformat(),
            }

            # Add execution history if we have one
            if execution:
                error_result["execution_history"] = [execution]
                error_result["last_agent_execution"] = execution

            return error_result

    def _create_execution_record(
        self,
        state: WorkflowState,
        output: dict,
        success: bool,
        duration: float,
        error_context: Optional[ErrorContext] = None,
    ) -> AgentExecution:
        """Create an agent execution record.

        Args:
            state: Current workflow state
            output: Node output (may contain prompt/output info)
            success: Whether execution succeeded
            duration: Execution duration in seconds
            error_context: Error context if failed

        Returns:
            AgentExecution record
        """
        # Extract prompt and output from result if available
        # Nodes should include these in their output for tracking
        prompt = output.get("_prompt", "")
        agent_output = output.get("_output", str(output))
        exit_code = output.get("_exit_code", 0 if success else 1)
        cost_usd = output.get("_cost_usd", 0.0)
        model = output.get("_model", "")
        input_tokens = output.get("_input_tokens")
        output_tokens = output.get("_output_tokens")

        return create_agent_execution(
            agent=self.agent or "unknown",
            node=self.node_name,
            template_name=self.template or "unknown",
            prompt=prompt,
            output=agent_output if isinstance(agent_output, str) else str(agent_output),
            success=success,
            exit_code=exit_code,
            duration_seconds=duration,
            cost_usd=cost_usd,
            model=model,
            task_id=state.get("current_task_id"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error_context=error_context,
        )

    def _add_execution_to_result(
        self,
        result: dict[str, Any],
        execution: AgentExecution,
    ) -> dict[str, Any]:
        """Add execution tracking to node result.

        Args:
            result: Original node result
            execution: Execution record to add

        Returns:
            Result with execution tracking
        """
        # Don't modify internal tracking fields in the result
        result_copy = dict(result)

        # Remove internal tracking fields from final output
        for key in ["_prompt", "_output", "_exit_code", "_cost_usd", "_model", "_input_tokens", "_output_tokens"]:
            result_copy.pop(key, None)

        # Add execution tracking
        result_copy["last_agent_execution"] = execution
        result_copy["execution_history"] = [execution]

        return result_copy

    def _is_recoverable_error(self, e: Exception) -> bool:
        """Determine if an error is likely recoverable.

        Args:
            e: The exception

        Returns:
            True if error might be auto-fixable
        """
        recoverable_types = {
            "TimeoutError",
            "ConnectionError",
            "FileNotFoundError",
            "ImportError",
            "SyntaxError",
            "JSONDecodeError",
            "AssertionError",
            "KeyError",
            "ValueError",
        }
        return type(e).__name__ in recoverable_types


def wrapped_node(
    func: Optional[T] = None,
    *,
    name: Optional[str] = None,
    agent: Optional[str] = None,
    template: Optional[str] = None,
    auto_evaluate: bool = True,
) -> Union[T, Callable[[T], T]]:
    """Decorator for wrapping node functions with global error handling.

    Can be used with or without arguments:

        @wrapped_node
        async def my_node(state): ...

        @wrapped_node(agent="claude", template="planning")
        async def planning_node(state): ...

    Args:
        func: The node function (when used without parentheses)
        name: Override for node name
        agent: Agent name if node calls an agent
        template: Template name if node uses a prompt
        auto_evaluate: Whether to auto-route to evaluation

    Returns:
        Wrapped node function
    """
    def decorator(f: T) -> T:
        wrapper = NodeWrapper(
            f,
            node_name=name,
            agent=agent,
            template=template,
            auto_evaluate=auto_evaluate,
        )
        return wrapper  # type: ignore

    if func is not None:
        # Called without parentheses: @wrapped_node
        return decorator(func)
    else:
        # Called with parentheses: @wrapped_node(...)
        return decorator


def wrap_existing_node(
    node_func: T,
    node_name: str,
    agent: Optional[str] = None,
    template: Optional[str] = None,
) -> T:
    """Wrap an existing node function without using decorator syntax.

    Useful for wrapping imported node functions in workflow.py:

        from .nodes import planning_node
        planning_node = wrap_existing_node(planning_node, "planning", "claude", "planning")

    Args:
        node_func: The node function to wrap
        node_name: Name of the node
        agent: Agent name if applicable
        template: Template name if applicable

    Returns:
        Wrapped node function
    """
    return NodeWrapper(  # type: ignore
        node_func,
        node_name=node_name,
        agent=agent,
        template=template,
    )
