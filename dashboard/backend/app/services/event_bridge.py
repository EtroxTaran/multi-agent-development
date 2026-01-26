"""Event bridge service for real-time workflow event streaming.

Subscribes to SurrealDB live queries on the workflow_events table
and forwards events to connected WebSocket clients.
"""

import asyncio
import logging
import sys
from typing import Any, Optional

from ..config import get_settings
from ..websocket import get_connection_manager

logger = logging.getLogger(__name__)

# Add conductor root to path for orchestrator imports
settings = get_settings()
sys.path.insert(0, str(settings.conductor_root))


class EventBridge:
    """Bridge between SurrealDB workflow_events and WebSocket clients.

    This service:
    1. Subscribes to live queries on workflow_events for each active project
    2. Forwards events to WebSocket clients via ConnectionManager
    3. Handles reconnection and cleanup automatically
    """

    def __init__(
        self,
        reconnect_delay: float = 5.0,
        max_reconnect_attempts: int = 10,
    ):
        """Initialize event bridge.

        Args:
            reconnect_delay: Delay between reconnection attempts
            max_reconnect_attempts: Maximum reconnection attempts
        """
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts

        # Track active subscriptions by project
        self._subscriptions: dict[str, str] = {}  # project_name -> live_id
        self._tasks: dict[str, asyncio.Task] = {}  # project_name -> task
        self._lock = asyncio.Lock()
        self._running = False

        # Connection for live queries
        self._connections: dict[str, Any] = {}  # project_name -> connection

    async def start(self) -> None:
        """Start the event bridge.

        This should be called from the FastAPI lifespan handler.
        """
        if self._running:
            return

        self._running = True
        logger.info("Event bridge started")

    async def stop(self) -> None:
        """Stop the event bridge and cleanup subscriptions.

        This should be called from the FastAPI lifespan handler.
        """
        self._running = False

        async with self._lock:
            # Cancel all subscription tasks
            for project_name, task in list(self._tasks.items()):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Kill live queries
            for project_name, live_id in list(self._subscriptions.items()):
                await self._unsubscribe(project_name, live_id)

            self._tasks.clear()
            self._subscriptions.clear()
            self._connections.clear()

        logger.info("Event bridge stopped")

    async def subscribe_project(self, project_name: str) -> bool:
        """Subscribe to events for a project.

        Args:
            project_name: Project name to subscribe to

        Returns:
            True if subscription successful
        """
        async with self._lock:
            if project_name in self._subscriptions:
                logger.debug(f"Already subscribed to {project_name}")
                return True

            try:
                # Start subscription task
                task = asyncio.create_task(
                    self._subscription_loop(project_name),
                    name=f"event_bridge_{project_name}",
                )
                self._tasks[project_name] = task
                logger.info(f"Started event subscription for {project_name}")
                return True

            except Exception as e:
                logger.error(f"Failed to subscribe to {project_name}: {e}")
                return False

    async def unsubscribe_project(self, project_name: str) -> None:
        """Unsubscribe from events for a project.

        Args:
            project_name: Project name to unsubscribe from
        """
        async with self._lock:
            # Cancel task
            if project_name in self._tasks:
                self._tasks[project_name].cancel()
                try:
                    await self._tasks[project_name]
                except asyncio.CancelledError:
                    pass
                del self._tasks[project_name]

            # Kill live query
            if project_name in self._subscriptions:
                await self._unsubscribe(project_name, self._subscriptions[project_name])
                del self._subscriptions[project_name]

            # Close connection
            if project_name in self._connections:
                try:
                    await self._connections[project_name].disconnect()
                except Exception:
                    pass
                del self._connections[project_name]

            logger.info(f"Unsubscribed from {project_name}")

    async def _subscription_loop(self, project_name: str) -> None:
        """Main subscription loop for a project.

        Handles connection, subscription, and reconnection.

        Args:
            project_name: Project name
        """
        reconnect_attempts = 0

        while self._running and reconnect_attempts < self.max_reconnect_attempts:
            try:
                await self._subscribe_to_events(project_name)
                reconnect_attempts = 0  # Reset on successful subscription

            except asyncio.CancelledError:
                raise

            except Exception as e:
                reconnect_attempts += 1
                logger.warning(
                    f"Event subscription error for {project_name} "
                    f"(attempt {reconnect_attempts}/{self.max_reconnect_attempts}): {e}"
                )

                if reconnect_attempts < self.max_reconnect_attempts:
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    logger.error(f"Max reconnection attempts reached for {project_name}")
                    break

    async def _subscribe_to_events(self, project_name: str) -> None:
        """Subscribe to workflow_events for a project.

        Args:
            project_name: Project name
        """
        try:
            from orchestrator.db.connection import get_connection

            # Get a dedicated connection for this subscription
            async with get_connection(project_name) as conn:
                self._connections[project_name] = conn

                # Set up live query callback
                def on_event(data: dict[str, Any]) -> None:
                    # Schedule event forwarding in the event loop
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._forward_event(project_name, data))
                    except RuntimeError:
                        pass

                # Start live query
                live_id = await conn.live("workflow_events", on_event)
                self._subscriptions[project_name] = live_id

                logger.info(f"Live query started for {project_name}: {live_id}")

                # Keep connection alive
                while self._running and project_name in self._subscriptions:
                    await asyncio.sleep(1)

        except ImportError:
            logger.error("Orchestrator DB module not available")
            raise

    async def _unsubscribe(self, project_name: str, live_id: str) -> None:
        """Unsubscribe from a live query.

        Args:
            project_name: Project name
            live_id: Live query ID
        """
        if project_name in self._connections:
            try:
                await self._connections[project_name].kill(live_id)
            except Exception as e:
                logger.debug(f"Error killing live query: {e}")

    async def _forward_event(self, project_name: str, data: dict[str, Any]) -> None:
        """Forward an event to WebSocket clients.

        Args:
            project_name: Project name
            data: Event data from live query
        """
        try:
            # Extract event details
            # Live query data format: {"action": "CREATE/UPDATE/DELETE", "result": {...}}
            action = data.get("action", "CREATE")
            result = data.get("result", data)

            # Extract event type and data
            event_type = result.get("event_type", "unknown")
            event_data = result.get("event_data", {})

            # Include metadata
            payload = {
                "event_type": event_type,
                "node_name": result.get("node_name"),
                "task_id": result.get("task_id"),
                "phase": result.get("phase"),
                "priority": result.get("priority"),
                "created_at": result.get("created_at"),
                **event_data,
            }

            # Forward to WebSocket clients
            manager = get_connection_manager()
            await manager.broadcast_to_project(
                project_name,
                event_type,
                payload,
            )

            logger.debug(f"Forwarded event {event_type} for {project_name}")

        except Exception as e:
            logger.error(f"Failed to forward event: {e}")

    @property
    def active_subscriptions(self) -> list[str]:
        """Get list of active subscription project names."""
        return list(self._subscriptions.keys())

    def is_subscribed(self, project_name: str) -> bool:
        """Check if subscribed to a project."""
        return project_name in self._subscriptions


# Global event bridge instance
_bridge: Optional[EventBridge] = None


def get_event_bridge() -> EventBridge:
    """Get the global event bridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = EventBridge()
    return _bridge


async def start_event_bridge() -> None:
    """Start the global event bridge."""
    bridge = get_event_bridge()
    await bridge.start()


async def stop_event_bridge() -> None:
    """Stop the global event bridge."""
    bridge = get_event_bridge()
    await bridge.stop()
