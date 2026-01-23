"""Observability manager facade.

Provides a unified interface for all observability features.
"""

import asyncio
import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Optional

from .config import get_config
from .metrics import MetricsRegistry, get_metrics_registry
from .tracing import TracingManager, get_tracing_manager
from .webhooks import WebhookDispatcher, WebhookEventType, get_webhook_dispatcher

logger = logging.getLogger(__name__)

# Singleton manager
_manager: Optional["ObservabilityManager"] = None


class ObservabilityManager:
    """Unified observability manager.

    Coordinates metrics, tracing, and webhooks to provide a single
    interface for recording workflow events.
    """

    def __init__(self):
        """Initialize the observability manager."""
        self.config = get_config()
        self._metrics: Optional[MetricsRegistry] = None
        self._tracing: Optional[TracingManager] = None
        self._webhooks: Optional[WebhookDispatcher] = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize all observability components.

        Call this at application startup to set up metrics server,
        tracing exporters, etc.
        """
        if self._initialized:
            return

        if self.config.prometheus.enabled:
            self._metrics = get_metrics_registry()
            self._metrics.start_server()

        if self.config.tracing.enabled:
            self._tracing = get_tracing_manager()

        if self.config.webhooks.enabled:
            self._webhooks = get_webhook_dispatcher()

        self._initialized = True
        logger.info("Observability manager initialized")

    @property
    def metrics(self) -> Optional[MetricsRegistry]:
        """Get the metrics registry."""
        if self._metrics is None and self.config.prometheus.enabled:
            self._metrics = get_metrics_registry()
        return self._metrics

    @property
    def tracing(self) -> Optional[TracingManager]:
        """Get the tracing manager."""
        if self._tracing is None and self.config.tracing.enabled:
            self._tracing = get_tracing_manager()
        return self._tracing

    @property
    def webhooks(self) -> Optional[WebhookDispatcher]:
        """Get the webhook dispatcher."""
        if self._webhooks is None and self.config.webhooks.enabled:
            self._webhooks = get_webhook_dispatcher()
        return self._webhooks

    # Workflow Events

    def record_workflow_started(
        self,
        project: str,
        workflow_id: str,
    ) -> None:
        """Record workflow start.

        Args:
            project: Project name
            workflow_id: Workflow ID
        """
        if self.metrics:
            self.metrics.set_active_workflows(1)  # Simplified for now

        if self.webhooks:
            asyncio.create_task(
                self.webhooks.dispatch(
                    WebhookEventType.WORKFLOW_STARTED,
                    project,
                    workflow_id,
                )
            )

    def record_workflow_completed(
        self,
        project: str,
        workflow_id: str,
        duration_seconds: float,
    ) -> None:
        """Record workflow completion.

        Args:
            project: Project name
            workflow_id: Workflow ID
            duration_seconds: Total workflow duration
        """
        if self.metrics:
            self.metrics.record_workflow("completed")
            self.metrics.set_active_workflows(0)

        if self.webhooks:
            asyncio.create_task(
                self.webhooks.dispatch(
                    WebhookEventType.WORKFLOW_COMPLETED,
                    project,
                    workflow_id,
                    {"duration_seconds": duration_seconds},
                )
            )

    def record_workflow_failed(
        self,
        project: str,
        workflow_id: str,
        error: str,
    ) -> None:
        """Record workflow failure.

        Args:
            project: Project name
            workflow_id: Workflow ID
            error: Error message
        """
        if self.metrics:
            self.metrics.record_workflow("failed")
            self.metrics.record_error("error", "workflow")
            self.metrics.set_active_workflows(0)

        if self.webhooks:
            asyncio.create_task(
                self.webhooks.dispatch(
                    WebhookEventType.WORKFLOW_FAILED,
                    project,
                    workflow_id,
                    {"error": error},
                )
            )

    # Phase Events

    @contextmanager
    def phase_context(
        self,
        phase: str,
        project: str,
        workflow_id: str,
    ) -> Generator[None, None, None]:
        """Context manager for tracking phase execution.

        Args:
            phase: Phase name
            project: Project name
            workflow_id: Workflow ID

        Yields:
            None
        """
        start_time = time.time()
        status = "success"

        # Start tracing span
        tracing_ctx = None
        if self.tracing:
            tracing_ctx = self.tracing.phase_span(phase, project)
            tracing_ctx.__enter__()

        # Send phase started webhook
        if self.webhooks:
            asyncio.create_task(
                self.webhooks.dispatch(
                    WebhookEventType.PHASE_STARTED,
                    project,
                    workflow_id,
                    {"phase": phase},
                )
            )

        try:
            yield
        except Exception:
            status = "failure"
            if self.metrics:
                self.metrics.record_error("error", phase)
            raise
        finally:
            duration = time.time() - start_time

            # Record metrics
            if self.metrics:
                self.metrics.record_phase_duration(phase, duration, status)

            # End tracing span
            if tracing_ctx:
                tracing_ctx.__exit__(None, None, None)

            # Send phase completed webhook
            if self.webhooks:
                asyncio.create_task(
                    self.webhooks.dispatch(
                        WebhookEventType.PHASE_COMPLETED,
                        project,
                        workflow_id,
                        {
                            "phase": phase,
                            "status": status,
                            "duration_seconds": duration,
                        },
                    )
                )

    # Agent Events

    def record_agent_invocation(
        self,
        agent: str,
        task_id: str,
        success: bool,
        cost_usd: float = 0.0,
        duration_seconds: float = 0.0,
        model: Optional[str] = None,
        project: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> None:
        """Record an agent invocation.

        Args:
            agent: Agent name (claude, cursor, gemini)
            task_id: Task ID
            success: Whether invocation succeeded
            cost_usd: Cost in dollars
            duration_seconds: Duration in seconds
            model: Optional model name
            project: Optional project name
            workflow_id: Optional workflow ID
        """
        status = "success" if success else "failure"

        if self.metrics:
            self.metrics.record_agent_invocation(agent, status, cost_usd)

        # Note: Agent-level webhooks are typically not needed
        # as task events cover the same information

    # Task Events

    def record_task_started(
        self,
        project: str,
        workflow_id: str,
        task_id: str,
    ) -> None:
        """Record task start.

        Args:
            project: Project name
            workflow_id: Workflow ID
            task_id: Task ID
        """
        if self.metrics:
            self.metrics.set_active_tasks(project, 1)

        if self.webhooks:
            asyncio.create_task(
                self.webhooks.dispatch(
                    WebhookEventType.TASK_STARTED,
                    project,
                    workflow_id,
                    {"task_id": task_id},
                )
            )

    def record_task_completed(
        self,
        project: str,
        workflow_id: str,
        task_id: str,
        duration_seconds: float,
    ) -> None:
        """Record task completion.

        Args:
            project: Project name
            workflow_id: Workflow ID
            task_id: Task ID
            duration_seconds: Task duration
        """
        if self.metrics:
            self.metrics.set_active_tasks(project, 0)

        if self.webhooks:
            asyncio.create_task(
                self.webhooks.dispatch(
                    WebhookEventType.TASK_COMPLETED,
                    project,
                    workflow_id,
                    {
                        "task_id": task_id,
                        "duration_seconds": duration_seconds,
                    },
                )
            )

    def record_task_failed(
        self,
        project: str,
        workflow_id: str,
        task_id: str,
        error: str,
    ) -> None:
        """Record task failure.

        Args:
            project: Project name
            workflow_id: Workflow ID
            task_id: Task ID
            error: Error message
        """
        if self.metrics:
            self.metrics.record_error("error", "implementation")
            self.metrics.set_active_tasks(project, 0)

        if self.webhooks:
            asyncio.create_task(
                self.webhooks.dispatch(
                    WebhookEventType.TASK_FAILED,
                    project,
                    workflow_id,
                    {
                        "task_id": task_id,
                        "error": error,
                    },
                )
            )

    # Escalation Events

    def record_escalation(
        self,
        project: str,
        workflow_id: str,
        reason: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record an escalation event.

        Args:
            project: Project name
            workflow_id: Workflow ID
            reason: Escalation reason
            context: Optional context data
        """
        if self.metrics:
            self.metrics.record_error("warning", "escalation")

        if self.webhooks:
            data = {"reason": reason}
            if context:
                data["context"] = context

            asyncio.create_task(
                self.webhooks.dispatch(
                    WebhookEventType.ESCALATION_REQUIRED,
                    project,
                    workflow_id,
                    data,
                )
            )


def get_observability_manager() -> ObservabilityManager:
    """Get the observability manager singleton.

    Returns:
        ObservabilityManager instance
    """
    global _manager

    if _manager is None:
        _manager = ObservabilityManager()
    return _manager
