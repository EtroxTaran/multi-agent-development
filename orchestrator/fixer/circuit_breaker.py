"""Circuit breaker pattern for preventing infinite fix loops.

The circuit breaker prevents the fixer from getting stuck in infinite
retry loops by tracking consecutive failures and temporarily disabling
the fixer when too many failures occur.

States:
- CLOSED: Fixer is operational, fixes are attempted
- OPEN: Fixer is disabled due to too many failures
- HALF_OPEN: Fixer is testing if it can recover

Usage:
    cb = CircuitBreaker(failure_threshold=5, reset_timeout=300)

    if cb.can_attempt():
        try:
            # Attempt fix
            cb.record_success()
        except Exception:
            cb.record_failure()

Granular Circuit Breaker:
    The GranularCircuitBreaker provides per-error-type tracking using
    sliding windows, allowing fine-grained control over which error
    types trigger circuit opening.

    gcb = GranularCircuitBreaker(workflow_dir, window_size=10, threshold=0.5)

    if gcb.can_attempt("SyntaxError"):
        try:
            # Attempt fix
            gcb.record("SyntaxError", success=True)
        except Exception:
            gcb.record("SyntaxError", success=False)
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, fixes are attempted
    OPEN = "open"  # Circuit tripped, fixes are blocked
    HALF_OPEN = "half_open"  # Testing if circuit can be closed


@dataclass
class CircuitStats:
    """Statistics for the circuit breaker."""

    total_attempts: int = 0
    total_successes: int = 0
    total_failures: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[str] = None
    last_success_time: Optional[str] = None
    state_changes: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_attempts": self.total_attempts,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "state_changes": self.state_changes[-10:],  # Keep last 10
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CircuitStats":
        return cls(
            total_attempts=data.get("total_attempts", 0),
            total_successes=data.get("total_successes", 0),
            total_failures=data.get("total_failures", 0),
            consecutive_failures=data.get("consecutive_failures", 0),
            consecutive_successes=data.get("consecutive_successes", 0),
            last_failure_time=data.get("last_failure_time"),
            last_success_time=data.get("last_success_time"),
            state_changes=data.get("state_changes", []),
        )


class CircuitBreaker:
    """Circuit breaker for the fixer agent.

    Prevents infinite fix loops by tracking failures and temporarily
    disabling the fixer when too many consecutive failures occur.

    Attributes:
        failure_threshold: Number of consecutive failures before opening circuit
        reset_timeout_seconds: Time to wait before attempting to close circuit
        half_open_success_threshold: Successes needed in half-open to close circuit
    """

    def __init__(
        self,
        workflow_dir: str | Path,
        failure_threshold: int = 5,
        reset_timeout_seconds: int = 300,
        half_open_success_threshold: int = 2,
    ):
        """Initialize the circuit breaker.

        Args:
            workflow_dir: Directory for persisting circuit state
            failure_threshold: Consecutive failures to trip circuit
            reset_timeout_seconds: Seconds before attempting recovery
            half_open_success_threshold: Successes needed to close from half-open
        """
        self.workflow_dir = Path(workflow_dir)
        self.state_file = self.workflow_dir / "fixer" / "circuit_breaker.json"
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.half_open_success_threshold = half_open_success_threshold

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._opened_at: Optional[float] = None
        self._stats = CircuitStats()

        self._load_state()

    def _ensure_dir(self) -> None:
        """Ensure fixer directory exists."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> None:
        """Load circuit state from disk."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                    self._state = CircuitState(data.get("state", "closed"))
                    self._opened_at = data.get("opened_at")
                    self._stats = CircuitStats.from_dict(data.get("stats", {}))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Could not load circuit state: {e}")

    def _save_state(self) -> None:
        """Save circuit state to disk."""
        self._ensure_dir()
        data = {
            "state": self._state.value,
            "opened_at": self._opened_at,
            "stats": self._stats.to_dict(),
            "updated_at": datetime.now().isoformat(),
        }
        try:
            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logger.warning(f"Could not save circuit state: {e}")

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            # Check for automatic state transitions
            self._check_state_transition()
            return self._state

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking fixes)."""
        return self.state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (allowing fixes)."""
        return self.state == CircuitState.CLOSED

    @property
    def stats(self) -> CircuitStats:
        """Get circuit statistics."""
        with self._lock:
            return self._stats

    def _check_state_transition(self) -> None:
        """Check if state should automatically transition.

        Called internally when checking state.
        """
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            elapsed = time.time() - self._opened_at
            if elapsed >= self.reset_timeout_seconds:
                self._transition_to(CircuitState.HALF_OPEN, "timeout_expired")

    def _transition_to(self, new_state: CircuitState, reason: str) -> None:
        """Transition to a new state.

        Args:
            new_state: State to transition to
            reason: Reason for transition
        """
        old_state = self._state
        self._state = new_state

        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()
        elif new_state == CircuitState.CLOSED:
            self._opened_at = None

        # Record state change
        self._stats.state_changes.append(
            {
                "from": old_state.value,
                "to": new_state.value,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.info(f"Circuit breaker: {old_state.value} -> {new_state.value} ({reason})")
        self._save_state()

    def can_attempt(self) -> bool:
        """Check if a fix attempt is allowed.

        Returns:
            True if fix can be attempted, False if circuit is open
        """
        with self._lock:
            self._check_state_transition()

            if self._state == CircuitState.CLOSED:
                return True
            elif self._state == CircuitState.HALF_OPEN:
                return True  # Allow test attempt
            else:  # OPEN
                return False

    def record_success(self) -> None:
        """Record a successful fix attempt."""
        with self._lock:
            self._stats.total_attempts += 1
            self._stats.total_successes += 1
            self._stats.consecutive_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = datetime.now().isoformat()

            if self._state == CircuitState.HALF_OPEN:
                if self._stats.consecutive_successes >= self.half_open_success_threshold:
                    self._transition_to(CircuitState.CLOSED, "recovery_successful")

            self._save_state()

    def record_failure(self, error_message: Optional[str] = None) -> None:
        """Record a failed fix attempt.

        Args:
            error_message: Optional error message for logging
        """
        with self._lock:
            self._stats.total_attempts += 1
            self._stats.total_failures += 1
            self._stats.consecutive_failures += 1
            self._stats.consecutive_successes = 0
            self._stats.last_failure_time = datetime.now().isoformat()

            if self._state == CircuitState.CLOSED:
                if self._stats.consecutive_failures >= self.failure_threshold:
                    self._transition_to(
                        CircuitState.OPEN,
                        f"failure_threshold_reached ({self._stats.consecutive_failures} failures)",
                    )
            elif self._state == CircuitState.HALF_OPEN:
                # Immediately trip back to OPEN on failure in half-open
                self._transition_to(CircuitState.OPEN, "half_open_failure")

            self._save_state()

    def force_open(self, reason: str = "manual") -> None:
        """Force the circuit to open.

        Args:
            reason: Reason for forcing open
        """
        with self._lock:
            if self._state != CircuitState.OPEN:
                self._transition_to(CircuitState.OPEN, f"force_open: {reason}")

    def force_close(self, reason: str = "manual") -> None:
        """Force the circuit to close.

        Args:
            reason: Reason for forcing close
        """
        with self._lock:
            self._stats.consecutive_failures = 0
            self._transition_to(CircuitState.CLOSED, f"force_close: {reason}")

    def reset(self) -> None:
        """Reset the circuit breaker to initial state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._stats = CircuitStats()
            self._save_state()
            logger.info("Circuit breaker reset to initial state")

    def get_status(self) -> dict:
        """Get current circuit breaker status.

        Returns:
            Status dictionary
        """
        with self._lock:
            self._check_state_transition()

            time_until_half_open = None
            if self._state == CircuitState.OPEN and self._opened_at:
                elapsed = time.time() - self._opened_at
                remaining = self.reset_timeout_seconds - elapsed
                time_until_half_open = max(0, remaining)

            return {
                "state": self._state.value,
                "is_open": self._state == CircuitState.OPEN,
                "failure_threshold": self.failure_threshold,
                "consecutive_failures": self._stats.consecutive_failures,
                "time_until_half_open": time_until_half_open,
                "stats": self._stats.to_dict(),
            }


# ============================================================================
# Granular Circuit Breaker - Per-Error-Type Tracking
# ============================================================================


@dataclass
class ErrorTypeStats:
    """Statistics for a specific error type."""

    error_type: str
    total_attempts: int = 0
    total_successes: int = 0
    total_failures: int = 0
    window_results: list[bool] = field(default_factory=list)  # True=success, False=failure
    last_attempt_time: Optional[str] = None
    opened_at: Optional[float] = None  # When this error type's circuit opened
    state: CircuitState = CircuitState.CLOSED

    def to_dict(self) -> dict:
        return {
            "error_type": self.error_type,
            "total_attempts": self.total_attempts,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "window_size": len(self.window_results),
            "window_failures": self.window_results.count(False) if self.window_results else 0,
            "failure_rate": self.failure_rate,
            "last_attempt_time": self.last_attempt_time,
            "state": self.state.value,
        }

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate from sliding window."""
        if not self.window_results:
            return 0.0
        return self.window_results.count(False) / len(self.window_results)

    @classmethod
    def from_dict(cls, data: dict) -> "ErrorTypeStats":
        return cls(
            error_type=data.get("error_type", "unknown"),
            total_attempts=data.get("total_attempts", 0),
            total_successes=data.get("total_successes", 0),
            total_failures=data.get("total_failures", 0),
            window_results=data.get("window_results", []),
            last_attempt_time=data.get("last_attempt_time"),
            opened_at=data.get("opened_at"),
            state=CircuitState(data.get("state", "closed")),
        )


class GranularCircuitBreaker:
    """Circuit breaker with per-error-type tracking using sliding windows.

    Unlike the standard CircuitBreaker which tracks all failures together,
    this implementation tracks each error type separately. This allows
    the fixer to continue attempting fixes for error types it handles well,
    while blocking error types that consistently fail.

    Attributes:
        window_size: Number of recent attempts to consider for failure rate
        threshold: Failure rate (0-1) that triggers circuit opening
        reset_timeout_seconds: Time before attempting recovery for an error type
        min_attempts: Minimum attempts before circuit can open

    Example:
        gcb = GranularCircuitBreaker(workflow_dir, window_size=10, threshold=0.5)

        # Check if we should attempt fixing a SyntaxError
        if gcb.can_attempt("SyntaxError"):
            try:
                fix_syntax_error()
                gcb.record("SyntaxError", success=True)
            except Exception:
                gcb.record("SyntaxError", success=False)
    """

    def __init__(
        self,
        workflow_dir: str | Path,
        window_size: int = 10,
        threshold: float = 0.5,
        reset_timeout_seconds: int = 300,
        min_attempts: int = 3,
    ):
        """Initialize the granular circuit breaker.

        Args:
            workflow_dir: Directory for persisting state
            window_size: Number of recent attempts to track per error type
            threshold: Failure rate (0-1) that triggers circuit opening
            reset_timeout_seconds: Seconds before attempting recovery
            min_attempts: Minimum attempts before circuit can open
        """
        self.workflow_dir = Path(workflow_dir)
        self.state_file = self.workflow_dir / "fixer" / "granular_circuit_breaker.json"
        self.window_size = window_size
        self.threshold = threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.min_attempts = min_attempts

        self._lock = threading.Lock()
        self._error_stats: dict[str, ErrorTypeStats] = {}
        self._global_open = False  # Emergency global shutoff
        self._state_changes: list[dict] = []

        self._load_state()

    def _ensure_dir(self) -> None:
        """Ensure fixer directory exists."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> None:
        """Load circuit state from disk."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                    self._global_open = data.get("global_open", False)
                    self._state_changes = data.get("state_changes", [])[-20:]  # Keep last 20

                    for error_type, stats_data in data.get("error_stats", {}).items():
                        self._error_stats[error_type] = ErrorTypeStats.from_dict(stats_data)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Could not load granular circuit state: {e}")

    def _save_state(self) -> None:
        """Save circuit state to disk."""
        self._ensure_dir()
        data = {
            "global_open": self._global_open,
            "state_changes": self._state_changes[-20:],
            "error_stats": {
                error_type: stats.to_dict() for error_type, stats in self._error_stats.items()
            },
            "updated_at": datetime.now().isoformat(),
        }
        try:
            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logger.warning(f"Could not save granular circuit state: {e}")

    def _get_or_create_stats(self, error_type: str) -> ErrorTypeStats:
        """Get or create stats for an error type."""
        if error_type not in self._error_stats:
            self._error_stats[error_type] = ErrorTypeStats(error_type=error_type)
        return self._error_stats[error_type]

    def _check_error_type_transition(self, stats: ErrorTypeStats) -> None:
        """Check if an error type's circuit should transition.

        Called internally when checking if an attempt is allowed.
        """
        if stats.state == CircuitState.OPEN and stats.opened_at is not None:
            elapsed = time.time() - stats.opened_at
            if elapsed >= self.reset_timeout_seconds:
                self._transition_error_type(stats, CircuitState.HALF_OPEN, "timeout_expired")

    def _transition_error_type(
        self,
        stats: ErrorTypeStats,
        new_state: CircuitState,
        reason: str,
    ) -> None:
        """Transition an error type to a new state."""
        old_state = stats.state
        stats.state = new_state

        if new_state == CircuitState.OPEN:
            stats.opened_at = time.time()
        elif new_state == CircuitState.CLOSED:
            stats.opened_at = None

        # Record state change
        self._state_changes.append(
            {
                "error_type": stats.error_type,
                "from": old_state.value,
                "to": new_state.value,
                "reason": reason,
                "failure_rate": stats.failure_rate,
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.info(
            f"Granular circuit breaker [{stats.error_type}]: "
            f"{old_state.value} -> {new_state.value} ({reason})"
        )
        self._save_state()

    def can_attempt(self, error_type: str) -> bool:
        """Check if a fix attempt is allowed for this error type.

        Args:
            error_type: The type of error to check (e.g., "SyntaxError")

        Returns:
            True if fix can be attempted, False if circuit is open
        """
        with self._lock:
            # Check global shutoff
            if self._global_open:
                return False

            stats = self._get_or_create_stats(error_type)
            self._check_error_type_transition(stats)

            if stats.state == CircuitState.CLOSED:
                return True
            elif stats.state == CircuitState.HALF_OPEN:
                return True  # Allow test attempt
            else:  # OPEN
                return False

    def record(self, error_type: str, success: bool, error_message: Optional[str] = None) -> None:
        """Record the result of a fix attempt.

        Args:
            error_type: The type of error that was attempted
            success: Whether the fix succeeded
            error_message: Optional error message for logging
        """
        with self._lock:
            stats = self._get_or_create_stats(error_type)

            # Update totals
            stats.total_attempts += 1
            if success:
                stats.total_successes += 1
            else:
                stats.total_failures += 1

            stats.last_attempt_time = datetime.now().isoformat()

            # Update sliding window
            stats.window_results.append(success)
            if len(stats.window_results) > self.window_size:
                stats.window_results.pop(0)

            # Check for state transitions
            if stats.state == CircuitState.CLOSED:
                # Check if we should open the circuit
                if (
                    len(stats.window_results) >= self.min_attempts
                    and stats.failure_rate >= self.threshold
                ):
                    self._transition_error_type(
                        stats,
                        CircuitState.OPEN,
                        f"failure_rate={stats.failure_rate:.2f} >= threshold={self.threshold}",
                    )
            elif stats.state == CircuitState.HALF_OPEN:
                if success:
                    # Success in half-open - close the circuit
                    self._transition_error_type(stats, CircuitState.CLOSED, "recovery_successful")
                else:
                    # Failure in half-open - reopen
                    self._transition_error_type(stats, CircuitState.OPEN, "half_open_failure")

            self._save_state()

    def is_open(self, error_type: str) -> bool:
        """Check if the circuit is open for an error type.

        Args:
            error_type: The error type to check

        Returns:
            True if circuit is open (blocking fixes)
        """
        with self._lock:
            if self._global_open:
                return True

            stats = self._get_or_create_stats(error_type)
            self._check_error_type_transition(stats)
            return stats.state == CircuitState.OPEN

    def get_open_error_types(self) -> list[str]:
        """Get list of error types with open circuits.

        Returns:
            List of error type names that are currently blocked
        """
        with self._lock:
            open_types = []
            for error_type, stats in self._error_stats.items():
                self._check_error_type_transition(stats)
                if stats.state == CircuitState.OPEN:
                    open_types.append(error_type)
            return open_types

    def force_open_all(self, reason: str = "manual") -> None:
        """Force all circuits to open (emergency shutoff).

        Args:
            reason: Reason for the global shutoff
        """
        with self._lock:
            self._global_open = True
            self._state_changes.append(
                {
                    "error_type": "GLOBAL",
                    "from": "active",
                    "to": "shutdown",
                    "reason": f"force_open_all: {reason}",
                    "timestamp": datetime.now().isoformat(),
                }
            )
            logger.warning(f"Granular circuit breaker: GLOBAL SHUTOFF - {reason}")
            self._save_state()

    def force_close_all(self, reason: str = "manual") -> None:
        """Force all circuits to close (resume normal operation).

        Args:
            reason: Reason for resuming
        """
        with self._lock:
            self._global_open = False
            for stats in self._error_stats.values():
                if stats.state == CircuitState.OPEN:
                    stats.state = CircuitState.CLOSED
                    stats.opened_at = None
                    stats.window_results.clear()

            self._state_changes.append(
                {
                    "error_type": "GLOBAL",
                    "from": "shutdown",
                    "to": "active",
                    "reason": f"force_close_all: {reason}",
                    "timestamp": datetime.now().isoformat(),
                }
            )
            logger.info(f"Granular circuit breaker: ALL CIRCUITS CLOSED - {reason}")
            self._save_state()

    def reset(self, error_type: Optional[str] = None) -> None:
        """Reset circuit breaker state.

        Args:
            error_type: Specific error type to reset, or None for all
        """
        with self._lock:
            if error_type:
                if error_type in self._error_stats:
                    del self._error_stats[error_type]
                    logger.info(f"Reset granular circuit for: {error_type}")
            else:
                self._error_stats.clear()
                self._global_open = False
                self._state_changes.clear()
                logger.info("Reset all granular circuit breakers")

            self._save_state()

    def get_status(self) -> dict:
        """Get comprehensive circuit breaker status.

        Returns:
            Status dictionary with all error type states
        """
        with self._lock:
            # Update all transitions first
            for stats in self._error_stats.values():
                self._check_error_type_transition(stats)

            error_type_statuses = {}
            for error_type, stats in self._error_stats.items():
                time_until_half_open = None
                if stats.state == CircuitState.OPEN and stats.opened_at:
                    elapsed = time.time() - stats.opened_at
                    remaining = self.reset_timeout_seconds - elapsed
                    time_until_half_open = max(0, remaining)

                error_type_statuses[error_type] = {
                    "state": stats.state.value,
                    "is_open": stats.state == CircuitState.OPEN,
                    "failure_rate": stats.failure_rate,
                    "window_size": len(stats.window_results),
                    "time_until_half_open": time_until_half_open,
                    "stats": stats.to_dict(),
                }

            return {
                "global_open": self._global_open,
                "threshold": self.threshold,
                "window_size": self.window_size,
                "reset_timeout_seconds": self.reset_timeout_seconds,
                "error_types": error_type_statuses,
                "open_count": len(self.get_open_error_types()),
                "recent_state_changes": self._state_changes[-10:],
            }
