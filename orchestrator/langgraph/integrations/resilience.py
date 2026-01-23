"""Async resilience patterns for LangGraph workflows.

Provides async versions of circuit breaker and retry patterns
for use in async LangGraph nodes.
"""

import asyncio
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Optional, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


class AsyncCircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class AsyncCircuitBreakerConfig:
    """Configuration for async circuit breaker."""

    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 60.0
    excluded_exceptions: tuple = ()


@dataclass
class AsyncCircuitStats:
    """Statistics for async circuit breaker."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: Optional[str] = None
    last_success_time: Optional[str] = None
    current_state: str = "closed"

    @property
    def success_rate(self) -> float:
        total = self.successful_calls + self.failed_calls
        return self.successful_calls / total if total > 0 else 1.0


class AsyncCircuitBreakerError(Exception):
    """Raised when async circuit breaker is open."""

    pass


class AsyncCircuitBreaker:
    """Async circuit breaker for LangGraph nodes.

    Prevents cascading failures in async workflows by stopping
    requests to failing services.

    Example:
        breaker = AsyncCircuitBreaker("gemini-api")

        @breaker
        async def call_gemini(prompt: str) -> str:
            return await gemini_api.generate(prompt)

        # Or as context manager:
        async with breaker:
            result = await call_gemini(prompt)
    """

    def __init__(
        self,
        name: str,
        config: Optional[AsyncCircuitBreakerConfig] = None,
        fallback: Optional[Callable] = None,
    ):
        """Initialize async circuit breaker.

        Args:
            name: Identifier for this circuit breaker
            config: Configuration options
            fallback: Optional async fallback function
        """
        self.name = name
        self.config = config or AsyncCircuitBreakerConfig()
        self.fallback = fallback

        self._state = AsyncCircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._lock = asyncio.Lock()
        self.stats = AsyncCircuitStats()

    @property
    def state(self) -> AsyncCircuitState:
        """Get current state (non-async check)."""
        if self._state == AsyncCircuitState.OPEN:
            if self._last_failure_time:
                elapsed = datetime.now() - self._last_failure_time
                if elapsed >= timedelta(seconds=self.config.timeout_seconds):
                    # Will transition in next async call
                    return AsyncCircuitState.HALF_OPEN
        return self._state

    async def _check_and_update_state(self) -> AsyncCircuitState:
        """Check and update state (async)."""
        async with self._lock:
            if self._state == AsyncCircuitState.OPEN:
                if self._last_failure_time:
                    elapsed = datetime.now() - self._last_failure_time
                    if elapsed >= timedelta(seconds=self.config.timeout_seconds):
                        self._transition_to(AsyncCircuitState.HALF_OPEN)
            return self._state

    def _transition_to(self, new_state: AsyncCircuitState) -> None:
        """Transition to new state."""
        old_state = self._state
        self._state = new_state
        self.stats.state_changes += 1
        self.stats.current_state = new_state.value

        logger.info(
            f"Async circuit breaker '{self.name}': " f"{old_state.value} -> {new_state.value}"
        )

        if new_state == AsyncCircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == AsyncCircuitState.HALF_OPEN:
            self._success_count = 0

    async def _record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            self.stats.successful_calls += 1
            self.stats.last_success_time = datetime.now().isoformat()

            if self._state == AsyncCircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(AsyncCircuitState.CLOSED)

    async def _record_failure(self, exception: Exception) -> None:
        """Record a failed call."""
        async with self._lock:
            if isinstance(exception, self.config.excluded_exceptions):
                return

            self.stats.failed_calls += 1
            self.stats.last_failure_time = datetime.now().isoformat()
            self._last_failure_time = datetime.now()

            if self._state == AsyncCircuitState.HALF_OPEN:
                self._transition_to(AsyncCircuitState.OPEN)
            elif self._state == AsyncCircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(AsyncCircuitState.OPEN)

    async def __aenter__(self) -> "AsyncCircuitBreaker":
        """Async context manager entry."""
        self.stats.total_calls += 1

        state = await self._check_and_update_state()
        if state == AsyncCircuitState.OPEN:
            self.stats.rejected_calls += 1
            raise AsyncCircuitBreakerError(f"Async circuit breaker '{self.name}' is OPEN")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Async context manager exit."""
        if exc_type is None:
            await self._record_success()
        elif exc_val is not None:
            await self._record_failure(exc_val)
        return False

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator for async functions."""

        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                async with self:
                    return await func(*args, **kwargs)
            except AsyncCircuitBreakerError:
                if self.fallback:
                    if asyncio.iscoroutinefunction(self.fallback):
                        return await self.fallback(*args, **kwargs)
                    return self.fallback(*args, **kwargs)
                raise

        return wrapper

    async def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        async with self._lock:
            self._transition_to(AsyncCircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None


@dataclass
class AsyncRetryConfig:
    """Configuration for async retry."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = (Exception,)


def async_retry_with_backoff(
    config: Optional[AsyncRetryConfig] = None,
) -> Callable:
    """Decorator for async retry with exponential backoff.

    Example:
        @async_retry_with_backoff(AsyncRetryConfig(max_attempts=5))
        async def call_api():
            return await api.request()
    """
    config = config or AsyncRetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt == config.max_attempts - 1:
                        break

                    delay = min(
                        config.base_delay * (config.exponential_base**attempt),
                        config.max_delay,
                    )

                    if config.jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"Async retry {attempt + 1}/{config.max_attempts} "
                        f"for {func.__name__} after {delay:.2f}s. Error: {e}"
                    )
                    await asyncio.sleep(delay)

            raise last_exception

        return wrapper

    return decorator


# Global async circuit breaker registry
_async_circuit_breakers: dict[str, AsyncCircuitBreaker] = {}


def get_async_circuit_breaker(
    name: str,
    config: Optional[AsyncCircuitBreakerConfig] = None,
    fallback: Optional[Callable] = None,
) -> AsyncCircuitBreaker:
    """Get or create a named async circuit breaker.

    Args:
        name: Unique identifier
        config: Configuration (only for new)
        fallback: Fallback function (only for new)

    Returns:
        AsyncCircuitBreaker instance
    """
    if name not in _async_circuit_breakers:
        _async_circuit_breakers[name] = AsyncCircuitBreaker(name, config, fallback)
    return _async_circuit_breakers[name]


def clear_circuit_breakers() -> int:
    """Clear all registered circuit breakers.

    Call this at workflow initialization and cleanup to prevent memory leaks
    from accumulated circuit breaker instances.

    Returns:
        Number of circuit breakers cleared
    """
    global _async_circuit_breakers
    count = len(_async_circuit_breakers)
    _async_circuit_breakers.clear()
    logger.info(f"Cleared {count} circuit breakers from registry")
    return count


async def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers to closed state.

    Useful for recovery after cascading failures are resolved.
    """
    for name, breaker in _async_circuit_breakers.items():
        await breaker.reset()
        logger.debug(f"Reset circuit breaker: {name}")


# Pre-configured circuit breakers for common services
CLAUDE_CIRCUIT_BREAKER = AsyncCircuitBreaker(
    "claude-sdk",
    AsyncCircuitBreakerConfig(
        failure_threshold=3,
        success_threshold=2,
        timeout_seconds=30.0,
    ),
)

GEMINI_CIRCUIT_BREAKER = AsyncCircuitBreaker(
    "gemini-sdk",
    AsyncCircuitBreakerConfig(
        failure_threshold=3,
        success_threshold=2,
        timeout_seconds=30.0,
    ),
)

CURSOR_CIRCUIT_BREAKER = AsyncCircuitBreaker(
    "cursor-cli",
    AsyncCircuitBreakerConfig(
        failure_threshold=5,
        success_threshold=2,
        timeout_seconds=60.0,
    ),
)


# Pre-configured retry configs
SDK_RETRY_CONFIG = AsyncRetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    jitter=True,
)

CLI_RETRY_CONFIG = AsyncRetryConfig(
    max_attempts=2,
    base_delay=2.0,
    max_delay=60.0,
    jitter=True,
)
