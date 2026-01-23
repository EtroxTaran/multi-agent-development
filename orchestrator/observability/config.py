"""Configuration for observability features.

All features are opt-in and configured via environment variables.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Singleton config instance
_config: Optional["ObservabilityConfig"] = None


@dataclass
class PrometheusConfig:
    """Prometheus metrics configuration."""

    enabled: bool = False
    port: int = 9090
    host: str = "0.0.0.0"
    namespace: str = "orchestrator"

    @classmethod
    def from_env(cls) -> "PrometheusConfig":
        """Create config from environment variables."""
        return cls(
            enabled=os.environ.get("OBSERVABILITY_PROMETHEUS_ENABLED", "").lower() == "true",
            port=int(os.environ.get("OBSERVABILITY_PROMETHEUS_PORT", "9090")),
            host=os.environ.get("OBSERVABILITY_PROMETHEUS_HOST", "0.0.0.0"),
            namespace=os.environ.get("OBSERVABILITY_PROMETHEUS_NAMESPACE", "orchestrator"),
        )


@dataclass
class TracingConfig:
    """OpenTelemetry tracing configuration."""

    enabled: bool = False
    endpoint: str = "http://localhost:4317"
    service_name: str = "orchestrator"
    insecure: bool = True
    batch_export: bool = True
    export_timeout_millis: int = 30000

    @classmethod
    def from_env(cls) -> "TracingConfig":
        """Create config from environment variables."""
        return cls(
            enabled=os.environ.get("OBSERVABILITY_OTLP_ENABLED", "").lower() == "true",
            endpoint=os.environ.get("OBSERVABILITY_OTLP_ENDPOINT", "http://localhost:4317"),
            service_name=os.environ.get("OBSERVABILITY_SERVICE_NAME", "orchestrator"),
            insecure=os.environ.get("OBSERVABILITY_OTLP_INSECURE", "true").lower() == "true",
            batch_export=os.environ.get("OBSERVABILITY_OTLP_BATCH", "true").lower() == "true",
            export_timeout_millis=int(os.environ.get("OBSERVABILITY_OTLP_TIMEOUT", "30000")),
        )


@dataclass
class WebhooksConfig:
    """Webhooks configuration."""

    enabled: bool = False
    secret: str = ""
    timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    endpoints: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "WebhooksConfig":
        """Create config from environment variables."""
        endpoints_str = os.environ.get("OBSERVABILITY_WEBHOOK_ENDPOINTS", "")
        endpoints = [e.strip() for e in endpoints_str.split(",") if e.strip()]

        return cls(
            enabled=os.environ.get("OBSERVABILITY_WEBHOOKS_ENABLED", "").lower() == "true",
            secret=os.environ.get("OBSERVABILITY_WEBHOOK_SECRET", ""),
            timeout_seconds=int(os.environ.get("OBSERVABILITY_WEBHOOK_TIMEOUT", "30")),
            retry_attempts=int(os.environ.get("OBSERVABILITY_WEBHOOK_RETRIES", "3")),
            retry_delay_seconds=float(os.environ.get("OBSERVABILITY_WEBHOOK_RETRY_DELAY", "1.0")),
            endpoints=endpoints,
        )


@dataclass
class ObservabilityConfig:
    """Unified observability configuration."""

    prometheus: PrometheusConfig = field(default_factory=PrometheusConfig)
    tracing: TracingConfig = field(default_factory=TracingConfig)
    webhooks: WebhooksConfig = field(default_factory=WebhooksConfig)

    @classmethod
    def from_env(cls) -> "ObservabilityConfig":
        """Create config from environment variables."""
        return cls(
            prometheus=PrometheusConfig.from_env(),
            tracing=TracingConfig.from_env(),
            webhooks=WebhooksConfig.from_env(),
        )

    @property
    def any_enabled(self) -> bool:
        """Check if any observability feature is enabled."""
        return (
            self.prometheus.enabled
            or self.tracing.enabled
            or self.webhooks.enabled
        )


def get_config() -> ObservabilityConfig:
    """Get the observability configuration singleton.

    Returns:
        ObservabilityConfig instance
    """
    global _config
    if _config is None:
        _config = ObservabilityConfig.from_env()
        if _config.any_enabled:
            logger.info(
                f"Observability enabled: "
                f"prometheus={_config.prometheus.enabled}, "
                f"tracing={_config.tracing.enabled}, "
                f"webhooks={_config.webhooks.enabled}"
            )
    return _config


def is_prometheus_enabled() -> bool:
    """Check if Prometheus metrics are enabled."""
    return get_config().prometheus.enabled


def is_tracing_enabled() -> bool:
    """Check if OpenTelemetry tracing is enabled."""
    return get_config().tracing.enabled


def is_webhooks_enabled() -> bool:
    """Check if webhooks are enabled."""
    return get_config().webhooks.enabled
