"""Observability package for the orchestrator.

Provides opt-in observability features:
- Prometheus metrics for monitoring
- OpenTelemetry tracing for distributed tracing
- Webhooks for external integrations

All features are disabled by default and configured via environment variables.

Usage:
    from orchestrator.observability import (
        get_observability_manager,
        record_workflow_event,
        record_agent_invocation,
    )

    # Get the singleton manager
    manager = get_observability_manager()

    # Record events
    manager.record_workflow_started("my-project", "wf-123")
    manager.record_agent_invocation("claude", "T1", success=True, cost_usd=0.05)

Environment Variables:
    OBSERVABILITY_PROMETHEUS_ENABLED=true
    OBSERVABILITY_PROMETHEUS_PORT=9090
    OBSERVABILITY_OTLP_ENABLED=true
    OBSERVABILITY_OTLP_ENDPOINT=http://localhost:4317
    OBSERVABILITY_WEBHOOKS_ENABLED=true
    OBSERVABILITY_WEBHOOK_SECRET=your-secret-key
"""

from .config import (
    ObservabilityConfig,
    get_config,
    is_prometheus_enabled,
    is_tracing_enabled,
    is_webhooks_enabled,
)
from .manager import ObservabilityManager, get_observability_manager

__all__ = [
    # Config
    "ObservabilityConfig",
    "get_config",
    "is_prometheus_enabled",
    "is_tracing_enabled",
    "is_webhooks_enabled",
    # Manager
    "ObservabilityManager",
    "get_observability_manager",
]
