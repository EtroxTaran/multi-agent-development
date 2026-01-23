"""OpenTelemetry tracing for the orchestrator.

Provides distributed tracing support with automatic span creation
for workflow phases and agent invocations.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Optional

from .config import get_config

logger = logging.getLogger(__name__)

# Singleton tracer
_tracer: Optional["TracingManager"] = None

# Optional import - graceful degradation if opentelemetry not installed
try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    from opentelemetry.trace import Span, Status, StatusCode

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    logger.debug("opentelemetry packages not installed, tracing disabled")


class TracingManager:
    """Manager for OpenTelemetry tracing.

    Handles tracer initialization and span creation.
    """

    def __init__(self):
        """Initialize the tracing manager."""
        self.config = get_config().tracing
        self._initialized = False
        self._tracer: Optional[Any] = None

    def _ensure_initialized(self) -> bool:
        """Ensure the tracer is initialized.

        Returns:
            True if tracing is available
        """
        if not self.config.enabled or not OTEL_AVAILABLE:
            return False

        if self._initialized:
            return True

        try:
            # Create resource with service information
            resource = Resource.create(
                {
                    "service.name": self.config.service_name,
                    "service.version": "1.0.0",
                }
            )

            # Create tracer provider
            provider = TracerProvider(resource=resource)

            # Configure exporter
            exporter = OTLPSpanExporter(
                endpoint=self.config.endpoint,
                insecure=self.config.insecure,
            )

            # Use batch or simple processor based on config
            if self.config.batch_export:
                processor = BatchSpanProcessor(
                    exporter,
                    export_timeout_millis=self.config.export_timeout_millis,
                )
            else:
                processor = SimpleSpanProcessor(exporter)

            provider.add_span_processor(processor)

            # Set global tracer provider
            trace.set_tracer_provider(provider)

            # Get tracer
            self._tracer = trace.get_tracer(
                self.config.service_name,
                "1.0.0",
            )

            self._initialized = True
            logger.info(
                f"OpenTelemetry tracing initialized, " f"exporting to {self.config.endpoint}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize OpenTelemetry tracing: {e}")
            return False

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Generator[Optional[Any], None, None]:
        """Create a tracing span.

        Args:
            name: Span name
            attributes: Optional span attributes

        Yields:
            Span object or None if tracing not available
        """
        if not self._ensure_initialized() or not self._tracer:
            yield None
            return

        with self._tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            yield span

    @contextmanager
    def workflow_span(
        self,
        project: str,
        workflow_id: str,
    ) -> Generator[Optional[Any], None, None]:
        """Create a span for a workflow.

        Args:
            project: Project name
            workflow_id: Workflow ID

        Yields:
            Span object or None
        """
        with self.span(
            "workflow",
            attributes={
                "workflow.project": project,
                "workflow.id": workflow_id,
            },
        ) as span:
            yield span

    @contextmanager
    def phase_span(
        self,
        phase: str,
        project: str,
    ) -> Generator[Optional[Any], None, None]:
        """Create a span for a workflow phase.

        Args:
            phase: Phase name
            project: Project name

        Yields:
            Span object or None
        """
        with self.span(
            f"phase.{phase}",
            attributes={
                "workflow.phase": phase,
                "workflow.project": project,
            },
        ) as span:
            yield span

    @contextmanager
    def agent_span(
        self,
        agent: str,
        task_id: str,
        model: Optional[str] = None,
    ) -> Generator[Optional[Any], None, None]:
        """Create a span for an agent invocation.

        Args:
            agent: Agent name (claude, cursor, gemini)
            task_id: Task ID
            model: Optional model name

        Yields:
            Span object or None
        """
        attributes = {
            "agent.name": agent,
            "agent.task_id": task_id,
        }
        if model:
            attributes["agent.model"] = model

        with self.span(f"agent.{agent}", attributes=attributes) as span:
            yield span

    def record_exception(
        self,
        span: Optional[Any],
        exception: Exception,
    ) -> None:
        """Record an exception on a span.

        Args:
            span: Span to record on
            exception: Exception to record
        """
        if span is None or not OTEL_AVAILABLE:
            return

        try:
            span.record_exception(exception)
            span.set_status(Status(StatusCode.ERROR, str(exception)))
        except Exception as e:
            logger.warning(f"Failed to record exception on span: {e}")

    def set_span_status(
        self,
        span: Optional[Any],
        success: bool,
        message: Optional[str] = None,
    ) -> None:
        """Set the status of a span.

        Args:
            span: Span to update
            success: Whether the operation succeeded
            message: Optional status message
        """
        if span is None or not OTEL_AVAILABLE:
            return

        try:
            if success:
                span.set_status(Status(StatusCode.OK, message or ""))
            else:
                span.set_status(Status(StatusCode.ERROR, message or "Unknown error"))
        except Exception as e:
            logger.warning(f"Failed to set span status: {e}")


def get_tracing_manager() -> TracingManager:
    """Get the tracing manager singleton.

    Returns:
        TracingManager instance
    """
    global _tracer

    if _tracer is None:
        _tracer = TracingManager()
    return _tracer
