"""Event streaming service.

Provides real-time event streaming via WebSocket and optional SurrealDB live queries.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import get_settings
from ..websocket import get_connection_manager

logger = logging.getLogger(__name__)


class EventService:
    """Service for real-time event streaming.

    Supports:
    - File-based event watching (coordination.log)
    - SurrealDB live queries (when enabled)
    - WebSocket broadcast
    """

    def __init__(self, project_dir: Path):
        """Initialize event service.

        Args:
            project_dir: Project directory
        """
        self.project_dir = project_dir
        self.project_name = project_dir.name
        self.workflow_dir = project_dir / ".workflow"
        self._stop_event = asyncio.Event()

    async def start_watching(self) -> None:
        """Start watching for events."""
        self._stop_event.clear()

        # Start file watcher
        asyncio.create_task(self._watch_coordination_log())

        # Start SurrealDB live queries if enabled
        settings = get_settings()
        if settings.use_surrealdb:
            asyncio.create_task(self._setup_live_queries())

    async def stop_watching(self) -> None:
        """Stop watching for events."""
        self._stop_event.set()

    async def _watch_coordination_log(self) -> None:
        """Watch coordination.log for new entries."""
        log_path = self.workflow_dir / "coordination.log"
        manager = get_connection_manager()

        last_position = 0
        if log_path.exists():
            last_position = log_path.stat().st_size

        while not self._stop_event.is_set():
            try:
                if log_path.exists():
                    current_size = log_path.stat().st_size
                    if current_size > last_position:
                        # Read new content
                        with open(log_path) as f:
                            f.seek(last_position)
                            new_content = f.read()

                        last_position = current_size

                        # Parse and broadcast events
                        for line in new_content.strip().split("\n"):
                            if line:
                                try:
                                    event = json.loads(line)
                                    await manager.broadcast_to_project(
                                        self.project_name,
                                        "action",
                                        event,
                                    )
                                except json.JSONDecodeError:
                                    # Plain text log line
                                    await manager.broadcast_to_project(
                                        self.project_name,
                                        "log",
                                        {"message": line},
                                    )

                await asyncio.sleep(0.5)  # Poll every 500ms

            except Exception as e:
                logger.error(f"Error watching coordination log: {e}")
                await asyncio.sleep(1)

    async def _setup_live_queries(self) -> None:
        """Setup SurrealDB live queries."""
        try:
            from orchestrator.db import get_connection

            conn = await get_connection()
            manager = get_connection_manager()

            # Subscribe to workflow state changes
            async for change in conn.live_query(
                f"LIVE SELECT * FROM workflow_state WHERE project_dir = '{self.project_dir}'"
            ):
                if self._stop_event.is_set():
                    break

                await manager.broadcast_to_project(
                    self.project_name,
                    "state_change",
                    change,
                )

        except ImportError:
            logger.debug("SurrealDB not available for live queries")
        except Exception as e:
            logger.warning(f"Failed to setup live queries: {e}")

    async def stream_events(
        self,
        since: Optional[datetime] = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream events as an async generator.

        Args:
            since: Only return events after this time

        Yields:
            Event dictionaries
        """
        log_path = self.workflow_dir / "coordination.log"

        if not log_path.exists():
            return

        with open(log_path) as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    event = json.loads(line)

                    # Filter by time if specified
                    if since:
                        event_time = event.get("timestamp")
                        if event_time:
                            event_dt = datetime.fromisoformat(event_time)
                            if event_dt < since:
                                continue

                    yield event

                except json.JSONDecodeError:
                    continue

    def get_recent_events(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
    ) -> list[dict]:
        """Get recent events.

        Args:
            limit: Maximum events to return
            event_type: Filter by event type

        Returns:
            List of event dictionaries
        """
        log_path = self.workflow_dir / "coordination.log"

        if not log_path.exists():
            return []

        events = []
        with open(log_path) as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    event = json.loads(line)

                    if event_type and event.get("type") != event_type:
                        continue

                    events.append(event)

                except json.JSONDecodeError:
                    continue

        # Return most recent
        return events[-limit:] if len(events) > limit else events

    def get_error_events(self, limit: int = 50) -> list[dict]:
        """Get recent error events.

        Args:
            limit: Maximum events to return

        Returns:
            List of error event dictionaries
        """
        return self.get_recent_events(
            limit=limit,
            event_type="error",
        )
