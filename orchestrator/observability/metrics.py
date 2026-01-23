"""Prometheus metrics for the orchestrator.

Provides metrics for monitoring workflow execution, agent invocations,
and error rates.

Metrics exposed:
    orchestrator_workflow_phase_duration_seconds - Phase execution time
    orchestrator_workflow_total - Total workflows by status
    orchestrator_agent_invocations_total - Agent invocations by status
    orchestrator_agent_cost_dollars - Cumulative agent costs
    orchestrator_errors_total - Errors by severity and phase
"""

import logging
import threading
from typing import Optional

from .config import get_config

logger = logging.getLogger(__name__)

# Singleton registry
_registry: Optional["MetricsRegistry"] = None
_registry_lock = threading.Lock()

# Optional import - graceful degradation if prometheus_client not installed
try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        CollectorRegistry,
        start_http_server,
        REGISTRY,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.debug("prometheus_client not installed, metrics disabled")


class MetricsRegistry:
    """Registry for Prometheus metrics.

    Provides lazy initialization of metrics and handles the case
    where prometheus_client is not installed.
    """

    def __init__(self):
        """Initialize the metrics registry."""
        self.config = get_config().prometheus
        self._initialized = False
        self._server_started = False

        # Metrics will be initialized lazily
        self._workflow_phase_duration: Optional["Histogram"] = None
        self._workflow_total: Optional["Counter"] = None
        self._agent_invocations: Optional["Counter"] = None
        self._agent_cost: Optional["Counter"] = None
        self._errors_total: Optional["Counter"] = None
        self._active_workflows: Optional["Gauge"] = None
        self._active_tasks: Optional["Gauge"] = None

    def _ensure_initialized(self) -> bool:
        """Ensure metrics are initialized.

        Returns:
            True if metrics are available
        """
        if not self.config.enabled or not PROMETHEUS_AVAILABLE:
            return False

        if self._initialized:
            return True

        try:
            namespace = self.config.namespace

            self._workflow_phase_duration = Histogram(
                f"{namespace}_workflow_phase_duration_seconds",
                "Time spent in each workflow phase",
                ["phase", "status"],
                buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
            )

            self._workflow_total = Counter(
                f"{namespace}_workflow_total",
                "Total number of workflows",
                ["status"],
            )

            self._agent_invocations = Counter(
                f"{namespace}_agent_invocations_total",
                "Total agent invocations",
                ["agent", "status"],
            )

            self._agent_cost = Counter(
                f"{namespace}_agent_cost_dollars",
                "Cumulative agent costs in dollars",
                ["agent"],
            )

            self._errors_total = Counter(
                f"{namespace}_errors_total",
                "Total errors by severity and phase",
                ["severity", "phase"],
            )

            self._active_workflows = Gauge(
                f"{namespace}_active_workflows",
                "Number of currently active workflows",
            )

            self._active_tasks = Gauge(
                f"{namespace}_active_tasks",
                "Number of currently active tasks",
                ["project"],
            )

            self._initialized = True
            logger.info("Prometheus metrics initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Prometheus metrics: {e}")
            return False

    def start_server(self) -> bool:
        """Start the Prometheus HTTP server.

        Returns:
            True if server started successfully
        """
        if not self._ensure_initialized():
            return False

        if self._server_started:
            return True

        try:
            start_http_server(
                port=self.config.port,
                addr=self.config.host,
            )
            self._server_started = True
            logger.info(
                f"Prometheus metrics server started on "
                f"{self.config.host}:{self.config.port}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to start Prometheus server: {e}")
            return False

    def record_phase_duration(
        self,
        phase: str,
        duration_seconds: float,
        status: str = "success",
    ) -> None:
        """Record workflow phase duration.

        Args:
            phase: Phase name (e.g., "planning", "validation")
            duration_seconds: Duration in seconds
            status: Phase status (success, failure, skipped)
        """
        if self._ensure_initialized() and self._workflow_phase_duration:
            self._workflow_phase_duration.labels(
                phase=phase,
                status=status,
            ).observe(duration_seconds)

    def record_workflow(self, status: str) -> None:
        """Record a workflow completion.

        Args:
            status: Workflow status (completed, failed, cancelled)
        """
        if self._ensure_initialized() and self._workflow_total:
            self._workflow_total.labels(status=status).inc()

    def record_agent_invocation(
        self,
        agent: str,
        status: str,
        cost_usd: float = 0.0,
    ) -> None:
        """Record an agent invocation.

        Args:
            agent: Agent name (claude, cursor, gemini)
            status: Invocation status (success, failure, timeout)
            cost_usd: Cost in dollars
        """
        if self._ensure_initialized():
            if self._agent_invocations:
                self._agent_invocations.labels(
                    agent=agent,
                    status=status,
                ).inc()

            if self._agent_cost and cost_usd > 0:
                self._agent_cost.labels(agent=agent).inc(cost_usd)

    def record_error(self, severity: str, phase: str) -> None:
        """Record an error.

        Args:
            severity: Error severity (warning, error, critical)
            phase: Workflow phase where error occurred
        """
        if self._ensure_initialized() and self._errors_total:
            self._errors_total.labels(
                severity=severity,
                phase=phase,
            ).inc()

    def set_active_workflows(self, count: int) -> None:
        """Set the number of active workflows.

        Args:
            count: Number of active workflows
        """
        if self._ensure_initialized() and self._active_workflows:
            self._active_workflows.set(count)

    def set_active_tasks(self, project: str, count: int) -> None:
        """Set the number of active tasks for a project.

        Args:
            project: Project name
            count: Number of active tasks
        """
        if self._ensure_initialized() and self._active_tasks:
            self._active_tasks.labels(project=project).set(count)


def get_metrics_registry() -> MetricsRegistry:
    """Get the metrics registry singleton.

    Returns:
        MetricsRegistry instance
    """
    global _registry

    with _registry_lock:
        if _registry is None:
            _registry = MetricsRegistry()
        return _registry
