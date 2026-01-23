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
