"""Unified action log for workflow observability.

Provides a single, append-only log of all significant workflow actions
with real-time console output and queryable persistence.
"""

import json
import os
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class ActionType(str, Enum):
    """Types of actions that can be logged."""

    # Workflow level
    WORKFLOW_START = "workflow_start"
    WORKFLOW_END = "workflow_end"
    WORKFLOW_PAUSE = "workflow_pause"
    WORKFLOW_RESUME = "workflow_resume"

    # Phase level
    PHASE_START = "phase_start"
    PHASE_COMPLETE = "phase_complete"
    PHASE_FAILED = "phase_failed"
    PHASE_RETRY = "phase_retry"

    # Agent level
    AGENT_INVOKE = "agent_invoke"
    AGENT_COMPLETE = "agent_complete"
    AGENT_ERROR = "agent_error"
    AGENT_TIMEOUT = "agent_timeout"

    # Task level
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"
    TASK_BLOCKED = "task_blocked"
    TASK_SKIPPED = "task_skipped"

    # Validation/Verification
    VALIDATION_PASS = "validation_pass"
    VALIDATION_FAIL = "validation_fail"
    VERIFICATION_PASS = "verification_pass"
    VERIFICATION_FAIL = "verification_fail"

    # Human interaction
    ESCALATION = "escalation"
    HUMAN_INPUT = "human_input"
    CLARIFICATION_REQUEST = "clarification_request"
    CLARIFICATION_RESPONSE = "clarification_response"

    # Git operations
    GIT_COMMIT = "git_commit"
    GIT_ROLLBACK = "git_rollback"

    # System
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    CHECKPOINT = "checkpoint"


class ActionStatus(str, Enum):
    """Status of an action."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"


@dataclass
class ErrorInfo:
    """Structured error information."""

    error_type: str
    message: str
    stack_trace: Optional[str] = None
    context: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "stack_trace": self.stack_trace,
            "context": self.context,
        }

    @classmethod
    def from_exception(cls, exc: Exception, context: Optional[dict] = None) -> "ErrorInfo":
        """Create ErrorInfo from an exception."""
        import traceback

        return cls(
            error_type=type(exc).__name__,
            message=str(exc),
            stack_trace=traceback.format_exc(),
            context=context,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "ErrorInfo":
        return cls(**data)


@dataclass
class ActionEntry:
    """A single action log entry."""

    id: str
    timestamp: str
    action_type: ActionType
    message: str
    status: ActionStatus = ActionStatus.COMPLETED
    phase: Optional[int] = None
    agent: Optional[str] = None
    task_id: Optional[str] = None
    details: Optional[dict] = None
    error: Optional[ErrorInfo] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "action_type": self.action_type.value,
            "message": self.message,
            "status": self.status.value,
            "phase": self.phase,
            "agent": self.agent,
            "task_id": self.task_id,
            "details": self.details,
            "error": self.error.to_dict() if self.error else None,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActionEntry":
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            action_type=ActionType(data["action_type"]),
            message=data["message"],
            status=ActionStatus(data.get("status", "completed")),
            phase=data.get("phase"),
            agent=data.get("agent"),
            task_id=data.get("task_id"),
            details=data.get("details"),
            error=ErrorInfo.from_dict(data["error"]) if data.get("error") else None,
            duration_ms=data.get("duration_ms"),
        )


# ANSI color codes for console output
COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "magenta": "\033[95m",
    "cyan": "\033[96m",
    "white": "\033[97m",
    "gray": "\033[90m",
}

# Status symbols
SYMBOLS = {
    ActionStatus.STARTED: ("▶", "blue"),
    ActionStatus.COMPLETED: ("✓", "green"),
    ActionStatus.FAILED: ("✗", "red"),
    ActionStatus.SKIPPED: ("⊘", "gray"),
    ActionStatus.PENDING: ("○", "yellow"),
}

# Action type formatting
ACTION_COLORS = {
    ActionType.WORKFLOW_START: "cyan",
    ActionType.WORKFLOW_END: "cyan",
    ActionType.PHASE_START: "blue",
    ActionType.PHASE_COMPLETE: "green",
    ActionType.PHASE_FAILED: "red",
    ActionType.AGENT_INVOKE: "magenta",
    ActionType.AGENT_COMPLETE: "green",
    ActionType.AGENT_ERROR: "red",
    ActionType.TASK_START: "blue",
    ActionType.TASK_COMPLETE: "green",
    ActionType.TASK_FAILED: "red",
    ActionType.ERROR: "red",
    ActionType.WARNING: "yellow",
    ActionType.ESCALATION: "yellow",
}


class ActionLog:
    """Unified action log for workflow observability.

    Thread-safe, append-only log with real-time console output
    and queryable persistence.
    """

    def __init__(
        self,
        workflow_dir: str | Path,
        console_output: bool = True,
        console_colors: bool = True,
    ):
        """Initialize the action log.

        Args:
            workflow_dir: Directory for log storage (.workflow/)
            console_output: Whether to output to console in real-time
            console_colors: Whether to use ANSI colors in console output
        """
        self.workflow_dir = Path(workflow_dir)
        self.log_file = self.workflow_dir / "action_log.jsonl"
        self.index_file = self.workflow_dir / "action_log_index.json"
        self.console_output = console_output
        self.console_colors = console_colors
        self._lock = threading.Lock()
        self._index: dict = {"total": 0, "by_phase": {}, "by_agent": {}, "errors": 0}
        self._ensure_dir()
        self._load_index()

    def _ensure_dir(self) -> None:
        """Ensure workflow directory exists."""
        self.workflow_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> None:
        """Load index from file if it exists."""
        if self.index_file.exists():
            try:
                with open(self.index_file, encoding="utf-8") as f:
                    self._index = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass  # Start with empty index

    def _save_index(self) -> None:
        """Save index to file atomically.

        Uses write-to-temp then atomic rename to prevent corruption.
        """
        tmp_path = None
        try:
            # Write to temp file first
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self.workflow_dir,
                prefix=".index_",
                suffix=".json",
                delete=False,
                encoding="utf-8",
            ) as tmp_file:
                tmp_path = tmp_file.name
                json.dump(self._index, tmp_file, indent=2)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())

            # Atomic replace
            os.replace(tmp_path, str(self.index_file))
            tmp_path = None  # Mark as successfully moved

        finally:
            # Clean up temp file if atomic replace failed
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _update_index(self, entry: ActionEntry) -> None:
        """Update the index with a new entry."""
        self._index["total"] += 1

        if entry.phase is not None:
            phase_key = str(entry.phase)
            self._index["by_phase"][phase_key] = self._index["by_phase"].get(phase_key, 0) + 1

        if entry.agent:
            self._index["by_agent"][entry.agent] = self._index["by_agent"].get(entry.agent, 0) + 1

        if entry.error or entry.status == ActionStatus.FAILED:
            self._index["errors"] += 1

        self._index["last_updated"] = datetime.now().isoformat()
        self._save_index()

    def _format_console(self, entry: ActionEntry) -> str:
        """Format entry for console output with colors."""
        timestamp = datetime.fromisoformat(entry.timestamp).strftime("%H:%M:%S")

        if self.console_colors:
            # Get status symbol and color
            symbol, symbol_color = SYMBOLS.get(entry.status, ("•", "white"))
            action_color = ACTION_COLORS.get(entry.action_type, "white")

            parts = [f"{COLORS['gray']}[{timestamp}]{COLORS['reset']}"]

            if entry.phase is not None:
                parts.append(f"{COLORS['cyan']}[P{entry.phase}]{COLORS['reset']}")

            if entry.agent:
                parts.append(f"{COLORS['magenta']}[{entry.agent}]{COLORS['reset']}")

            if entry.task_id:
                parts.append(f"{COLORS['blue']}[{entry.task_id}]{COLORS['reset']}")

            parts.append(f"{COLORS[symbol_color]}{symbol}{COLORS['reset']}")
            parts.append(f"{COLORS[action_color]}{entry.message}{COLORS['reset']}")

            if entry.duration_ms is not None:
                parts.append(f"{COLORS['gray']}({entry.duration_ms:.0f}ms){COLORS['reset']}")

            return " ".join(parts)
        else:
            # Plain text format
            parts = [f"[{timestamp}]"]

            if entry.phase is not None:
                parts.append(f"[P{entry.phase}]")

            if entry.agent:
                parts.append(f"[{entry.agent}]")

            if entry.task_id:
                parts.append(f"[{entry.task_id}]")

            symbol, _ = SYMBOLS.get(entry.status, ("•", "white"))
            parts.append(symbol)
            parts.append(entry.message)

            if entry.duration_ms is not None:
                parts.append(f"({entry.duration_ms:.0f}ms)")

            return " ".join(parts)

    def log(
        self,
        action_type: ActionType,
        message: str,
        status: ActionStatus = ActionStatus.COMPLETED,
        phase: Optional[int] = None,
        agent: Optional[str] = None,
        task_id: Optional[str] = None,
        details: Optional[dict] = None,
        error: Optional[ErrorInfo] = None,
        duration_ms: Optional[float] = None,
    ) -> ActionEntry:
        """Log an action.

        Args:
            action_type: Type of action
            message: Human-readable message
            status: Action status
            phase: Phase number (1-5)
            agent: Agent name (claude, cursor, gemini)
            task_id: Task identifier
            details: Additional structured data
            error: Error information if failed
            duration_ms: Duration in milliseconds

        Returns:
            The created ActionEntry
        """
        entry = ActionEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            action_type=action_type,
            message=message,
            status=status,
            phase=phase,
            agent=agent,
            task_id=task_id,
            details=details,
            error=error,
            duration_ms=duration_ms,
        )

        with self._lock:
            # Append to log file with proper flush/sync
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
                f.flush()
                os.fsync(f.fileno())

            # Update index (uses atomic write internally)
            self._update_index(entry)

            # Console output
            if self.console_output:
                formatted = self._format_console(entry)
                output = sys.stderr if entry.status == ActionStatus.FAILED else sys.stdout
                print(formatted, file=output)

        return entry

    def get_recent(self, limit: int = 20) -> list[ActionEntry]:
        """Get the most recent log entries using efficient reverse file reading.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of ActionEntry objects (newest first)
        """
        entries = []
        if not self.log_file.exists():
            return entries

        with self._lock:
            # Use efficient reverse reading to avoid loading entire file
            entries = self._read_from_end(limit)

        return entries

    def _read_from_end(self, limit: int, filter_fn: callable = None) -> list[ActionEntry]:
        """Read entries from end of file efficiently.

        Uses seek and read backwards to avoid loading entire file.

        Args:
            limit: Maximum entries to return
            filter_fn: Optional filter function (entry_dict -> bool)

        Returns:
            List of ActionEntry objects (newest first)
        """
        entries = []
        if not self.log_file.exists():
            return entries

        # For small files, just read all
        file_size = self.log_file.stat().st_size
        if file_size < 100_000:  # 100KB threshold
            return self._read_all_filtered(limit, filter_fn)

        # Read backwards for large files
        buffer_size = 8192
        with open(self.log_file, "rb") as f:
            f.seek(0, 2)  # Seek to end
            file_size = f.tell()
            remainder = b""
            position = file_size

            while position > 0 and len(entries) < limit:
                # Move backwards
                read_size = min(buffer_size, position)
                position -= read_size
                f.seek(position)
                chunk = f.read(read_size)

                # Combine with remainder from previous chunk
                data = chunk + remainder
                lines = data.split(b"\n")

                # Last element may be incomplete - save for next iteration
                remainder = lines[0]
                lines = lines[1:]

                # Process lines in reverse
                for line in reversed(lines):
                    if line.strip():
                        try:
                            entry_dict = json.loads(line.decode("utf-8"))
                            if filter_fn is None or filter_fn(entry_dict):
                                entries.append(ActionEntry.from_dict(entry_dict))
                                if len(entries) >= limit:
                                    break
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue

            # Handle remainder from beginning of file
            if remainder.strip() and len(entries) < limit:
                try:
                    entry_dict = json.loads(remainder.decode("utf-8"))
                    if filter_fn is None or filter_fn(entry_dict):
                        entries.append(ActionEntry.from_dict(entry_dict))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

        return entries

    def _read_all_filtered(self, limit: int, filter_fn: callable = None) -> list[ActionEntry]:
        """Read all entries with optional filter (for small files).

        Args:
            limit: Maximum entries to return
            filter_fn: Optional filter function

        Returns:
            List of ActionEntry objects (newest first)
        """
        entries = []
        with open(self.log_file, encoding="utf-8") as f:
            lines = f.readlines()

        for line in reversed(lines):
            if len(entries) >= limit:
                break
            if line.strip():
                try:
                    data = json.loads(line)
                    if filter_fn is None or filter_fn(data):
                        entries.append(ActionEntry.from_dict(data))
                except json.JSONDecodeError:
                    continue

        return entries

    def get_errors(self, since: Optional[str] = None, limit: int = 100) -> list[ActionEntry]:
        """Get error entries with pagination.

        Args:
            since: ISO timestamp to filter errors after
            limit: Maximum number of errors to return (default 100)

        Returns:
            List of error ActionEntry objects (newest first)
        """
        if not self.log_file.exists():
            return []

        def is_error(data: dict) -> bool:
            """Check if entry is an error."""
            if since and data.get("timestamp", "") < since:
                return False
            return (
                data.get("error")
                or data.get("status") == "failed"
                or data.get("action_type")
                in ["error", "agent_error", "phase_failed", "task_failed"]
            )

        with self._lock:
            return self._read_from_end(limit, filter_fn=is_error)

    def get_by_phase(self, phase: int, limit: int = 500) -> list[ActionEntry]:
        """Get entries for a specific phase with pagination.

        Args:
            phase: Phase number (1-5)
            limit: Maximum number of entries to return (default 500)

        Returns:
            List of ActionEntry objects for the phase (newest first)
        """
        if not self.log_file.exists():
            return []

        def matches_phase(data: dict) -> bool:
            return data.get("phase") == phase

        with self._lock:
            return self._read_from_end(limit, filter_fn=matches_phase)

    def get_by_agent(self, agent: str, limit: int = 500) -> list[ActionEntry]:
        """Get entries for a specific agent with pagination.

        Args:
            agent: Agent name (claude, cursor, gemini)
            limit: Maximum number of entries to return (default 500)

        Returns:
            List of ActionEntry objects for the agent (newest first)
        """
        if not self.log_file.exists():
            return []

        def matches_agent(data: dict) -> bool:
            return data.get("agent") == agent

        with self._lock:
            return self._read_from_end(limit, filter_fn=matches_agent)

    def get_by_task(self, task_id: str, limit: int = 200) -> list[ActionEntry]:
        """Get entries for a specific task with pagination.

        Args:
            task_id: Task identifier
            limit: Maximum number of entries to return (default 200)

        Returns:
            List of ActionEntry objects for the task (newest first)
        """
        if not self.log_file.exists():
            return []

        def matches_task(data: dict) -> bool:
            return data.get("task_id") == task_id

        with self._lock:
            return self._read_from_end(limit, filter_fn=matches_task)

    def get_summary(self) -> dict:
        """Get a summary of the action log.

        Returns:
            Dictionary with summary statistics
        """
        with self._lock:
            return {
                "total_actions": self._index.get("total", 0),
                "actions_by_phase": self._index.get("by_phase", {}),
                "actions_by_agent": self._index.get("by_agent", {}),
                "error_count": self._index.get("errors", 0),
                "last_updated": self._index.get("last_updated"),
            }

    def clear(self) -> None:
        """Clear the action log (for testing/reset)."""
        with self._lock:
            if self.log_file.exists():
                self.log_file.unlink()
            self._index = {"total": 0, "by_phase": {}, "by_agent": {}, "errors": 0}
            self._save_index()


# Global action log registry - keyed by resolved path to prevent cross-contamination
_action_logs: dict[str, ActionLog] = {}
_action_log_lock = threading.Lock()


def get_action_log(workflow_dir: Optional[str | Path] = None) -> ActionLog:
    """Get or create an action log instance for a specific workflow directory.

    Uses a registry keyed by the resolved absolute path to prevent
    cross-contamination between different projects.

    Args:
        workflow_dir: Workflow directory (defaults to .workflow/)

    Returns:
        ActionLog instance for this workflow directory
    """
    workflow_dir = Path(workflow_dir or ".workflow").resolve()
    key = str(workflow_dir)

    with _action_log_lock:
        if key not in _action_logs:
            _action_logs[key] = ActionLog(workflow_dir)
        return _action_logs[key]


def reset_action_log(workflow_dir: Optional[str | Path] = None) -> None:
    """Reset an action log instance for a specific workflow directory.

    Args:
        workflow_dir: Workflow directory to reset (None resets all)
    """
    global _action_logs

    with _action_log_lock:
        if workflow_dir is None:
            _action_logs.clear()
        else:
            key = str(Path(workflow_dir).resolve())
            if key in _action_logs:
                del _action_logs[key]
