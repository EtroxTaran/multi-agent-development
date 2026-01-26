"""Dashboard callback implementing ProgressCallback protocol.

This callback emits events through the EventEmitter, which writes them
to SurrealDB for the dashboard to subscribe to via live queries.
"""

import asyncio
import logging
import time
from typing import Any, Optional

from .emitter import EventEmitter
from .types import (
    agent_complete_event,
    agent_start_event,
    error_event,
    escalation_event,
    metrics_update_event,
    node_end_event,
    node_start_event,
    path_decision_event,
    ralph_iteration_event,
    task_complete_event,
    task_start_event,
    workflow_complete_event,
    workflow_paused_event,
    workflow_start_event,
)

logger = logging.getLogger(__name__)


class DashboardCallback:
    """Callback handler that emits events to the dashboard via EventEmitter.

    Implements the ProgressCallback protocol with additional event types
    for comprehensive dashboard monitoring.
    """

    def __init__(
        self,
        emitter: EventEmitter,
        current_phase: int = 1,
    ):
        """Initialize callback handler.

        Args:
            emitter: EventEmitter for writing events to SurrealDB
            current_phase: Current workflow phase
        """
        self.emitter = emitter
        self.current_phase = current_phase
        self._node_start_times: dict[str, float] = {}

    def _emit_sync(self, coro) -> None:
        """Helper to emit async events from sync context."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            # No running loop - skip emission
            pass

    def set_phase(self, phase: int) -> None:
        """Update current phase."""
        self.current_phase = phase

    # ==================== ProgressCallback Protocol ====================

    def on_node_start(self, node_name: str, state: dict[str, Any]) -> None:
        """Called when a workflow node starts."""
        self._node_start_times[node_name] = time.time()

        # Extract minimal state summary to avoid large payloads
        state_summary = {
            "current_phase": state.get("current_phase"),
            "current_task_id": state.get("current_task_id"),
            "iteration_count": state.get("iteration_count"),
        }

        event = node_start_event(
            project_name=self.emitter.project_name,
            node_name=node_name,
            phase=self.current_phase,
            state_summary=state_summary,
        )
        self._emit_sync(self.emitter.emit(event))

    def on_node_end(self, node_name: str, state: dict[str, Any]) -> None:
        """Called when a workflow node ends."""
        # Calculate duration
        start_time = self._node_start_times.pop(node_name, None)
        duration = time.time() - start_time if start_time else None

        # Check for errors
        errors = state.get("errors", [])
        success = len(errors) == 0

        event = node_end_event(
            project_name=self.emitter.project_name,
            node_name=node_name,
            phase=self.current_phase,
            success=success,
            duration_seconds=duration,
        )
        self._emit_sync(self.emitter.emit(event))

    def on_ralph_iteration(
        self,
        task_id: str,
        iteration: int,
        max_iter: int,
        tests_passed: int = 0,
        tests_total: int = 0,
    ) -> None:
        """Called on each Ralph loop iteration."""
        event = ralph_iteration_event(
            project_name=self.emitter.project_name,
            task_id=task_id,
            iteration=iteration,
            max_iterations=max_iter,
            tests_passed=tests_passed,
            tests_total=tests_total,
        )
        self._emit_sync(self.emitter.emit(event))

    def on_task_start(self, task_id: str, task_title: str) -> None:
        """Called when a task starts."""
        event = task_start_event(
            project_name=self.emitter.project_name,
            task_id=task_id,
            task_title=task_title,
            phase=self.current_phase,
        )
        self._emit_sync(self.emitter.emit(event))

    def on_task_complete(self, task_id: str, success: bool) -> None:
        """Called when a task completes."""
        event = task_complete_event(
            project_name=self.emitter.project_name,
            task_id=task_id,
            success=success,
            phase=self.current_phase,
        )
        self._emit_sync(self.emitter.emit(event))

    def on_metrics_update(
        self,
        tokens: int = 0,
        cost: float = 0.0,
        files_created: Optional[int] = None,
        files_modified: Optional[int] = None,
    ) -> None:
        """Called when metrics are updated."""
        event = metrics_update_event(
            project_name=self.emitter.project_name,
            tokens=tokens,
            cost=cost,
            files_created=files_created,
            files_modified=files_modified,
        )
        self._emit_sync(self.emitter.emit(event))

    # ==================== Extended Event Methods ====================

    def on_agent_start(
        self,
        agent_name: str,
        node_name: str,
        task_id: Optional[str] = None,
    ) -> None:
        """Called when an agent (claude, cursor, gemini) starts."""
        event = agent_start_event(
            project_name=self.emitter.project_name,
            agent_name=agent_name,
            node_name=node_name,
            task_id=task_id,
        )
        self._emit_sync(self.emitter.emit(event))

    def on_agent_complete(
        self,
        agent_name: str,
        node_name: str,
        success: bool,
        duration_seconds: Optional[float] = None,
        task_id: Optional[str] = None,
    ) -> None:
        """Called when an agent completes."""
        event = agent_complete_event(
            project_name=self.emitter.project_name,
            agent_name=agent_name,
            node_name=node_name,
            success=success,
            duration_seconds=duration_seconds,
            task_id=task_id,
        )
        self._emit_sync(self.emitter.emit(event))

    def on_error(
        self,
        error_message: str,
        error_type: str,
        node_name: Optional[str] = None,
        task_id: Optional[str] = None,
        recoverable: bool = True,
    ) -> None:
        """Called when an error occurs."""
        event = error_event(
            project_name=self.emitter.project_name,
            error_message=error_message,
            error_type=error_type,
            node_name=node_name,
            task_id=task_id,
            recoverable=recoverable,
        )
        # Emit errors immediately (high priority)
        self._emit_sync(self.emitter.emit_now(event))

    def on_escalation(
        self,
        question: str,
        options: Optional[list[str]] = None,
        context: Optional[dict] = None,
        node_name: Optional[str] = None,
    ) -> None:
        """Called when human input is required."""
        event = escalation_event(
            project_name=self.emitter.project_name,
            question=question,
            options=options,
            context=context,
            node_name=node_name,
        )
        # Emit escalations immediately (high priority)
        self._emit_sync(self.emitter.emit_now(event))

    def on_path_decision(
        self,
        router: str,
        decision: str,
        state: dict[str, Any],
    ) -> None:
        """Called when a router makes a path decision."""
        event = path_decision_event(
            project_name=self.emitter.project_name,
            router=router,
            decision=decision,
            phase=self.current_phase,
        )
        self._emit_sync(self.emitter.emit(event))

    def on_hitl_interrupt(
        self,
        question: str,
        options: Optional[list[str]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Called when workflow hits HITL interrupt requiring user input."""
        self.on_escalation(
            question=question,
            options=options,
            context=context,
        )

    def on_workflow_start(
        self,
        mode: str = "langgraph",
        start_phase: int = 1,
        autonomous: bool = False,
    ) -> None:
        """Called when workflow starts."""
        event = workflow_start_event(
            project_name=self.emitter.project_name,
            mode=mode,
            start_phase=start_phase,
            autonomous=autonomous,
        )
        self._emit_sync(self.emitter.emit_now(event))

    def on_workflow_complete(
        self,
        success: bool,
        final_phase: int,
        summary: Optional[dict] = None,
    ) -> None:
        """Called when workflow completes."""
        event = workflow_complete_event(
            project_name=self.emitter.project_name,
            success=success,
            final_phase=final_phase,
            summary=summary,
        )
        self._emit_sync(self.emitter.emit_now(event))

    def on_workflow_paused(
        self,
        reason: Optional[str] = None,
        node_name: Optional[str] = None,
    ) -> None:
        """Called when workflow is paused."""
        event = workflow_paused_event(
            project_name=self.emitter.project_name,
            phase=self.current_phase,
            node_name=node_name,
            reason=reason,
        )
        self._emit_sync(self.emitter.emit_now(event))


def create_dashboard_callback(
    project_name: str,
    enabled: bool = True,
    current_phase: int = 1,
) -> DashboardCallback:
    """Create a dashboard callback for a project.

    Args:
        project_name: Project name
        enabled: Whether event emission is enabled
        current_phase: Starting workflow phase

    Returns:
        Configured DashboardCallback
    """
    from .emitter import create_event_emitter

    emitter = create_event_emitter(project_name, enabled=enabled)
    return DashboardCallback(emitter, current_phase=current_phase)
