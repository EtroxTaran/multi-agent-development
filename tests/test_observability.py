"""Tests for the observability package."""

import asyncio
import hashlib
import hmac
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.observability.config import (
    ObservabilityConfig,
    PrometheusConfig,
    TracingConfig,
    WebhooksConfig,
    get_config,
    is_prometheus_enabled,
    is_tracing_enabled,
    is_webhooks_enabled,
)
from orchestrator.observability.webhooks import (
    WebhookPayload,
    WebhookEventType,
    WebhookDispatcher,
    WebhookDeliveryResult,
)
from orchestrator.observability.manager import (
    ObservabilityManager,
    get_observability_manager,
)


class TestPrometheusConfig:
    """Tests for PrometheusConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PrometheusConfig()
        assert config.enabled is False
        assert config.port == 9090
        assert config.host == "0.0.0.0"
        assert config.namespace == "orchestrator"

    def test_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("OBSERVABILITY_PROMETHEUS_ENABLED", "true")
        monkeypatch.setenv("OBSERVABILITY_PROMETHEUS_PORT", "9091")
        monkeypatch.setenv("OBSERVABILITY_PROMETHEUS_HOST", "127.0.0.1")
        monkeypatch.setenv("OBSERVABILITY_PROMETHEUS_NAMESPACE", "myapp")

        config = PrometheusConfig.from_env()
        assert config.enabled is True
        assert config.port == 9091
        assert config.host == "127.0.0.1"
        assert config.namespace == "myapp"


class TestTracingConfig:
    """Tests for TracingConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TracingConfig()
        assert config.enabled is False
        assert config.endpoint == "http://localhost:4317"
        assert config.service_name == "orchestrator"

    def test_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("OBSERVABILITY_OTLP_ENABLED", "true")
        monkeypatch.setenv("OBSERVABILITY_OTLP_ENDPOINT", "http://jaeger:4317")
        monkeypatch.setenv("OBSERVABILITY_SERVICE_NAME", "my-service")

        config = TracingConfig.from_env()
        assert config.enabled is True
        assert config.endpoint == "http://jaeger:4317"
        assert config.service_name == "my-service"


class TestWebhooksConfig:
    """Tests for WebhooksConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = WebhooksConfig()
        assert config.enabled is False
        assert config.secret == ""
        assert config.timeout_seconds == 30
        assert config.endpoints == []

    def test_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("OBSERVABILITY_WEBHOOKS_ENABLED", "true")
        monkeypatch.setenv("OBSERVABILITY_WEBHOOK_SECRET", "mysecret")
        monkeypatch.setenv("OBSERVABILITY_WEBHOOK_ENDPOINTS", "http://a.com/hook,http://b.com/hook")

        config = WebhooksConfig.from_env()
        assert config.enabled is True
        assert config.secret == "mysecret"
        assert len(config.endpoints) == 2
        assert "http://a.com/hook" in config.endpoints
        assert "http://b.com/hook" in config.endpoints


class TestObservabilityConfig:
    """Tests for ObservabilityConfig."""

    def test_any_enabled_false(self):
        """Test any_enabled when all disabled."""
        config = ObservabilityConfig()
        assert config.any_enabled is False

    def test_any_enabled_prometheus(self):
        """Test any_enabled when prometheus enabled."""
        config = ObservabilityConfig(
            prometheus=PrometheusConfig(enabled=True),
        )
        assert config.any_enabled is True

    def test_any_enabled_tracing(self):
        """Test any_enabled when tracing enabled."""
        config = ObservabilityConfig(
            tracing=TracingConfig(enabled=True),
        )
        assert config.any_enabled is True

    def test_any_enabled_webhooks(self):
        """Test any_enabled when webhooks enabled."""
        config = ObservabilityConfig(
            webhooks=WebhooksConfig(enabled=True),
        )
        assert config.any_enabled is True


class TestWebhookPayload:
    """Tests for WebhookPayload."""

    def test_to_dict(self):
        """Test converting payload to dict."""
        payload = WebhookPayload(
            event_type=WebhookEventType.WORKFLOW_STARTED,
            project="my-project",
            workflow_id="wf-123",
            data={"key": "value"},
        )

        d = payload.to_dict()
        assert d["event_type"] == "workflow.started"
        assert d["project"] == "my-project"
        assert d["workflow_id"] == "wf-123"
        assert d["data"] == {"key": "value"}
        assert "timestamp" in d

    def test_to_json(self):
        """Test converting payload to JSON."""
        payload = WebhookPayload(
            event_type=WebhookEventType.TASK_COMPLETED,
            project="my-project",
            workflow_id="wf-123",
            timestamp="2026-01-23T12:00:00Z",
        )

        json_str = payload.to_json()
        parsed = json.loads(json_str)
        assert parsed["event_type"] == "task.completed"


class TestWebhookDispatcher:
    """Tests for WebhookDispatcher."""

    def test_compute_signature(self):
        """Test HMAC signature computation."""
        dispatcher = WebhookDispatcher()
        dispatcher.config.secret = "test-secret"

        payload = '{"event_type": "test"}'
        signature = dispatcher._compute_signature(payload)

        # Verify signature format
        assert signature.startswith("sha256=")

        # Verify signature is correct
        expected = hmac.new(
            b"test-secret",
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert signature == f"sha256={expected}"

    def test_compute_signature_no_secret(self):
        """Test signature with no secret returns empty string."""
        dispatcher = WebhookDispatcher()
        dispatcher.config.secret = ""

        signature = dispatcher._compute_signature('{"event": "test"}')
        assert signature == ""

    def test_get_headers(self):
        """Test header generation."""
        dispatcher = WebhookDispatcher()
        dispatcher.config.secret = "my-secret"

        headers = dispatcher._get_headers('{"event": "test"}')

        assert headers["Content-Type"] == "application/json"
        assert headers["User-Agent"] == "Conductor-Orchestrator/1.0"
        assert "X-Webhook-Signature" in headers

    @pytest.mark.asyncio
    async def test_dispatch_no_endpoints(self):
        """Test dispatch with no endpoints returns empty list."""
        dispatcher = WebhookDispatcher()
        dispatcher.config.enabled = True
        dispatcher.config.endpoints = []

        results = await dispatcher.dispatch(
            WebhookEventType.WORKFLOW_STARTED,
            "project",
            "wf-123",
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_dispatch_disabled(self):
        """Test dispatch when disabled returns empty list."""
        dispatcher = WebhookDispatcher()
        dispatcher.config.enabled = False
        dispatcher.config.endpoints = ["http://example.com/hook"]

        results = await dispatcher.dispatch(
            WebhookEventType.WORKFLOW_STARTED,
            "project",
            "wf-123",
        )
        assert results == []


class TestWebhookEventType:
    """Tests for WebhookEventType enum."""

    def test_event_type_values(self):
        """Test event type string values."""
        assert WebhookEventType.WORKFLOW_STARTED.value == "workflow.started"
        assert WebhookEventType.WORKFLOW_COMPLETED.value == "workflow.completed"
        assert WebhookEventType.WORKFLOW_FAILED.value == "workflow.failed"
        assert WebhookEventType.PHASE_STARTED.value == "phase.started"
        assert WebhookEventType.PHASE_COMPLETED.value == "phase.completed"
        assert WebhookEventType.TASK_STARTED.value == "task.started"
        assert WebhookEventType.TASK_COMPLETED.value == "task.completed"
        assert WebhookEventType.TASK_FAILED.value == "task.failed"
        assert WebhookEventType.ESCALATION_REQUIRED.value == "escalation.required"


class TestWebhookDeliveryResult:
    """Tests for WebhookDeliveryResult."""

    def test_success_result(self):
        """Test successful delivery result."""
        result = WebhookDeliveryResult(
            endpoint="http://example.com",
            success=True,
            status_code=200,
            duration_ms=50,
        )
        assert result.success is True
        assert result.status_code == 200
        assert result.error is None

    def test_failure_result(self):
        """Test failed delivery result."""
        result = WebhookDeliveryResult(
            endpoint="http://example.com",
            success=False,
            error="Connection timeout",
            attempt=3,
        )
        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.attempt == 3


class TestObservabilityManager:
    """Tests for ObservabilityManager."""

    def test_initialization(self):
        """Test manager initialization."""
        manager = ObservabilityManager()
        assert manager._initialized is False

    def test_record_workflow_started_no_metrics(self):
        """Test recording workflow start without metrics enabled."""
        manager = ObservabilityManager()
        # Should not raise
        manager.record_workflow_started("project", "wf-123")

    def test_record_agent_invocation_no_metrics(self):
        """Test recording agent invocation without metrics enabled."""
        manager = ObservabilityManager()
        # Should not raise
        manager.record_agent_invocation(
            agent="claude",
            task_id="T1",
            success=True,
            cost_usd=0.05,
        )

    def test_phase_context_no_tracing(self):
        """Test phase context without tracing enabled."""
        manager = ObservabilityManager()

        with manager.phase_context("planning", "project", "wf-123"):
            pass  # Should not raise


class TestConfigHelpers:
    """Tests for config helper functions."""

    def test_is_prometheus_enabled_default(self, monkeypatch):
        """Test prometheus disabled by default."""
        # Clear env vars
        monkeypatch.delenv("OBSERVABILITY_PROMETHEUS_ENABLED", raising=False)

        # Force config reload
        import orchestrator.observability.config as config_module
        config_module._config = None

        assert is_prometheus_enabled() is False

    def test_is_tracing_enabled_default(self, monkeypatch):
        """Test tracing disabled by default."""
        monkeypatch.delenv("OBSERVABILITY_OTLP_ENABLED", raising=False)

        import orchestrator.observability.config as config_module
        config_module._config = None

        assert is_tracing_enabled() is False

    def test_is_webhooks_enabled_default(self, monkeypatch):
        """Test webhooks disabled by default."""
        monkeypatch.delenv("OBSERVABILITY_WEBHOOKS_ENABLED", raising=False)

        import orchestrator.observability.config as config_module
        config_module._config = None

        assert is_webhooks_enabled() is False
