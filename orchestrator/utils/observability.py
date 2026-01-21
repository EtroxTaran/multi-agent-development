"""Observability and tracing for multi-agent workflows.

Implements:
- Distributed tracing (OpenTelemetry-compatible)
- Session tracking
- Span-level metrics
- Cost and latency tracking
- Agent execution visualization
"""

import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Generator
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SpanKind(Enum):
    """Type of span in the trace."""
    WORKFLOW = "workflow"       # Top-level workflow execution
    PHASE = "phase"             # Workflow phase (1-5)
    AGENT = "agent"             # Agent invocation
    LLM_CALL = "llm_call"       # LLM API call
    TOOL = "tool"               # Tool execution
    VALIDATION = "validation"   # Validation step
    INTERNAL = "internal"       # Internal operation


class SpanStatus(Enum):
    """Status of a span."""
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class SpanEvent:
    """An event within a span."""
    name: str
    timestamp: str
    attributes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Span:
    """A single span in a trace.

    Represents a unit of work (e.g., an agent call, LLM request, or phase).
    """
    trace_id: str
    span_id: str
    name: str
    kind: SpanKind
    start_time: str
    end_time: Optional[str] = None
    parent_span_id: Optional[str] = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: dict = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)

    # Metrics
    duration_ms: Optional[float] = None
    token_count: Optional[int] = None
    cost: Optional[float] = None

    def end(self, status: SpanStatus = SpanStatus.OK) -> None:
        """End the span."""
        self.end_time = datetime.now().isoformat()
        self.status = status

        # Calculate duration
        start = datetime.fromisoformat(self.start_time)
        end = datetime.fromisoformat(self.end_time)
        self.duration_ms = (end - start).total_seconds() * 1000

    def add_event(self, name: str, attributes: Optional[dict] = None) -> None:
        """Add an event to the span."""
        self.events.append(SpanEvent(
            name=name,
            timestamp=datetime.now().isoformat(),
            attributes=attributes or {},
        ))

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute."""
        self.attributes[key] = value

    def set_error(self, error: Exception) -> None:
        """Record an error on the span."""
        self.status = SpanStatus.ERROR
        self.attributes["error.type"] = type(error).__name__
        self.attributes["error.message"] = str(error)
        self.add_event("exception", {
            "exception.type": type(error).__name__,
            "exception.message": str(error),
        })

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "name": self.name,
            "kind": self.kind.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "parent_span_id": self.parent_span_id,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": [e.to_dict() for e in self.events],
            "duration_ms": self.duration_ms,
            "token_count": self.token_count,
            "cost": self.cost,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Span":
        data["kind"] = SpanKind(data["kind"])
        data["status"] = SpanStatus(data["status"])
        data["events"] = [SpanEvent(**e) for e in data.get("events", [])]
        return cls(**data)


@dataclass
class Trace:
    """A complete trace representing a workflow execution."""
    trace_id: str
    name: str
    start_time: str
    end_time: Optional[str] = None
    spans: list[Span] = field(default_factory=list)
    session_id: Optional[str] = None

    # Aggregated metrics
    total_duration_ms: Optional[float] = None
    total_tokens: int = 0
    total_cost: float = 0.0
    span_count: int = 0
    error_count: int = 0

    def add_span(self, span: Span) -> None:
        """Add a span to the trace."""
        self.spans.append(span)
        self.span_count += 1

        if span.token_count:
            self.total_tokens += span.token_count
        if span.cost:
            self.total_cost += span.cost
        if span.status == SpanStatus.ERROR:
            self.error_count += 1

    def end(self) -> None:
        """End the trace."""
        self.end_time = datetime.now().isoformat()
        start = datetime.fromisoformat(self.start_time)
        end = datetime.fromisoformat(self.end_time)
        self.total_duration_ms = (end - start).total_seconds() * 1000

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "session_id": self.session_id,
            "spans": [s.to_dict() for s in self.spans],
            "total_duration_ms": self.total_duration_ms,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "span_count": self.span_count,
            "error_count": self.error_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Trace":
        spans = [Span.from_dict(s) for s in data.pop("spans", [])]
        trace = cls(**data)
        trace.spans = spans
        return trace


class Tracer:
    """Distributed tracer for multi-agent workflows.

    Provides OpenTelemetry-compatible tracing with:
    - Hierarchical span tracking
    - Automatic context propagation
    - Cost and latency metrics
    - Persistence and export
    - Rolling trace buffer with configurable max size
    """

    # Default maximum traces to keep in memory
    DEFAULT_MAX_TRACES = 100

    def __init__(
        self,
        service_name: str,
        storage_dir: str | Path,
        session_id: Optional[str] = None,
        max_traces: int = None,
    ):
        """Initialize tracer.

        Args:
            service_name: Name of the service being traced
            storage_dir: Directory to store traces
            session_id: Optional session ID for grouping traces
            max_traces: Maximum traces to keep in memory (default 100)
        """
        self.service_name = service_name
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or str(uuid.uuid4())
        self.max_traces = max_traces or self.DEFAULT_MAX_TRACES

        self._current_trace: Optional[Trace] = None
        self._span_stack: list[Span] = []
        self._traces: list[Trace] = []

    def _generate_id(self) -> str:
        """Generate a unique ID."""
        return str(uuid.uuid4()).replace("-", "")[:16]

    def start_trace(self, name: str) -> Trace:
        """Start a new trace.

        Args:
            name: Name of the trace (e.g., workflow name)

        Returns:
            New Trace object
        """
        trace = Trace(
            trace_id=self._generate_id(),
            name=name,
            start_time=datetime.now().isoformat(),
            session_id=self.session_id,
        )
        self._current_trace = trace
        self._span_stack = []

        logger.debug(f"Started trace: {trace.trace_id} ({name})")
        return trace

    def end_trace(self) -> Optional[Trace]:
        """End the current trace.

        Implements rolling window - drops oldest traces when max_traces exceeded.

        Returns:
            Completed Trace object
        """
        if not self._current_trace:
            return None

        self._current_trace.end()
        self._traces.append(self._current_trace)
        self._save_trace(self._current_trace)

        # Enforce rolling window - drop oldest traces if over limit
        while len(self._traces) > self.max_traces:
            self._traces.pop(0)

        logger.debug(
            f"Ended trace: {self._current_trace.trace_id} "
            f"({self._current_trace.total_duration_ms:.0f}ms, "
            f"${self._current_trace.total_cost:.4f})"
        )

        trace = self._current_trace
        self._current_trace = None
        return trace

    def clear_traces(self) -> int:
        """Clear all in-memory traces.

        Call this at workflow end to free memory.
        Traces are still persisted to disk.

        Returns:
            Number of traces cleared
        """
        count = len(self._traces)
        self._traces.clear()
        self._span_stack.clear()
        self._current_trace = None
        logger.debug(f"Cleared {count} traces from memory")
        return count

    @contextmanager
    def span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[dict] = None,
    ) -> Generator[Span, None, None]:
        """Context manager for creating a span.

        Args:
            name: Span name
            kind: Type of span
            attributes: Initial attributes

        Yields:
            Span object
        """
        span = self.start_span(name, kind, attributes)
        try:
            yield span
            span.end(SpanStatus.OK)
        except Exception as e:
            span.set_error(e)
            span.end(SpanStatus.ERROR)
            raise
        finally:
            self.end_span()

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[dict] = None,
    ) -> Span:
        """Start a new span.

        Args:
            name: Span name
            kind: Type of span
            attributes: Initial attributes

        Returns:
            New Span object
        """
        if not self._current_trace:
            self.start_trace("auto-trace")

        parent_span_id = self._span_stack[-1].span_id if self._span_stack else None

        span = Span(
            trace_id=self._current_trace.trace_id,
            span_id=self._generate_id(),
            name=name,
            kind=kind,
            start_time=datetime.now().isoformat(),
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )

        span.set_attribute("service.name", self.service_name)
        self._span_stack.append(span)

        logger.debug(f"Started span: {span.span_id} ({name})")
        return span

    def end_span(self) -> Optional[Span]:
        """End the current span.

        Returns:
            Completed Span object
        """
        if not self._span_stack:
            return None

        span = self._span_stack.pop()
        if span.status == SpanStatus.UNSET:
            span.end(SpanStatus.OK)

        if self._current_trace:
            self._current_trace.add_span(span)

        logger.debug(
            f"Ended span: {span.span_id} ({span.name}) - "
            f"{span.duration_ms:.0f}ms, status={span.status.value}"
        )

        return span

    def current_span(self) -> Optional[Span]:
        """Get the current active span."""
        return self._span_stack[-1] if self._span_stack else None

    def record_llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        latency_ms: float,
    ) -> None:
        """Record metrics for an LLM call.

        Args:
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count
            cost: Cost in dollars
            latency_ms: Latency in milliseconds
        """
        span = self.current_span()
        if span:
            span.set_attribute("llm.model", model)
            span.set_attribute("llm.input_tokens", input_tokens)
            span.set_attribute("llm.output_tokens", output_tokens)
            span.token_count = input_tokens + output_tokens
            span.cost = cost
            span.set_attribute("llm.cost", cost)
            span.set_attribute("llm.latency_ms", latency_ms)

    def _save_trace(self, trace: Trace) -> None:
        """Save trace to disk."""
        trace_file = self.storage_dir / f"trace-{trace.trace_id}.json"
        with open(trace_file, "w") as f:
            json.dump(trace.to_dict(), f, indent=2)

        # Also append to session log
        session_file = self.storage_dir / f"session-{self.session_id}.jsonl"
        with open(session_file, "a") as f:
            f.write(json.dumps(trace.to_dict()) + "\n")

    def load_trace(self, trace_id: str) -> Optional[Trace]:
        """Load a trace from disk.

        Args:
            trace_id: Trace ID to load

        Returns:
            Trace if found
        """
        trace_file = self.storage_dir / f"trace-{trace_id}.json"
        if not trace_file.exists():
            return None

        with open(trace_file) as f:
            data = json.load(f)
        return Trace.from_dict(data)

    def get_session_traces(self) -> list[Trace]:
        """Get all traces for the current session."""
        session_file = self.storage_dir / f"session-{self.session_id}.jsonl"
        if not session_file.exists():
            return []

        traces = []
        with open(session_file) as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    traces.append(Trace.from_dict(data))
        return traces

    def get_summary(self) -> dict:
        """Get summary of tracing activity."""
        traces = self.get_session_traces()

        total_spans = sum(t.span_count for t in traces)
        total_errors = sum(t.error_count for t in traces)
        total_cost = sum(t.total_cost for t in traces)
        total_tokens = sum(t.total_tokens for t in traces)
        total_duration = sum(t.total_duration_ms or 0 for t in traces)

        return {
            "session_id": self.session_id,
            "trace_count": len(traces),
            "span_count": total_spans,
            "error_count": total_errors,
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "total_duration_ms": total_duration,
            "avg_trace_duration_ms": total_duration / len(traces) if traces else 0,
            "error_rate": total_errors / total_spans if total_spans > 0 else 0,
        }

    def export_to_otlp(self) -> list[dict]:
        """Export traces in OpenTelemetry format.

        Returns:
            List of traces in OTLP-compatible format
        """
        traces = self.get_session_traces()
        return [self._to_otlp_format(t) for t in traces]

    def _to_otlp_format(self, trace: Trace) -> dict:
        """Convert trace to OTLP format."""
        return {
            "resourceSpans": [{
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": self.service_name}},
                        {"key": "session.id", "value": {"stringValue": self.session_id}},
                    ]
                },
                "scopeSpans": [{
                    "scope": {"name": "multi-agent-orchestrator"},
                    "spans": [
                        {
                            "traceId": span.trace_id,
                            "spanId": span.span_id,
                            "parentSpanId": span.parent_span_id or "",
                            "name": span.name,
                            "kind": self._map_span_kind(span.kind),
                            "startTimeUnixNano": self._to_nanos(span.start_time),
                            "endTimeUnixNano": self._to_nanos(span.end_time) if span.end_time else 0,
                            "status": {"code": 1 if span.status == SpanStatus.OK else 2},
                            "attributes": [
                                {"key": k, "value": {"stringValue": str(v)}}
                                for k, v in span.attributes.items()
                            ],
                        }
                        for span in trace.spans
                    ]
                }]
            }]
        }

    def _map_span_kind(self, kind: SpanKind) -> int:
        """Map SpanKind to OTLP kind value."""
        mapping = {
            SpanKind.WORKFLOW: 1,  # INTERNAL
            SpanKind.PHASE: 1,
            SpanKind.AGENT: 3,     # CLIENT
            SpanKind.LLM_CALL: 3,
            SpanKind.TOOL: 1,
            SpanKind.VALIDATION: 1,
            SpanKind.INTERNAL: 1,
        }
        return mapping.get(kind, 1)

    def _to_nanos(self, iso_time: str) -> int:
        """Convert ISO timestamp to nanoseconds."""
        dt = datetime.fromisoformat(iso_time)
        return int(dt.timestamp() * 1_000_000_000)


# Global tracer instance
_tracer: Optional[Tracer] = None


def get_tracer(
    service_name: str = "multi-agent-orchestrator",
    storage_dir: Optional[str | Path] = None,
) -> Tracer:
    """Get or create the global tracer instance.

    Args:
        service_name: Service name for traces
        storage_dir: Storage directory (defaults to .workflow/traces)

    Returns:
        Tracer instance
    """
    global _tracer

    if _tracer is None:
        storage_dir = storage_dir or Path(".workflow/traces")
        _tracer = Tracer(service_name, storage_dir)

    return _tracer


def reset_tracer() -> None:
    """Reset the global tracer instance.

    Call this at workflow boundaries to prevent memory accumulation.
    Clears in-memory traces (disk traces are preserved).
    """
    global _tracer
    if _tracer is not None:
        _tracer.clear_traces()
    _tracer = None
