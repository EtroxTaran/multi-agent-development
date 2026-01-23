"""WebSocket callbacks for workflow events."""

import asyncio
import logging
from typing import Any, Dict, Optional

from orchestrator.ui.callbacks import ProgressCallback
from .websocket import ConnectionManager

logger = logging.getLogger(__name__)


class WebSocketProgressCallback:
    """Callback handler that streams events to WebSockets."""

    def __init__(self, manager: ConnectionManager, project_name: str):
        """Initialize the callback handler.

        Args:
            manager: WebSocket connection manager
            project_name: Name of the project to broadcast to
        """
        self.manager = manager
        self.project_name = project_name

    def _broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcast event asynchronously."""
        try:
            # We are running inside an event loop, so we can schedule the coroutine
            loop = asyncio.get_running_loop()
            loop.create_task(
                self.manager.broadcast_to_project(
                    self.project_name,
                    event_type,
                    data
                )
            )
        except RuntimeError:
            # Fallback if no running loop (e.g. testing)
            pass
        except Exception as e:
            logger.error(f"Failed to broadcast event {event_type}: {e}")

    def on_node_start(self, node_name: str, state: Dict[str, Any]) -> None:
        """Called when a workflow node starts."""
        self._broadcast("node_start", {
            "node": node_name,
            "input": state,
            "timestamp": asyncio.get_running_loop().time()
        })

    def on_node_end(self, node_name: str, state: Dict[str, Any]) -> None:
        """Called when a workflow node ends."""
        self._broadcast("node_end", {
            "node": node_name,
            "output": state,
            "timestamp": asyncio.get_running_loop().time()
        })

    def on_ralph_iteration(
        self,
        task_id: str,
        iteration: int,
        max_iter: int,
        tests_passed: int = 0,
        tests_total: int = 0,
    ) -> None:
        """Called on each Ralph loop iteration."""
        self._broadcast("ralph_iteration", {
            "task_id": task_id,
            "iteration": iteration,
            "max_iter": max_iter,
            "tests_passed": tests_passed,
            "tests_total": tests_total
        })

    def on_task_start(self, task_id: str, task_title: str) -> None:
        """Called when a task starts."""
        self._broadcast("task_start", {
            "task_id": task_id,
            "title": task_title
        })

    def on_task_complete(self, task_id: str, success: bool) -> None:
        """Called when a task completes."""
        self._broadcast("task_complete", {
            "task_id": task_id,
            "success": success
        })

    def on_metrics_update(
        self,
        tokens: int = 0,
        cost: float = 0.0,
        files_created: Optional[int] = None,
        files_modified: Optional[int] = None,
    ) -> None:
        """Called when metrics are updated."""
        self._broadcast("metrics_update", {
            "tokens": tokens,
            "cost": cost,
            "files_created": files_created,
            "files_modified": files_modified
        })
