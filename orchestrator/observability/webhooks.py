"""Webhook dispatcher for external integrations.

Sends workflow events to configured webhook endpoints with
HMAC signature verification support.

Webhook Events:
    workflow.started - Workflow started
    workflow.completed - Workflow completed successfully
    workflow.failed - Workflow failed
    phase.started - Phase started
    phase.completed - Phase completed
    task.started - Task implementation started
    task.completed - Task implementation completed
    task.failed - Task implementation failed
    escalation.required - Human escalation needed
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from .config import get_config

logger = logging.getLogger(__name__)

# Optional import - graceful degradation if aiohttp not installed
try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logger.debug("aiohttp not installed, webhooks will use sync requests")

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class WebhookEventType(str, Enum):
    """Types of webhook events."""

    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    PHASE_STARTED = "phase.started"
    PHASE_COMPLETED = "phase.completed"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    ESCALATION_REQUIRED = "escalation.required"


@dataclass
class WebhookPayload:
    """Webhook event payload."""

    event_type: WebhookEventType
    project: str
    workflow_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Payload as dict
        """
        return {
            "event_type": self.event_type.value,
            "project": self.project,
            "workflow_id": self.workflow_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }

    def to_json(self) -> str:
        """Convert to JSON string.

        Returns:
            JSON string
        """
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass
class WebhookDeliveryResult:
    """Result of a webhook delivery attempt."""

    endpoint: str
    success: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    attempt: int = 1
    duration_ms: int = 0


class WebhookDispatcher:
    """Dispatcher for webhook events.

    Handles sending events to configured endpoints with:
    - HMAC signature verification
    - Retry logic with exponential backoff
    - Async and sync delivery modes
    """

    def __init__(self):
        """Initialize the webhook dispatcher."""
        self.config = get_config().webhooks
        self._session: Optional[Any] = None

    def _compute_signature(self, payload: str) -> str:
        """Compute HMAC-SHA256 signature for a payload.

        Args:
            payload: JSON payload string

        Returns:
            Hex-encoded signature
        """
        if not self.config.secret:
            return ""

        signature = hmac.new(
            self.config.secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        return f"sha256={signature}"

    def _get_headers(self, payload: str) -> dict[str, str]:
        """Get headers for webhook request.

        Args:
            payload: JSON payload string

        Returns:
            Headers dict
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Conductor-Orchestrator/1.0",
        }

        signature = self._compute_signature(payload)
        if signature:
            headers["X-Webhook-Signature"] = signature

        return headers

    async def _deliver_async(
        self,
        endpoint: str,
        payload: WebhookPayload,
    ) -> WebhookDeliveryResult:
        """Deliver webhook asynchronously using aiohttp.

        Args:
            endpoint: Webhook endpoint URL
            payload: Event payload

        Returns:
            Delivery result
        """
        if not AIOHTTP_AVAILABLE:
            return await asyncio.to_thread(self._deliver_sync, endpoint, payload)

        json_payload = payload.to_json()
        headers = self._get_headers(json_payload)

        for attempt in range(1, self.config.retry_attempts + 1):
            start_time = time.time()

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        endpoint,
                        data=json_payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
                    ) as response:
                        duration_ms = int((time.time() - start_time) * 1000)

                        if response.status < 400:
                            return WebhookDeliveryResult(
                                endpoint=endpoint,
                                success=True,
                                status_code=response.status,
                                attempt=attempt,
                                duration_ms=duration_ms,
                            )
                        else:
                            error = f"HTTP {response.status}"
                            if attempt < self.config.retry_attempts:
                                await asyncio.sleep(self.config.retry_delay_seconds * attempt)
                                continue

                            return WebhookDeliveryResult(
                                endpoint=endpoint,
                                success=False,
                                status_code=response.status,
                                error=error,
                                attempt=attempt,
                                duration_ms=duration_ms,
                            )

            except asyncio.TimeoutError:
                duration_ms = int((time.time() - start_time) * 1000)
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(self.config.retry_delay_seconds * attempt)
                    continue

                return WebhookDeliveryResult(
                    endpoint=endpoint,
                    success=False,
                    error="Timeout",
                    attempt=attempt,
                    duration_ms=duration_ms,
                )

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(self.config.retry_delay_seconds * attempt)
                    continue

                return WebhookDeliveryResult(
                    endpoint=endpoint,
                    success=False,
                    error=str(e),
                    attempt=attempt,
                    duration_ms=duration_ms,
                )

        # Should not reach here
        return WebhookDeliveryResult(
            endpoint=endpoint,
            success=False,
            error="Max retries exceeded",
            attempt=self.config.retry_attempts,
        )

    def _deliver_sync(
        self,
        endpoint: str,
        payload: WebhookPayload,
    ) -> WebhookDeliveryResult:
        """Deliver webhook synchronously using requests.

        Args:
            endpoint: Webhook endpoint URL
            payload: Event payload

        Returns:
            Delivery result
        """
        if not REQUESTS_AVAILABLE:
            return WebhookDeliveryResult(
                endpoint=endpoint,
                success=False,
                error="No HTTP client available (install aiohttp or requests)",
            )

        json_payload = payload.to_json()
        headers = self._get_headers(json_payload)

        for attempt in range(1, self.config.retry_attempts + 1):
            start_time = time.time()

            try:
                response = requests.post(
                    endpoint,
                    data=json_payload,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )
                duration_ms = int((time.time() - start_time) * 1000)

                if response.status_code < 400:
                    return WebhookDeliveryResult(
                        endpoint=endpoint,
                        success=True,
                        status_code=response.status_code,
                        attempt=attempt,
                        duration_ms=duration_ms,
                    )
                else:
                    if attempt < self.config.retry_attempts:
                        time.sleep(self.config.retry_delay_seconds * attempt)
                        continue

                    return WebhookDeliveryResult(
                        endpoint=endpoint,
                        success=False,
                        status_code=response.status_code,
                        error=f"HTTP {response.status_code}",
                        attempt=attempt,
                        duration_ms=duration_ms,
                    )

            except requests.Timeout:
                duration_ms = int((time.time() - start_time) * 1000)
                if attempt < self.config.retry_attempts:
                    time.sleep(self.config.retry_delay_seconds * attempt)
                    continue

                return WebhookDeliveryResult(
                    endpoint=endpoint,
                    success=False,
                    error="Timeout",
                    attempt=attempt,
                    duration_ms=duration_ms,
                )

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                if attempt < self.config.retry_attempts:
                    time.sleep(self.config.retry_delay_seconds * attempt)
                    continue

                return WebhookDeliveryResult(
                    endpoint=endpoint,
                    success=False,
                    error=str(e),
                    attempt=attempt,
                    duration_ms=duration_ms,
                )

        return WebhookDeliveryResult(
            endpoint=endpoint,
            success=False,
            error="Max retries exceeded",
            attempt=self.config.retry_attempts,
        )

    async def dispatch(
        self,
        event_type: WebhookEventType,
        project: str,
        workflow_id: str,
        data: Optional[dict[str, Any]] = None,
    ) -> list[WebhookDeliveryResult]:
        """Dispatch a webhook event to all configured endpoints.

        Args:
            event_type: Type of event
            project: Project name
            workflow_id: Workflow ID
            data: Optional event data

        Returns:
            List of delivery results
        """
        if not self.config.enabled or not self.config.endpoints:
            return []

        payload = WebhookPayload(
            event_type=event_type,
            project=project,
            workflow_id=workflow_id,
            data=data or {},
        )

        # Deliver to all endpoints concurrently
        tasks = [self._deliver_async(endpoint, payload) for endpoint in self.config.endpoints]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(
                    WebhookDeliveryResult(
                        endpoint=self.config.endpoints[i],
                        success=False,
                        error=str(result),
                    )
                )
            else:
                final_results.append(result)

        # Log delivery results
        for result in final_results:
            if result.success:
                logger.debug(
                    f"Webhook delivered to {result.endpoint} "
                    f"(status={result.status_code}, ms={result.duration_ms})"
                )
            else:
                logger.warning(f"Webhook delivery failed to {result.endpoint}: {result.error}")

        return final_results

    def dispatch_sync(
        self,
        event_type: WebhookEventType,
        project: str,
        workflow_id: str,
        data: Optional[dict[str, Any]] = None,
    ) -> list[WebhookDeliveryResult]:
        """Dispatch a webhook event synchronously.

        Args:
            event_type: Type of event
            project: Project name
            workflow_id: Workflow ID
            data: Optional event data

        Returns:
            List of delivery results
        """
        if not self.config.enabled or not self.config.endpoints:
            return []

        payload = WebhookPayload(
            event_type=event_type,
            project=project,
            workflow_id=workflow_id,
            data=data or {},
        )

        results = []
        for endpoint in self.config.endpoints:
            result = self._deliver_sync(endpoint, payload)
            results.append(result)

        return results


# Singleton dispatcher
_dispatcher: Optional[WebhookDispatcher] = None


def get_webhook_dispatcher() -> WebhookDispatcher:
    """Get the webhook dispatcher singleton.

    Returns:
        WebhookDispatcher instance
    """
    global _dispatcher

    if _dispatcher is None:
        _dispatcher = WebhookDispatcher()
    return _dispatcher
