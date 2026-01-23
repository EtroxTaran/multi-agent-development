"""WebSocket connection manager for real-time events."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time event streaming.

    Supports:
    - Multiple connections per project
    - Broadcasting events to project subscribers
    - Heartbeat/ping for connection health
    - Automatic cleanup of dead connections
    """

    def __init__(self, heartbeat_interval: int = 30):
        """Initialize connection manager.

        Args:
            heartbeat_interval: Interval between heartbeat pings in seconds
        """
        self.heartbeat_interval = heartbeat_interval
        # Map of project_name -> list of websockets
        self._connections: dict[str, list[WebSocket]] = {}
        # Global connections (not project-specific)
        self._global_connections: list[WebSocket] = []
        # Lock for thread safety
        self._lock = asyncio.Lock()
        # Heartbeat task
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def connect(
        self,
        websocket: WebSocket,
        project_name: Optional[str] = None,
    ) -> None:
        """Accept a WebSocket connection.

        Args:
            websocket: WebSocket connection
            project_name: Optional project name to subscribe to
        """
        await websocket.accept()

        async with self._lock:
            if project_name:
                if project_name not in self._connections:
                    self._connections[project_name] = []
                self._connections[project_name].append(websocket)
                logger.info(f"WebSocket connected for project: {project_name}")
            else:
                self._global_connections.append(websocket)
                logger.info("WebSocket connected (global)")

        # Start heartbeat if not running
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def disconnect(
        self,
        websocket: WebSocket,
        project_name: Optional[str] = None,
    ) -> None:
        """Remove a WebSocket connection.

        Args:
            websocket: WebSocket connection
            project_name: Optional project name
        """
        async with self._lock:
            if project_name and project_name in self._connections:
                try:
                    self._connections[project_name].remove(websocket)
                    logger.info(f"WebSocket disconnected for project: {project_name}")
                except ValueError:
                    pass
                # Clean up empty project lists
                if not self._connections[project_name]:
                    del self._connections[project_name]
            else:
                try:
                    self._global_connections.remove(websocket)
                    logger.info("WebSocket disconnected (global)")
                except ValueError:
                    pass

    async def broadcast_to_project(
        self,
        project_name: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Broadcast an event to all connections for a project.

        Args:
            project_name: Project name
            event_type: Event type (action, state_change, escalation, etc.)
            data: Event data
        """
        message = json.dumps(
            {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }
        )

        async with self._lock:
            connections = self._connections.get(project_name, []).copy()

        if not connections:
            return

        # Send to all connections in parallel
        results = await asyncio.gather(*[self._send_safe(ws, message) for ws in connections])

        dead_connections = []
        for websocket, success in zip(connections, results):
            if not success:
                dead_connections.append(websocket)

        # Clean up dead connections
        for websocket in dead_connections:
            await self.disconnect(websocket, project_name)

    async def broadcast_global(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Broadcast an event to all global connections.

        Args:
            event_type: Event type
            data: Event data
        """
        message = json.dumps(
            {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }
        )

        async with self._lock:
            connections = self._global_connections.copy()

        if not connections:
            return

        # Send to all connections in parallel
        results = await asyncio.gather(*[self._send_safe(ws, message) for ws in connections])

        dead_connections = []
        for websocket, success in zip(connections, results):
            if not success:
                dead_connections.append(websocket)

        # Clean up dead connections
        for websocket in dead_connections:
            await self.disconnect(websocket)

    async def send_to_connection(
        self,
        websocket: WebSocket,
        event_type: str,
        data: dict[str, Any],
    ) -> bool:
        """Send an event to a specific connection.

        Args:
            websocket: WebSocket connection
            event_type: Event type
            data: Event data

        Returns:
            True if sent successfully
        """
        message = json.dumps(
            {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }
        )
        return await self._send_safe(websocket, message)

    async def _send_safe(self, websocket: WebSocket, message: str) -> bool:
        """Safely send a message, handling disconnection.

        Args:
            websocket: WebSocket connection
            message: Message to send

        Returns:
            True if sent successfully
        """
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(message)
                return True
        except Exception as e:
            logger.debug(f"Failed to send WebSocket message: {e}")
        return False

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat pings to all connections."""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                async with self._lock:
                    all_connections = list(self._global_connections)
                    for connections in self._connections.values():
                        all_connections.extend(connections)

                if not all_connections:
                    # No connections, stop heartbeat
                    break

                message = json.dumps(
                    {
                        "type": "heartbeat",
                        "data": {},
                        "timestamp": datetime.now().isoformat(),
                    }
                )

                for websocket in all_connections:
                    await self._send_safe(websocket, message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    @property
    def connection_count(self) -> int:
        """Get total number of active connections."""
        count = len(self._global_connections)
        for connections in self._connections.values():
            count += len(connections)
        return count

    def get_project_connection_count(self, project_name: str) -> int:
        """Get number of connections for a specific project."""
        return len(self._connections.get(project_name, []))


# Global connection manager instance
_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
