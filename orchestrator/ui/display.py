"""Display implementations for workflow UI."""

import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

from orchestrator.ui.state_adapter import EventLogEntry, TaskUIInfo, UIStateSnapshot


class UIState:
    """Thread-safe state container for UI."""

    def __init__(self, project_name: str):
        """
        Initialize UI state.

        Args:
            project_name: Name of the project
        """
        self._lock = threading.Lock()
        self._project_name = project_name
        self._start_time = time.time()

        # Phase tracking
        self._current_phase = 0
        self._total_phases = 5
        self._phase_progress = 0.0
        self._phase_name = "Initializing"

        # Task tracking
        self._tasks: list[TaskUIInfo] = []
        self._tasks_completed = 0
        self._tasks_total = 0
        self._current_task_id: Optional[str] = None

        # Metrics
        self._tokens = 0
        self._cost = 0.0
        self._files_created = 0
        self._files_modified = 0

        # Events
        self._recent_events: list[EventLogEntry] = []
        self._max_events = 50

        # Status
        self._status = "running"

    def add_event(self, message: str, level: str = "info") -> None:
        """Add an event to the log."""
        with self._lock:
            entry = EventLogEntry(
                timestamp=datetime.now(),
                message=message,
                level=level,
            )
            self._recent_events.append(entry)

            # Trim if too many events
            if len(self._recent_events) > self._max_events:
                self._recent_events = self._recent_events[-self._max_events :]

    def update_ralph_iteration(
        self,
        task_id: str,
        iteration: int,
        max_iterations: int,
        tests_passed: int = 0,
        tests_total: int = 0,
    ) -> None:
        """Update Ralph iteration for a task."""
        with self._lock:
            for task in self._tasks:
                if task.id == task_id:
                    task.iteration = iteration
                    task.max_iterations = max_iterations
                    task.tests_passed = tests_passed
                    task.tests_total = tests_total
                    break

    def update_metrics(
        self,
        tokens: int = 0,
        cost: float = 0.0,
        files_created: Optional[int] = None,
        files_modified: Optional[int] = None,
    ) -> None:
        """Update metrics."""
        with self._lock:
            if tokens:
                self._tokens = tokens
            if cost:
                self._cost = cost
            if files_created is not None:
                self._files_created = files_created
            if files_modified is not None:
                self._files_modified = files_modified

    def set_status(self, status: str) -> None:
        """Set workflow status."""
        with self._lock:
            self._status = status

    def set_phase(self, phase: int, name: str, progress: float = 0.0) -> None:
        """Set current phase."""
        with self._lock:
            self._current_phase = phase
            self._phase_name = name
            self._phase_progress = progress

    def set_tasks(self, tasks: list[TaskUIInfo]) -> None:
        """Set task list."""
        with self._lock:
            self._tasks = tasks
            self._tasks_total = len(tasks)
            self._tasks_completed = sum(1 for t in tasks if t.status == "completed")

    def get_snapshot(self) -> UIStateSnapshot:
        """Get immutable snapshot of current state."""
        with self._lock:
            return UIStateSnapshot(
                project_name=self._project_name,
                elapsed_seconds=time.time() - self._start_time,
                current_phase=self._current_phase,
                total_phases=self._total_phases,
                phase_progress=self._phase_progress,
                phase_name=self._phase_name,
                tasks=list(self._tasks),  # Copy
                tasks_completed=self._tasks_completed,
                tasks_total=self._tasks_total,
                current_task_id=self._current_task_id,
                tokens=self._tokens,
                cost=self._cost,
                files_created=self._files_created,
                files_modified=self._files_modified,
                recent_events=list(self._recent_events),  # Copy
                status=self._status,
            )


class PlaintextDisplay:
    """Simple plaintext display for non-interactive environments."""

    def __init__(self, project_name: str):
        """
        Initialize plaintext display.

        Args:
            project_name: Name of the project
        """
        self.project_name = project_name
        self._start_time = time.time()

    @contextmanager
    def start(self) -> Generator[None, None, None]:
        """Context manager for display lifecycle."""
        print(f"Starting workflow for project: {self.project_name}")
        try:
            yield
        finally:
            elapsed = time.time() - self._start_time
            print(f"Workflow completed in {elapsed:.1f}s")

    def log_event(self, message: str, level: str = "info") -> None:
        """Print a log event."""
        level_map = {
            "info": "INFO",
            "warning": "WARN",
            "error": "ERROR",
            "success": "OK",
        }
        level_str = level_map.get(level, "INFO")
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level_str}] {message}")

    def update_ralph_iteration(
        self,
        task_id: str,
        iteration: int,
        max_iter: int,
        tests_passed: int = 0,
        tests_total: int = 0,
    ) -> None:
        """Print Ralph iteration info."""
        print(
            f"  Task {task_id}: iteration {iteration}/{max_iter}, {tests_passed}/{tests_total} tests passed"
        )

    def update_state(self, state: dict[str, Any]) -> None:
        """Update from workflow state (no-op for plaintext)."""
        pass

    def update_metrics(
        self,
        tokens: int = 0,
        cost: float = 0.0,
        files_created: Optional[int] = None,
        files_modified: Optional[int] = None,
    ) -> None:
        """Update metrics (no-op for plaintext)."""
        pass

    def show_completion(self, success: bool, message: str = "") -> None:
        """Show completion message."""
        if success:
            print(f"[OK] Workflow completed: {message}")
        else:
            print(f"[ERROR] Workflow failed: {message}")


class WorkflowDisplay:
    """Rich interactive display for workflow monitoring."""

    def __init__(self, project_name: str):
        """
        Initialize workflow display.

        Args:
            project_name: Name of the project
        """
        self.project_name = project_name
        self._state = UIState(project_name)
        self._running = False

    @contextmanager
    def start(self) -> Generator[None, None, None]:
        """Context manager for display lifecycle."""
        self._running = True
        self._state.add_event(f"Starting workflow for {self.project_name}", "info")
        try:
            yield
        finally:
            self._running = False

    def log_event(self, message: str, level: str = "info") -> None:
        """Add event to log."""
        self._state.add_event(message, level)

    def update_ralph_iteration(
        self,
        task_id: str,
        iteration: int,
        max_iter: int,
        tests_passed: int = 0,
        tests_total: int = 0,
    ) -> None:
        """Update Ralph iteration."""
        self._state.update_ralph_iteration(
            task_id=task_id,
            iteration=iteration,
            max_iterations=max_iter,
            tests_passed=tests_passed,
            tests_total=tests_total,
        )
        self.log_event(
            f"Task {task_id}: iteration {iteration}/{max_iter}, {tests_passed}/{tests_total} tests",
            "info",
        )

    def update_state(self, state: dict[str, Any]) -> None:
        """Update from workflow state."""
        if "current_phase" in state:
            phase = state["current_phase"]
            phase_names = {
                1: "Planning",
                2: "Validation",
                3: "Implementation",
                4: "Verification",
                5: "Completion",
            }
            self._state.set_phase(
                phase=phase,
                name=phase_names.get(phase, "Unknown"),
            )

        if "tasks" in state:
            tasks = []
            for t in state["tasks"]:
                tasks.append(
                    TaskUIInfo(
                        id=t.get("id", ""),
                        title=t.get("title", ""),
                        status=t.get("status", "pending"),
                    )
                )
            self._state.set_tasks(tasks)

    def update_metrics(
        self,
        tokens: int = 0,
        cost: float = 0.0,
        files_created: Optional[int] = None,
        files_modified: Optional[int] = None,
    ) -> None:
        """Update metrics."""
        self._state.update_metrics(
            tokens=tokens,
            cost=cost,
            files_created=files_created,
            files_modified=files_modified,
        )

    def show_completion(self, success: bool, message: str = "") -> None:
        """Show completion."""
        if success:
            self._state.set_status("completed")
            self._state.add_event(f"Workflow completed: {message}", "success")
        else:
            self._state.set_status("failed")
            self._state.add_event(f"Workflow failed: {message}", "error")
