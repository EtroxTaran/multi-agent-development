"""Event emitter for writing workflow events to SurrealDB.

The EventEmitter writes events to the workflow_events table which
the dashboard backend subscribes to via live queries.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, Optional

from .types import EventPriority, EventType, WorkflowEvent

logger = logging.getLogger(__name__)


class EventEmitter:
    """Emits workflow events to SurrealDB.

    Events are written to the workflow_events table and can be subscribed
    to by the dashboard backend using live queries.

    Features:
    - Non-blocking event emission (failures don't stop workflow)
    - Batching for efficiency (optional)
    - Automatic cleanup of old events
    - Priority-based filtering
    """

    def __init__(
        self,
        project_name: str,
        batch_size: int = 10,
        flush_interval: float = 1.0,
        enabled: bool = True,
        min_priority: EventPriority = EventPriority.LOW,
    ):
        """Initialize event emitter.

        Args:
            project_name: Project name for event scoping
            batch_size: Number of events to batch before writing
            flush_interval: Max seconds between flushes
            enabled: Whether event emission is enabled
            min_priority: Minimum priority level to emit
        """
        self.project_name = project_name
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.enabled = enabled
        self.min_priority = min_priority

        self._batch: list[WorkflowEvent] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._callbacks: list[Callable[[WorkflowEvent], None]] = []

        # Statistics
        self._events_emitted = 0
        self._events_failed = 0

    def add_callback(self, callback: Callable[[WorkflowEvent], None]) -> None:
        """Add a callback to be called on each event.

        This allows the WebSocket progress callback to also receive events
        without going through the database.

        Args:
            callback: Function to call with each event
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[WorkflowEvent], None]) -> None:
        """Remove a previously added callback."""
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    async def emit(self, event: WorkflowEvent) -> None:
        """Emit a single event.

        The event is added to the batch and written when the batch
        is full or the flush interval expires.

        Args:
            event: Event to emit
        """
        if not self.enabled:
            return

        # Check priority filter
        priority_order = {
            EventPriority.HIGH: 0,
            EventPriority.MEDIUM: 1,
            EventPriority.LOW: 2,
        }
        if priority_order.get(event.priority, 2) > priority_order.get(self.min_priority, 2):
            return

        # Call callbacks immediately (synchronous)
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.debug(f"Event callback failed: {e}")

        # Add to batch
        async with self._lock:
            self._batch.append(event)

            # Flush if batch is full
            if len(self._batch) >= self.batch_size:
                await self._flush_batch()
            else:
                # Start flush timer if not running
                self._ensure_flush_timer()

    async def emit_now(self, event: WorkflowEvent) -> None:
        """Emit an event immediately without batching.

        Use for high-priority events that need instant delivery.

        Args:
            event: Event to emit
        """
        if not self.enabled:
            return

        # Call callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.debug(f"Event callback failed: {e}")

        # Write directly to DB
        await self._write_event(event)

    async def emit_type(
        self,
        event_type: EventType,
        data: Optional[dict[str, Any]] = None,
        node_name: Optional[str] = None,
        task_id: Optional[str] = None,
        phase: Optional[int] = None,
        priority: EventPriority = EventPriority.MEDIUM,
    ) -> None:
        """Emit an event by type with data.

        Convenience method for emitting events without creating WorkflowEvent manually.

        Args:
            event_type: Type of event
            data: Event data payload
            node_name: Node that generated the event
            task_id: Associated task ID
            phase: Current workflow phase
            priority: Event priority
        """
        event = WorkflowEvent(
            event_type=event_type,
            project_name=self.project_name,
            data=data or {},
            node_name=node_name,
            task_id=task_id,
            phase=phase,
            priority=priority,
        )
        await self.emit(event)

    async def flush(self) -> None:
        """Flush all pending events immediately."""
        async with self._lock:
            await self._flush_batch()

    async def close(self) -> None:
        """Close the emitter, flushing any remaining events."""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        await self.flush()

    def _ensure_flush_timer(self) -> None:
        """Ensure flush timer is running."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_timer())

    async def _flush_timer(self) -> None:
        """Timer that flushes the batch after interval."""
        try:
            await asyncio.sleep(self.flush_interval)
            async with self._lock:
                await self._flush_batch()
        except asyncio.CancelledError:
            pass

    async def _flush_batch(self) -> None:
        """Write all batched events to database.

        Must be called with self._lock held.
        """
        if not self._batch:
            return

        events = self._batch
        self._batch = []

        # Write events in parallel
        tasks = [self._write_event(event) for event in events]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _write_event(self, event: WorkflowEvent) -> None:
        """Write a single event to the database.

        Failures are logged but don't raise - events are non-critical.

        Args:
            event: Event to write
        """
        try:
            # Import here to avoid circular imports
            from orchestrator.db.connection import get_connection

            async with get_connection(self.project_name) as conn:
                await conn.create(
                    "workflow_events",
                    {
                        "event_type": event.event_type.value,
                        "event_data": event.data,
                        "node_name": event.node_name,
                        "task_id": event.task_id,
                        "phase": event.phase,
                        "priority": event.priority.value,
                        "correlation_id": event.correlation_id,
                        "created_at": event.timestamp,
                    },
                )

            self._events_emitted += 1
            logger.debug(f"Emitted event: {event.event_type.value}")

        except Exception as e:
            self._events_failed += 1
            logger.warning(f"Failed to emit event {event.event_type.value}: {e}")

    @property
    def stats(self) -> dict[str, int]:
        """Get emitter statistics."""
        return {
            "events_emitted": self._events_emitted,
            "events_failed": self._events_failed,
            "events_pending": len(self._batch),
        }


# Factory function for creating emitters


def create_event_emitter(
    project_name: str,
    enabled: bool = True,
) -> EventEmitter:
    """Create an event emitter for a project.

    Args:
        project_name: Project name
        enabled: Whether events should be emitted

    Returns:
        Configured EventEmitter
    """
    return EventEmitter(
        project_name=project_name,
        enabled=enabled,
        batch_size=10,
        flush_interval=1.0,
    )


async def cleanup_old_events(
    project_name: str,
    days: int = 7,
) -> int:
    """Clean up events older than specified days.

    Args:
        project_name: Project name
        days: Number of days to keep

    Returns:
        Number of events deleted
    """
    try:
        from orchestrator.db.connection import get_connection

        cutoff = datetime.now().isoformat()  # Would need proper date math

        async with get_connection(project_name) as conn:
            # Delete old events
            result = await conn.query(
                f"DELETE FROM workflow_events WHERE created_at < '{cutoff}' - {days}d"
            )
            return len(result) if result else 0

    except Exception as e:
        logger.warning(f"Failed to cleanup old events: {e}")
        return 0
