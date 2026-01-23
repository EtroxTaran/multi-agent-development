"""Callback handlers for UI updates."""

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class ProgressCallback(Protocol):
    """Protocol for progress callbacks."""

    def on_node_start(self, node_name: str, state: dict[str, Any]) -> None:
        """Called when a workflow node starts."""
        ...

    def on_node_end(self, node_name: str, state: dict[str, Any]) -> None:
        """Called when a workflow node ends."""
        ...

    def on_ralph_iteration(
        self,
        task_id: str,
        iteration: int,
        max_iter: int,
        tests_passed: int = 0,
        tests_total: int = 0,
    ) -> None:
        """Called on each Ralph loop iteration."""
        ...

    def on_task_start(self, task_id: str, task_title: str) -> None:
        """Called when a task starts."""
        ...

    def on_task_complete(self, task_id: str, success: bool) -> None:
        """Called when a task completes."""
        ...

    def on_metrics_update(
        self,
        tokens: int = 0,
        cost: float = 0.0,
        files_created: Optional[int] = None,
        files_modified: Optional[int] = None,
    ) -> None:
        """Called when metrics are updated."""
        ...


class NullCallback:
    """No-op callback implementation."""

    def on_node_start(self, node_name: str, state: dict[str, Any]) -> None:
        """No-op."""
        pass

    def on_node_end(self, node_name: str, state: dict[str, Any]) -> None:
        """No-op."""
        pass

    def on_ralph_iteration(
        self,
        task_id: str,
        iteration: int,
        max_iter: int,
        tests_passed: int = 0,
        tests_total: int = 0,
    ) -> None:
        """No-op."""
        pass

    def on_task_start(self, task_id: str, task_title: str) -> None:
        """No-op."""
        pass

    def on_task_complete(self, task_id: str, success: bool) -> None:
        """No-op."""
        pass

    def on_metrics_update(
        self,
        tokens: int = 0,
        cost: float = 0.0,
        files_created: Optional[int] = None,
        files_modified: Optional[int] = None,
    ) -> None:
        """No-op."""
        pass


class UICallbackHandler:
    """Callback handler that forwards events to UI display."""

    def __init__(self, display: Any):
        """
        Initialize callback handler.

        Args:
            display: Display instance to forward events to
        """
        self._display = display

    def on_node_start(self, node_name: str, state: dict[str, Any]) -> None:
        """Forward node start to display."""
        self._display.log_event(f"Starting node: {node_name}", "info")
        self._display.update_state(state)

    def on_node_end(self, node_name: str, state: dict[str, Any]) -> None:
        """Forward node end to display."""
        errors = state.get("errors", [])
        if errors:
            self._display.log_event(f"Node {node_name} completed with errors", "warning")
        else:
            self._display.log_event(f"Node {node_name} completed", "info")
        self._display.update_state(state)

    def on_ralph_iteration(
        self,
        task_id: str,
        iteration: int,
        max_iter: int,
        tests_passed: int = 0,
        tests_total: int = 0,
    ) -> None:
        """Forward Ralph iteration to display."""
        self._display.update_ralph_iteration(
            task_id=task_id,
            iteration=iteration,
            max_iter=max_iter,
            tests_passed=tests_passed,
            tests_total=tests_total,
        )

    def on_task_start(self, task_id: str, task_title: str) -> None:
        """Forward task start to display."""
        self._display.log_event(f"Starting task {task_id}: {task_title}", "info")

    def on_task_complete(self, task_id: str, success: bool) -> None:
        """Forward task completion to display."""
        if success:
            self._display.log_event(f"Task {task_id} completed successfully", "success")
        else:
            self._display.log_event(f"Task {task_id} failed", "error")

    def on_metrics_update(
        self,
        tokens: int = 0,
        cost: float = 0.0,
        files_created: Optional[int] = None,
        files_modified: Optional[int] = None,
    ) -> None:
        """Forward metrics update to display."""
        self._display.update_metrics(
            tokens=tokens,
            cost=cost,
            files_created=files_created,
            files_modified=files_modified,
        )
