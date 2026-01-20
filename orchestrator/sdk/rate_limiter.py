"""Async rate limiter for SDK API calls.

Implements token bucket algorithm with async support for
rate limiting API requests across multiple agents.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    # Request limits
    requests_per_minute: int = 60
    requests_per_hour: int = 1000

    # Token limits
    tokens_per_minute: int = 100000
    tokens_per_day: int = 1000000

    # Cost limits
    max_cost_per_hour: float = 10.0
    max_cost_per_day: float = 100.0

    # Behavior
    burst_multiplier: float = 1.5  # Allow burst up to this multiplier
    backoff_base: float = 1.0  # Base delay for backoff
    backoff_max: float = 60.0  # Maximum delay for backoff


@dataclass
class RateLimitStats:
    """Statistics for rate limiter monitoring."""

    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    throttled_requests: int = 0
    current_rpm: float = 0.0
    current_tpm: float = 0.0
    last_request_time: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "throttled_requests": self.throttled_requests,
            "current_rpm": self.current_rpm,
            "current_tpm": self.current_tpm,
            "last_request_time": self.last_request_time,
        }


class TokenBucket:
    """Token bucket implementation for rate limiting.

    Allows bursting up to capacity while maintaining average rate.
    """

    def __init__(
        self,
        rate: float,  # tokens per second
        capacity: float,  # maximum tokens
    ):
        """Initialize token bucket.

        Args:
            rate: Tokens added per second
            capacity: Maximum tokens in bucket
        """
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0, wait: bool = True) -> bool:
        """Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire
            wait: Whether to wait if tokens not available

        Returns:
            True if tokens acquired, False if not available and wait=False
        """
        async with self._lock:
            await self._refill()

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True

            if not wait:
                return False

            # Calculate wait time
            needed = tokens - self._tokens
            wait_time = needed / self.rate

            await asyncio.sleep(wait_time)
            await self._refill()
            self._tokens -= tokens
            return True

    async def _refill(self) -> None:
        """Refill tokens based on time elapsed."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_update = now

    @property
    def available(self) -> float:
        """Get current available tokens."""
        return self._tokens


class AsyncRateLimiter:
    """Async rate limiter for API calls.

    Features:
    - Token bucket algorithm for smooth rate limiting
    - Request and token-based limits
    - Cost tracking
    - Statistics and monitoring
    - Automatic backoff on rate limit errors

    Example:
        limiter = AsyncRateLimiter(
            config=RateLimitConfig(requests_per_minute=60)
        )

        async def make_api_call():
            async with limiter.acquire():
                response = await api.call()
                limiter.record_usage(tokens=response.tokens, cost=response.cost)
    """

    def __init__(
        self,
        config: Optional[RateLimitConfig] = None,
        name: str = "default",
    ):
        """Initialize rate limiter.

        Args:
            config: Rate limit configuration
            name: Name for this limiter (for logging)
        """
        self.config = config or RateLimitConfig()
        self.name = name

        # Create token buckets
        # Requests per minute bucket
        rpm_rate = self.config.requests_per_minute / 60.0
        rpm_capacity = self.config.requests_per_minute * self.config.burst_multiplier
        self._request_bucket = TokenBucket(rpm_rate, rpm_capacity)

        # Tokens per minute bucket
        tpm_rate = self.config.tokens_per_minute / 60.0
        tpm_capacity = self.config.tokens_per_minute * self.config.burst_multiplier
        self._token_bucket = TokenBucket(tpm_rate, tpm_capacity)

        # Tracking
        self._minute_requests: list[datetime] = []
        self._hour_requests: list[datetime] = []
        self._minute_tokens: list[tuple[datetime, int]] = []
        self._hour_cost: float = 0.0
        self._day_cost: float = 0.0
        self._hour_start: datetime = datetime.now()
        self._day_start: datetime = datetime.now()

        self.stats = RateLimitStats()
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        estimated_tokens: int = 0,
        timeout: Optional[float] = None,
    ) -> "RateLimitContext":
        """Acquire permission to make an API call.

        Args:
            estimated_tokens: Estimated tokens for the call
            timeout: Maximum time to wait for permission

        Returns:
            Context manager for the rate-limited call
        """
        start = time.monotonic()
        deadline = start + timeout if timeout else None

        while True:
            # Check if we can proceed
            allowed, reason = await self._check_limits(estimated_tokens)

            if allowed:
                # Acquire from request bucket
                remaining_time = deadline - time.monotonic() if deadline else None
                if remaining_time is not None and remaining_time <= 0:
                    raise asyncio.TimeoutError("Rate limit timeout")

                await self._request_bucket.acquire()

                # Acquire from token bucket if tokens estimated
                if estimated_tokens > 0:
                    await self._token_bucket.acquire(estimated_tokens)

                return RateLimitContext(self)

            # Calculate backoff
            self.stats.throttled_requests += 1
            backoff = self._calculate_backoff()

            if deadline:
                remaining_time = deadline - time.monotonic()
                if remaining_time <= 0:
                    raise asyncio.TimeoutError("Rate limit timeout")
                backoff = min(backoff, remaining_time)

            logger.warning(f"Rate limited ({self.name}): {reason}. Waiting {backoff:.1f}s")
            await asyncio.sleep(backoff)

    async def _check_limits(self, estimated_tokens: int = 0) -> tuple[bool, str]:
        """Check if current limits allow a request.

        Args:
            estimated_tokens: Estimated tokens for the call

        Returns:
            Tuple of (allowed, reason)
        """
        async with self._lock:
            await self._cleanup_old_data()

            now = datetime.now()

            # Check requests per minute
            minute_count = len(self._minute_requests)
            if minute_count >= self.config.requests_per_minute:
                return False, f"RPM limit ({self.config.requests_per_minute}) exceeded"

            # Check requests per hour
            hour_count = len(self._hour_requests)
            if hour_count >= self.config.requests_per_hour:
                return False, f"RPH limit ({self.config.requests_per_hour}) exceeded"

            # Check tokens per minute
            minute_tokens = sum(t for _, t in self._minute_tokens)
            if minute_tokens + estimated_tokens > self.config.tokens_per_minute:
                return False, f"TPM limit ({self.config.tokens_per_minute}) exceeded"

            # Check hourly cost
            if self._hour_cost >= self.config.max_cost_per_hour:
                return False, f"Hourly cost limit (${self.config.max_cost_per_hour}) exceeded"

            # Check daily cost
            if self._day_cost >= self.config.max_cost_per_day:
                return False, f"Daily cost limit (${self.config.max_cost_per_day}) exceeded"

            return True, "OK"

    async def _cleanup_old_data(self) -> None:
        """Clean up old tracking data."""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)

        self._minute_requests = [t for t in self._minute_requests if t > minute_ago]
        self._hour_requests = [t for t in self._hour_requests if t > hour_ago]
        self._minute_tokens = [(t, tokens) for t, tokens in self._minute_tokens if t > minute_ago]

        # Reset hourly cost
        if now - self._hour_start >= timedelta(hours=1):
            self._hour_cost = 0.0
            self._hour_start = now

        # Reset daily cost
        if now - self._day_start >= timedelta(days=1):
            self._day_cost = 0.0
            self._day_start = now

    def _calculate_backoff(self) -> float:
        """Calculate backoff time based on current throttling."""
        # Simple exponential backoff based on throttle count
        backoff = self.config.backoff_base * (1.5 ** min(self.stats.throttled_requests, 10))
        return min(backoff, self.config.backoff_max)

    async def record_usage(
        self,
        tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        """Record actual usage after a call completes.

        Args:
            tokens: Actual tokens used
            cost: Actual cost incurred
        """
        async with self._lock:
            now = datetime.now()

            self._minute_requests.append(now)
            self._hour_requests.append(now)

            if tokens > 0:
                self._minute_tokens.append((now, tokens))

            self._hour_cost += cost
            self._day_cost += cost

            # Update stats
            self.stats.total_requests += 1
            self.stats.total_tokens += tokens
            self.stats.total_cost += cost
            self.stats.last_request_time = now.isoformat()

            # Calculate current rates
            self.stats.current_rpm = len(self._minute_requests)
            self.stats.current_tpm = sum(t for _, t in self._minute_tokens)

    def get_stats(self) -> RateLimitStats:
        """Get current rate limiter statistics."""
        return self.stats

    async def wait_for_capacity(self, tokens: int = 0) -> None:
        """Wait until there is capacity for a request.

        Args:
            tokens: Required token capacity
        """
        while True:
            allowed, _ = await self._check_limits(tokens)
            if allowed:
                return
            await asyncio.sleep(self.config.backoff_base)


class RateLimitContext:
    """Context manager for rate-limited API calls."""

    def __init__(self, limiter: AsyncRateLimiter):
        self.limiter = limiter
        self._entered = False

    async def __aenter__(self) -> "RateLimitContext":
        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._entered = False

    async def record_usage(self, tokens: int = 0, cost: float = 0.0) -> None:
        """Record usage for this call."""
        await self.limiter.record_usage(tokens=tokens, cost=cost)


# Global rate limiters per service
_rate_limiters: dict[str, AsyncRateLimiter] = {}


def get_rate_limiter(
    name: str,
    config: Optional[RateLimitConfig] = None,
) -> AsyncRateLimiter:
    """Get or create a named rate limiter.

    Args:
        name: Unique name for the limiter (e.g., "claude", "gemini")
        config: Configuration (only used on creation)

    Returns:
        Rate limiter instance
    """
    if name not in _rate_limiters:
        _rate_limiters[name] = AsyncRateLimiter(config, name)
    return _rate_limiters[name]


def get_all_rate_limiters() -> dict[str, AsyncRateLimiter]:
    """Get all registered rate limiters."""
    return _rate_limiters.copy()


# Default configurations for common services
CLAUDE_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=60,
    requests_per_hour=1000,
    tokens_per_minute=100000,
    tokens_per_day=1000000,
    max_cost_per_hour=10.0,
    max_cost_per_day=100.0,
)

GEMINI_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=60,
    requests_per_hour=1500,
    tokens_per_minute=200000,
    tokens_per_day=2000000,
    max_cost_per_hour=5.0,
    max_cost_per_day=50.0,
)
