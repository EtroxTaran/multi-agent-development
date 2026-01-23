"""Resilience patterns for multi-agent systems.

Implements:
- Circuit Breaker: Prevent cascading failures
- Retry with Exponential Backoff: Handle transient failures
- Bulkhead: Isolate failures
- Timeout: Bound execution time
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Optional, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests flow through
    OPEN = "open"  # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3  # Successes to close from half-open
    timeout_seconds: int = 60  # Time before trying half-open
    excluded_exceptions: tuple = ()  # Exceptions that don't count as failures


@dataclass
class CircuitStats:
    """Statistics for circuit breaker monitoring."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: Optional[str] = None
    last_success_time: Optional[str] = None
    current_state: str = "closed"

    def to_dict(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "rejected_calls": self.rejected_calls,
            "state_changes": self.state_changes,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "current_state": self.current_state,
            "success_rate": self.success_rate,
        }

    @property
    def success_rate(self) -> float:
        total = self.successful_calls + self.failed_calls
        return self.successful_calls / total if total > 0 else 1.0


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    pass


class CircuitBreaker:
    """Circuit breaker pattern implementation.

    Prevents cascading failures by stopping requests to failing services.

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Service failing, all requests blocked
    - HALF_OPEN: Testing recovery, limited requests allowed

    Example:
        breaker = CircuitBreaker("gemini-api")

        @breaker
        def call_gemini(prompt):
            return gemini_api.generate(prompt)

        # Or manually:
        try:
            with breaker:
                result = call_gemini(prompt)
        except CircuitBreakerError:
            result = fallback_response()
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        fallback: Optional[Callable] = None,
    ):
        """Initialize circuit breaker.

        Args:
            name: Identifier for this circuit breaker
            config: Configuration options
            fallback: Optional fallback function when circuit is open
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.fallback = fallback

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._lock = threading.RLock()
        self.stats = CircuitStats()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, auto-transitioning if needed."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if timeout has passed
                if self._last_failure_time:
                    elapsed = datetime.now() - self._last_failure_time
                    if elapsed >= timedelta(seconds=self.config.timeout_seconds):
                        self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self.stats.state_changes += 1
        self.stats.current_state = new_state.value

        logger.info(
            f"Circuit breaker '{self.name}' transitioned: "
            f"{old_state.value} -> {new_state.value}"
        )

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0

    def _record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self.stats.successful_calls += 1
            self.stats.last_success_time = datetime.now().isoformat()

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def _record_failure(self, exception: Exception) -> None:
        """Record a failed call."""
        with self._lock:
            # Check if exception should be excluded
            if isinstance(exception, self.config.excluded_exceptions):
                return

            self.stats.failed_calls += 1
            self.stats.last_failure_time = datetime.now().isoformat()
            self._last_failure_time = datetime.now()

            if self._state == CircuitState.HALF_OPEN:
                # Immediate transition back to open
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def __enter__(self) -> "CircuitBreaker":
        """Context manager entry."""
        self.stats.total_calls += 1

        if self.state == CircuitState.OPEN:
            self.stats.rejected_calls += 1
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is OPEN. " f"Service temporarily unavailable."
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit."""
        if exc_type is None:
            self._record_success()
        elif exc_val is not None:
            self._record_failure(exc_val)

        # Don't suppress exceptions
        return False

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to wrap function with circuit breaker."""

        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                with self:
                    return func(*args, **kwargs)
            except CircuitBreakerError:
                if self.fallback:
                    return self.fallback(*args, **kwargs)
                raise

        return wrapper

    def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None

    def get_stats(self) -> CircuitStats:
        """Get circuit breaker statistics."""
        return self.stats


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: tuple = (Exception,),
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions


def retry_with_backoff(
    config: Optional[RetryConfig] = None,
) -> Callable:
    """Decorator for retry with exponential backoff.

    Example:
        @retry_with_backoff(RetryConfig(max_attempts=5))
        def call_api():
            return api.request()
    """
    config = config or RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt == config.max_attempts - 1:
                        # Last attempt, don't sleep
                        break

                    # Calculate delay with exponential backoff
                    delay = min(
                        config.base_delay * (config.exponential_base**attempt),
                        config.max_delay,
                    )

                    # Add jitter to prevent thundering herd
                    if config.jitter:
                        import random

                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"Retry {attempt + 1}/{config.max_attempts} for {func.__name__} "
                        f"after {delay:.2f}s delay. Error: {e}"
                    )
                    time.sleep(delay)

            # All retries exhausted
            raise last_exception

        return wrapper

    return decorator


@dataclass
class ExecutionLimit:
    """Execution limits for cost control."""

    max_calls_per_minute: int = 60
    max_calls_per_hour: int = 1000
    max_tokens_per_request: int = 100000
    max_cost_per_hour: float = 10.0
    timeout_seconds: int = 300


class ExecutionLimiter:
    """Enforces execution limits to prevent runaway costs.

    Tracks:
    - API calls per minute/hour
    - Token usage
    - Cost accumulation
    - Execution time
    """

    def __init__(self, limits: Optional[ExecutionLimit] = None):
        self.limits = limits or ExecutionLimit()
        self._minute_calls: list[datetime] = []
        self._hour_calls: list[datetime] = []
        self._hour_cost: float = 0.0
        self._hour_start: datetime = datetime.now()
        self._lock = threading.RLock()

    def _cleanup_old_calls(self) -> None:
        """Remove calls outside the tracking window."""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)

        self._minute_calls = [t for t in self._minute_calls if t > minute_ago]
        self._hour_calls = [t for t in self._hour_calls if t > hour_ago]

        # Reset hourly cost if hour has passed
        if now - self._hour_start >= timedelta(hours=1):
            self._hour_cost = 0.0
            self._hour_start = now

    def check_limits(self, estimated_cost: float = 0.0) -> tuple[bool, str]:
        """Check if execution is within limits.

        Args:
            estimated_cost: Estimated cost for this call

        Returns:
            Tuple of (allowed, reason)
        """
        with self._lock:
            self._cleanup_old_calls()

            # Check calls per minute
            if len(self._minute_calls) >= self.limits.max_calls_per_minute:
                return (
                    False,
                    f"Rate limit: {self.limits.max_calls_per_minute} calls/minute exceeded",
                )

            # Check calls per hour
            if len(self._hour_calls) >= self.limits.max_calls_per_hour:
                return False, f"Rate limit: {self.limits.max_calls_per_hour} calls/hour exceeded"

            # Check cost per hour
            if self._hour_cost + estimated_cost > self.limits.max_cost_per_hour:
                return False, f"Cost limit: ${self.limits.max_cost_per_hour}/hour exceeded"

            return True, "OK"

    def record_call(self, cost: float = 0.0) -> None:
        """Record an API call."""
        with self._lock:
            now = datetime.now()
            self._minute_calls.append(now)
            self._hour_calls.append(now)
            self._hour_cost += cost

    def get_usage(self) -> dict:
        """Get current usage statistics."""
        with self._lock:
            self._cleanup_old_calls()
            return {
                "calls_this_minute": len(self._minute_calls),
                "calls_this_hour": len(self._hour_calls),
                "cost_this_hour": self._hour_cost,
                "minute_limit": self.limits.max_calls_per_minute,
                "hour_limit": self.limits.max_calls_per_hour,
                "cost_limit": self.limits.max_cost_per_hour,
            }


def timeout(seconds: int) -> Callable:
    """Decorator to add timeout to function execution.

    Note: Only works on Unix-like systems with signal support.

    Example:
        @timeout(30)
        def long_running_task():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            import signal

            def handler(signum, frame):
                raise TimeoutError(f"Function {func.__name__} timed out after {seconds}s")

            # Set the signal handler
            old_handler = signal.signal(signal.SIGALRM, handler)
            signal.alarm(seconds)

            try:
                return func(*args, **kwargs)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper

    return decorator


# Global circuit breaker registry
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None,
    fallback: Optional[Callable] = None,
) -> CircuitBreaker:
    """Get or create a named circuit breaker.

    Args:
        name: Unique identifier for the circuit breaker
        config: Configuration (only used if creating new)
        fallback: Fallback function (only used if creating new)

    Returns:
        Circuit breaker instance
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config, fallback)
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
    """Get all registered circuit breakers."""
    return _circuit_breakers.copy()
