"""Error aggregator for unified error visibility.

Consolidates errors from all sources (action log, state, agent outputs)
into a unified view with deduplication and categorization.
"""

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any


class ErrorSource(str, Enum):
    """Source of the error."""
    ACTION_LOG = "action_log"
    STATE = "state"
    AGENT_OUTPUT = "agent_output"
    EXCEPTION = "exception"
    VALIDATION = "validation"
    VERIFICATION = "verification"


class ErrorSeverity(str, Enum):
    """Severity level of an error."""
    CRITICAL = "critical"  # Workflow cannot continue
    ERROR = "error"        # Step failed, may retry
    WARNING = "warning"    # Non-blocking issue


@dataclass
class AggregatedError:
    """A consolidated error entry."""
    id: str
    timestamp: str
    source: ErrorSource
    error_type: str
    severity: ErrorSeverity
    message: str
    phase: Optional[int] = None
    agent: Optional[str] = None
    task_id: Optional[str] = None
    context: Optional[dict] = None
    stack_trace: Optional[str] = None
    resolution: Optional[str] = None
    resolved_at: Optional[str] = None
    occurrence_count: int = 1
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source.value,
            "error_type": self.error_type,
            "severity": self.severity.value,
            "message": self.message,
            "phase": self.phase,
            "agent": self.agent,
            "task_id": self.task_id,
            "context": self.context,
            "stack_trace": self.stack_trace,
            "resolution": self.resolution,
            "resolved_at": self.resolved_at,
            "occurrence_count": self.occurrence_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AggregatedError":
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            source=ErrorSource(data["source"]),
            error_type=data["error_type"],
            severity=ErrorSeverity(data["severity"]),
            message=data["message"],
            phase=data.get("phase"),
            agent=data.get("agent"),
            task_id=data.get("task_id"),
            context=data.get("context"),
            stack_trace=data.get("stack_trace"),
            resolution=data.get("resolution"),
            resolved_at=data.get("resolved_at"),
            occurrence_count=data.get("occurrence_count", 1),
            first_seen=data.get("first_seen"),
            last_seen=data.get("last_seen"),
        )

    @property
    def is_resolved(self) -> bool:
        """Check if error has been resolved."""
        return self.resolution is not None

    def fingerprint(self) -> str:
        """Generate a fingerprint for deduplication."""
        # Combine key fields to create a unique signature
        key_parts = [
            self.error_type,
            self.message[:100] if self.message else "",
            str(self.phase) if self.phase else "",
            self.agent or "",
            self.task_id or "",
        ]
        return hashlib.md5("|".join(key_parts).encode()).hexdigest()[:16]


# Error type categorization
ERROR_CATEGORIES = {
    # Agent errors
    "timeout": ErrorSeverity.ERROR,
    "cli_not_found": ErrorSeverity.CRITICAL,
    "agent_crash": ErrorSeverity.ERROR,
    "rate_limit": ErrorSeverity.WARNING,

    # Validation errors
    "validation_failed": ErrorSeverity.ERROR,
    "score_below_threshold": ErrorSeverity.ERROR,
    "blocking_issue": ErrorSeverity.ERROR,

    # Implementation errors
    "test_failure": ErrorSeverity.ERROR,
    "build_failure": ErrorSeverity.ERROR,
    "compilation_error": ErrorSeverity.ERROR,

    # Security errors
    "security_vulnerability": ErrorSeverity.CRITICAL,
    "secret_exposure": ErrorSeverity.CRITICAL,

    # System errors
    "file_not_found": ErrorSeverity.ERROR,
    "permission_denied": ErrorSeverity.ERROR,
    "disk_full": ErrorSeverity.CRITICAL,
    "out_of_memory": ErrorSeverity.CRITICAL,

    # Unknown
    "unknown": ErrorSeverity.ERROR,
}


class ErrorAggregator:
    """Aggregates errors from multiple sources.

    Provides deduplication, categorization, and a unified view
    of all errors in the workflow.
    """

    # Maximum unresolved errors to keep in memory
    MAX_UNRESOLVED = 500
    # Percentage to prune when limit reached
    PRUNE_PERCENTAGE = 0.25

    def __init__(self, workflow_dir: str | Path, max_unresolved: int = None):
        """Initialize the error aggregator.

        Args:
            workflow_dir: Directory for error storage
            max_unresolved: Maximum unresolved errors to keep (default 500)
        """
        self.workflow_dir = Path(workflow_dir)
        self.errors_dir = self.workflow_dir / "errors"
        self.all_errors_file = self.errors_dir / "aggregated.jsonl"
        self.unresolved_file = self.errors_dir / "unresolved.json"
        self.max_unresolved = max_unresolved or self.MAX_UNRESOLVED
        self._lock = threading.Lock()
        self._unresolved: dict[str, AggregatedError] = {}
        self._fingerprints: dict[str, str] = {}  # fingerprint -> error_id
        self._ensure_dir()
        self._load_unresolved()

    def _ensure_dir(self) -> None:
        """Ensure errors directory exists."""
        self.errors_dir.mkdir(parents=True, exist_ok=True)

    def _load_unresolved(self) -> None:
        """Load unresolved errors from file."""
        if self.unresolved_file.exists():
            try:
                with open(self.unresolved_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._unresolved = {
                        k: AggregatedError.from_dict(v)
                        for k, v in data.get("errors", {}).items()
                    }
                    self._fingerprints = data.get("fingerprints", {})
            except (json.JSONDecodeError, IOError):
                pass

    def _save_unresolved(self) -> None:
        """Save unresolved errors to file."""
        data = {
            "errors": {k: v.to_dict() for k, v in self._unresolved.items()},
            "fingerprints": self._fingerprints,
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.unresolved_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _prune_old_errors(self) -> int:
        """Prune oldest errors when limit reached.

        Removes oldest 25% of unresolved errors by first_seen timestamp.

        Returns:
            Number of errors pruned
        """
        if len(self._unresolved) <= self.max_unresolved:
            return 0

        # Sort by first_seen (oldest first)
        sorted_errors = sorted(
            self._unresolved.items(),
            key=lambda x: x[1].first_seen or x[1].timestamp,
        )

        # Prune oldest 25%
        prune_count = max(1, int(len(sorted_errors) * self.PRUNE_PERCENTAGE))
        pruned = 0

        for error_id, error in sorted_errors[:prune_count]:
            # Remove from unresolved
            del self._unresolved[error_id]
            # Remove fingerprint mapping
            fingerprint = error.fingerprint()
            self._fingerprints.pop(fingerprint, None)
            pruned += 1

        return pruned

    def _categorize_error(self, error_type: str, message: str) -> ErrorSeverity:
        """Determine severity based on error type and message."""
        # Check known categories
        error_type_lower = error_type.lower()
        for pattern, severity in ERROR_CATEGORIES.items():
            if pattern in error_type_lower:
                return severity

        # Check message for severity hints
        message_lower = message.lower()
        if any(word in message_lower for word in ["critical", "fatal", "cannot continue"]):
            return ErrorSeverity.CRITICAL
        if any(word in message_lower for word in ["warning", "non-blocking", "minor"]):
            return ErrorSeverity.WARNING

        return ErrorSeverity.ERROR

    def add_error(
        self,
        source: ErrorSource,
        error_type: str,
        message: str,
        phase: Optional[int] = None,
        agent: Optional[str] = None,
        task_id: Optional[str] = None,
        context: Optional[dict] = None,
        stack_trace: Optional[str] = None,
        severity: Optional[ErrorSeverity] = None,
    ) -> AggregatedError:
        """Add a new error to the aggregator.

        Handles deduplication automatically.

        Args:
            source: Source of the error
            error_type: Type/category of error
            message: Error message
            phase: Phase number
            agent: Agent name
            task_id: Task identifier
            context: Additional context
            stack_trace: Stack trace if available
            severity: Severity override (auto-detected if not provided)

        Returns:
            The AggregatedError (new or updated existing)
        """
        now = datetime.now().isoformat()

        # Auto-detect severity if not provided
        if severity is None:
            severity = self._categorize_error(error_type, message)

        # Create temporary error for fingerprinting
        temp_error = AggregatedError(
            id="",
            timestamp=now,
            source=source,
            error_type=error_type,
            severity=severity,
            message=message,
            phase=phase,
            agent=agent,
            task_id=task_id,
        )
        fingerprint = temp_error.fingerprint()

        with self._lock:
            # Prune old errors if at capacity
            self._prune_old_errors()

            # Check for existing error with same fingerprint
            if fingerprint in self._fingerprints:
                existing_id = self._fingerprints[fingerprint]
                if existing_id in self._unresolved:
                    # Update existing error
                    existing = self._unresolved[existing_id]
                    existing.occurrence_count += 1
                    existing.last_seen = now
                    if context:
                        existing.context = {**(existing.context or {}), **context}
                    self._save_unresolved()
                    return existing

            # Create new error
            import uuid
            error_id = str(uuid.uuid4())

            error = AggregatedError(
                id=error_id,
                timestamp=now,
                source=source,
                error_type=error_type,
                severity=severity,
                message=message,
                phase=phase,
                agent=agent,
                task_id=task_id,
                context=context,
                stack_trace=stack_trace,
                first_seen=now,
                last_seen=now,
            )

            # Store
            self._unresolved[error_id] = error
            self._fingerprints[fingerprint] = error_id

            # Append to all errors log
            with open(self.all_errors_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(error.to_dict()) + "\n")

            self._save_unresolved()
            return error

    def resolve_error(self, error_id: str, resolution: str) -> Optional[AggregatedError]:
        """Mark an error as resolved.

        Args:
            error_id: ID of the error to resolve
            resolution: Description of how it was resolved

        Returns:
            The resolved error, or None if not found
        """
        with self._lock:
            if error_id not in self._unresolved:
                return None

            error = self._unresolved.pop(error_id)
            error.resolution = resolution
            error.resolved_at = datetime.now().isoformat()

            # Remove fingerprint mapping
            fingerprint = error.fingerprint()
            self._fingerprints.pop(fingerprint, None)

            # Update the all errors log entry
            with open(self.all_errors_file, "a", encoding="utf-8") as f:
                resolved_entry = error.to_dict()
                resolved_entry["_resolved"] = True
                f.write(json.dumps(resolved_entry) + "\n")

            self._save_unresolved()
            return error

    def get_unresolved(
        self,
        severity: Optional[ErrorSeverity] = None,
        phase: Optional[int] = None,
        agent: Optional[str] = None,
    ) -> list[AggregatedError]:
        """Get unresolved errors with optional filters.

        Args:
            severity: Filter by severity
            phase: Filter by phase
            agent: Filter by agent

        Returns:
            List of unresolved errors
        """
        with self._lock:
            errors = list(self._unresolved.values())

        # Apply filters
        if severity:
            errors = [e for e in errors if e.severity == severity]
        if phase is not None:
            errors = [e for e in errors if e.phase == phase]
        if agent:
            errors = [e for e in errors if e.agent == agent]

        # Sort by severity (critical first) then by timestamp (newest first)
        severity_order = {ErrorSeverity.CRITICAL: 0, ErrorSeverity.ERROR: 1, ErrorSeverity.WARNING: 2}
        errors.sort(key=lambda e: (severity_order.get(e.severity, 3), e.timestamp), reverse=True)

        return errors

    def get_all_errors(self, limit: int = 100) -> list[AggregatedError]:
        """Get errors from the log with pagination.

        Uses efficient reverse file reading for large files.

        Args:
            limit: Maximum number of errors to return (default 100)

        Returns:
            List of errors (newest first, excluding resolution entries)
        """
        errors = []
        if not self.all_errors_file.exists():
            return errors

        file_size = self.all_errors_file.stat().st_size
        if file_size < 100_000:  # 100KB threshold
            # Small file - read all
            with open(self.all_errors_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in reversed(lines):
                if len(errors) >= limit:
                    break
                if line.strip():
                    try:
                        data = json.loads(line)
                        if not data.get("_resolved"):
                            errors.append(AggregatedError.from_dict(data))
                    except json.JSONDecodeError:
                        continue
        else:
            # Large file - read from end
            buffer_size = 8192
            with open(self.all_errors_file, "rb") as f:
                f.seek(0, 2)
                position = f.tell()
                remainder = b""

                while position > 0 and len(errors) < limit:
                    read_size = min(buffer_size, position)
                    position -= read_size
                    f.seek(position)
                    chunk = f.read(read_size)
                    data = chunk + remainder
                    lines = data.split(b"\n")
                    remainder = lines[0]

                    for line in reversed(lines[1:]):
                        if len(errors) >= limit:
                            break
                        if line.strip():
                            try:
                                entry = json.loads(line.decode("utf-8"))
                                if not entry.get("_resolved"):
                                    errors.append(AggregatedError.from_dict(entry))
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                continue

        return errors

    def collect_from_action_log(self, action_log_file: Path) -> int:
        """Collect errors from an action log file.

        Args:
            action_log_file: Path to action_log.jsonl

        Returns:
            Number of new errors collected
        """
        if not action_log_file.exists():
            return 0

        collected = 0
        seen_ids = set()

        with open(action_log_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Skip if we've seen this entry
                entry_id = data.get("id", "")
                if entry_id in seen_ids:
                    continue
                seen_ids.add(entry_id)

                # Check if it's an error
                if (
                    data.get("error")
                    or data.get("status") == "failed"
                    or data.get("action_type") in ["error", "agent_error", "phase_failed", "task_failed"]
                ):
                    error_info = data.get("error", {})
                    self.add_error(
                        source=ErrorSource.ACTION_LOG,
                        error_type=error_info.get("error_type", data.get("action_type", "unknown")),
                        message=error_info.get("message", data.get("message", "")),
                        phase=data.get("phase"),
                        agent=data.get("agent"),
                        task_id=data.get("task_id"),
                        context=data.get("details"),
                        stack_trace=error_info.get("stack_trace"),
                    )
                    collected += 1

        return collected

    def collect_from_state(self, state_file: Path) -> int:
        """Collect errors from state.json.

        Args:
            state_file: Path to state.json

        Returns:
            Number of new errors collected
        """
        if not state_file.exists():
            return 0

        collected = 0

        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            return 0

        # Check phase errors
        for phase_name, phase_data in state.get("phases", {}).items():
            if phase_data.get("status") == "failed" and phase_data.get("error"):
                phase_num = {"planning": 1, "validation": 2, "implementation": 3, "verification": 4, "completion": 5}.get(phase_name)
                self.add_error(
                    source=ErrorSource.STATE,
                    error_type="phase_failed",
                    message=phase_data["error"],
                    phase=phase_num,
                    context={"phase_name": phase_name, "attempts": phase_data.get("attempts", 0)},
                )
                collected += 1

            # Check blockers
            for blocker in phase_data.get("blockers", []):
                self.add_error(
                    source=ErrorSource.STATE,
                    error_type="blocker",
                    message=blocker,
                    phase={"planning": 1, "validation": 2, "implementation": 3, "verification": 4, "completion": 5}.get(phase_name),
                    severity=ErrorSeverity.WARNING,
                )
                collected += 1

        return collected

    def get_summary(self) -> dict:
        """Get a summary of error statistics.

        Returns:
            Dictionary with error statistics
        """
        with self._lock:
            unresolved = list(self._unresolved.values())

        # Count by severity
        by_severity = {}
        for error in unresolved:
            by_severity[error.severity.value] = by_severity.get(error.severity.value, 0) + 1

        # Count by phase
        by_phase = {}
        for error in unresolved:
            if error.phase is not None:
                key = str(error.phase)
                by_phase[key] = by_phase.get(key, 0) + 1

        # Count by agent
        by_agent = {}
        for error in unresolved:
            if error.agent:
                by_agent[error.agent] = by_agent.get(error.agent, 0) + 1

        # Get critical errors
        critical_errors = [e for e in unresolved if e.severity == ErrorSeverity.CRITICAL]

        return {
            "unresolved_count": len(unresolved),
            "by_severity": by_severity,
            "by_phase": by_phase,
            "by_agent": by_agent,
            "has_critical": len(critical_errors) > 0,
            "critical_count": len(critical_errors),
        }

    def clear(self) -> None:
        """Clear all errors (for testing/reset)."""
        with self._lock:
            self._unresolved = {}
            self._fingerprints = {}
            if self.all_errors_file.exists():
                self.all_errors_file.unlink()
            self._save_unresolved()


# Global error aggregator instance
_error_aggregator: Optional[ErrorAggregator] = None


def get_error_aggregator(workflow_dir: Optional[str | Path] = None) -> ErrorAggregator:
    """Get or create the global error aggregator instance.

    Args:
        workflow_dir: Workflow directory

    Returns:
        ErrorAggregator instance
    """
    global _error_aggregator

    if _error_aggregator is None:
        workflow_dir = workflow_dir or Path(".workflow")
        _error_aggregator = ErrorAggregator(workflow_dir)

    return _error_aggregator


def reset_error_aggregator() -> None:
    """Reset the global error aggregator instance."""
    global _error_aggregator
    _error_aggregator = None
