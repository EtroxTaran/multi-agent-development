"""Execution tracker for monitoring all agent calls.

Provides utilities for tracking agent executions across the workflow,
enabling global evaluation and optimization.
"""

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..state import AgentExecution, ErrorContext, create_agent_execution

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Context for an in-progress execution."""

    agent: str
    node: str
    template_name: str
    task_id: Optional[str]
    start_time: float = field(default_factory=time.time)
    prompt: str = ""
    model: str = ""

    def elapsed_seconds(self) -> float:
        """Get elapsed time since execution started."""
        return time.time() - self.start_time


class ExecutionTracker:
    """Tracks agent executions for a workflow run.

    Usage:
        tracker = ExecutionTracker()

        with tracker.track("claude", "planning", "planning_template") as ctx:
            ctx.prompt = prompt
            result = run_agent(prompt)
            ctx.model = result.model

        execution = tracker.complete_execution(
            success=True,
            output=result.output,
            exit_code=0,
        )
    """

    def __init__(self):
        """Initialize the tracker."""
        self._current_execution: Optional[ExecutionContext] = None
        self._executions: list[AgentExecution] = []

    @contextmanager
    def track(
        self,
        agent: str,
        node: str,
        template_name: str,
        task_id: Optional[str] = None,
    ) -> Generator[ExecutionContext, None, None]:
        """Context manager for tracking an execution.

        Args:
            agent: Agent name (claude, cursor, gemini)
            node: Workflow node name
            template_name: Prompt template name
            task_id: Associated task ID

        Yields:
            ExecutionContext to populate during execution
        """
        ctx = ExecutionContext(
            agent=agent,
            node=node,
            template_name=template_name,
            task_id=task_id,
        )
        self._current_execution = ctx

        try:
            yield ctx
        finally:
            self._current_execution = None

    def complete_execution(
        self,
        success: bool,
        output: str = "",
        exit_code: int = 0,
        cost_usd: float = 0.0,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        error_context: Optional[ErrorContext] = None,
    ) -> AgentExecution:
        """Complete the current execution and create a record.

        Args:
            success: Whether execution succeeded
            output: Agent output
            exit_code: CLI exit code
            cost_usd: Estimated cost
            input_tokens: Input token count
            output_tokens: Output token count
            error_context: Error context if failed

        Returns:
            Completed AgentExecution record
        """
        if self._current_execution is None:
            raise RuntimeError("No active execution to complete")

        ctx = self._current_execution
        duration = ctx.elapsed_seconds()

        execution = create_agent_execution(
            agent=ctx.agent,
            node=ctx.node,
            template_name=ctx.template_name,
            prompt=ctx.prompt,
            output=output,
            success=success,
            exit_code=exit_code,
            duration_seconds=duration,
            cost_usd=cost_usd,
            model=ctx.model,
            task_id=ctx.task_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error_context=error_context,
        )

        self._executions.append(execution)
        return execution

    def get_executions(self) -> list[AgentExecution]:
        """Get all tracked executions."""
        return list(self._executions)

    def get_last_execution(self) -> Optional[AgentExecution]:
        """Get the most recent execution."""
        return self._executions[-1] if self._executions else None

    def clear(self) -> None:
        """Clear all tracked executions."""
        self._executions.clear()


# Global tracker instance (one per workflow run)
_tracker: Optional[ExecutionTracker] = None


def get_execution_tracker() -> ExecutionTracker:
    """Get the global execution tracker.

    Creates a new tracker if one doesn't exist.

    Returns:
        Global ExecutionTracker instance
    """
    global _tracker
    if _tracker is None:
        _tracker = ExecutionTracker()
    return _tracker


def reset_execution_tracker() -> None:
    """Reset the global execution tracker."""
    global _tracker
    _tracker = None


@contextmanager
def track_agent_execution(
    agent: str,
    node: str,
    template_name: str,
    task_id: Optional[str] = None,
) -> Generator[ExecutionContext, None, None]:
    """Convenience context manager for tracking agent execution.

    Uses the global tracker.

    Args:
        agent: Agent name
        node: Node name
        template_name: Template name
        task_id: Task ID

    Yields:
        ExecutionContext
    """
    tracker = get_execution_tracker()
    with tracker.track(agent, node, template_name, task_id) as ctx:
        yield ctx


def create_execution_from_result(
    agent: str,
    node: str,
    template_name: str,
    prompt: str,
    result: dict[str, Any],
    task_id: Optional[str] = None,
) -> AgentExecution:
    """Create an execution record from a node result.

    Extracts execution metadata from the result dict.

    Args:
        agent: Agent name
        node: Node name
        template_name: Template name
        prompt: Prompt sent to agent
        result: Node result dict
        task_id: Task ID

    Returns:
        AgentExecution record
    """
    # Extract standard fields from result
    success = result.get("success", not result.get("errors"))
    output = result.get("output", result.get("response", str(result)))
    exit_code = result.get("exit_code", 0 if success else 1)
    cost_usd = result.get("cost_usd", 0.0)
    model = result.get("model", "")
    duration = result.get("duration_seconds", 0.0)
    input_tokens = result.get("input_tokens")
    output_tokens = result.get("output_tokens")

    return create_agent_execution(
        agent=agent,
        node=node,
        template_name=template_name,
        prompt=prompt,
        output=output if isinstance(output, str) else str(output),
        success=success,
        exit_code=exit_code,
        duration_seconds=duration,
        cost_usd=cost_usd,
        model=model,
        task_id=task_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def build_execution_state_update(
    execution: AgentExecution,
) -> dict[str, Any]:
    """Build state update dict for an execution.

    Args:
        execution: AgentExecution record

    Returns:
        Dict to merge into state
    """
    return {
        "last_agent_execution": execution,
        "execution_history": [execution],
        "updated_at": datetime.now().isoformat(),
    }
