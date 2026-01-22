"""Async rate limiter module with token bucket algorithm.

Provides rate limiting for API calls to prevent overuse and control costs.
Supports per-minute/hour request limits, token limits, and cost limits.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    tokens_per_minute: int = 100000
    tokens_per_day: int = 1000000
    max_cost_per_hour: float = 10.0
    max_cost_per_day: float = 100.0
    burst_multiplier: float = 1.5
    backoff_base: float = 0.5  # Start at 0.5s for quicker initial recovery
    backoff_max: float = 60.0
    backoff_jitter: float = 0.25  # Add up to 25% jitter to prevent thundering herd


@dataclass
class RateLimitStats:
    """Statistics for rate limiting."""

    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    throttled_requests: int = 0
    current_rpm: float = 0.0
    current_tpm: float = 0.0
    last_request_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "throttled_requests": self.throttled_requests,
            "current_rpm": self.current_rpm,
            "current_tpm": self.current_tpm,
            "last_request_time": self.last_request_time.isoformat() if self.last_request_time else None,
        }


class TokenBucket:
    """Token bucket implementation for rate limiting."""

    def __init__(self, rate: float, capacity: float):
        """
        Initialize token bucket.

        Args:
            rate: Tokens per second to add
            capacity: Maximum tokens the bucket can hold
        """
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def available(self) -> float:
        """Get current available tokens."""
        return self._tokens

    async def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        tokens_to_add = elapsed * self.rate
        self._tokens = min(self.capacity, self._tokens + tokens_to_add)
        self._last_refill = now

    async def acquire(self, tokens: float = 1.0, wait: bool = True) -> bool:
        """
        Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire
            wait: Whether to wait if tokens unavailable

        Returns:
            True if tokens acquired, False otherwise
        """
        async with self._lock:
            await self._refill()

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True

            if not wait:
                return False

            # Calculate wait time
            tokens_needed = tokens - self._tokens
            wait_time = tokens_needed / self.rate

            await asyncio.sleep(wait_time)
            await self._refill()

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True

            return False


class RateLimitContext:
    """Context manager for rate-limited operations."""

    def __init__(self, limiter: "AsyncRateLimiter"):
        self._limiter = limiter
        self._entered = False

    async def __aenter__(self) -> "RateLimitContext":
        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._entered = False

    async def record_usage(self, tokens: int = 0, cost: float = 0.0) -> None:
        """Record token and cost usage."""
        await self._limiter.record_usage(tokens=tokens, cost=cost)


class AsyncRateLimiter:
    """Async rate limiter with multiple limit types."""

    def __init__(self, config: RateLimitConfig = None, name: str = "default"):
        """
        Initialize rate limiter.

        Args:
            config: Rate limit configuration
            name: Name for this limiter (for identification)
        """
        self.config = config or RateLimitConfig()
        self.name = name
        self.stats = RateLimitStats()

        # Token buckets for different limits
        self._rpm_bucket = TokenBucket(
            rate=self.config.requests_per_minute / 60.0,
            capacity=self.config.requests_per_minute * self.config.burst_multiplier,
        )
        self._tpm_bucket = TokenBucket(
            rate=self.config.tokens_per_minute / 60.0,
            capacity=self.config.tokens_per_minute * self.config.burst_multiplier,
        )

        # Request tracking
        self._minute_requests: List[datetime] = []
        self._hour_requests: List[datetime] = []
        self._minute_tokens: List[int] = []

        # Cost tracking
        self._hour_start = datetime.now()
        self._hour_cost = 0.0
        self._day_start = datetime.now()
        self._day_cost = 0.0

        # Track consecutive throttles for backoff (reset on success)
        self._consecutive_throttles = 0

        self._lock = asyncio.Lock()

    async def _cleanup_old_data(self) -> None:
        """Clean up old request/cost data."""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)

        # Clean minute data
        self._minute_requests = [r for r in self._minute_requests if r > minute_ago]

        # Clean hour data
        self._hour_requests = [r for r in self._hour_requests if r > hour_ago]

        # Reset hourly cost if hour passed
        if now - self._hour_start > timedelta(hours=1):
            self._hour_start = now
            self._hour_cost = 0.0

        # Reset daily cost if day passed
        if now - self._day_start > timedelta(days=1):
            self._day_start = now
            self._day_cost = 0.0

    async def _check_limits(self, estimated_tokens: int = 0) -> tuple[bool, str]:
        """
        Check if request is within limits.

        Returns:
            Tuple of (allowed, reason if not allowed)
        """
        await self._cleanup_old_data()

        # Check RPM
        if len(self._minute_requests) >= self.config.requests_per_minute:
            return False, "RPM limit exceeded"

        # Check hourly requests
        if len(self._hour_requests) >= self.config.requests_per_hour:
            return False, "Hourly request limit exceeded"

        # Check TPM
        current_minute_tokens = sum(self._minute_tokens) if hasattr(self, '_minute_tokens') else 0
        if current_minute_tokens + estimated_tokens > self.config.tokens_per_minute:
            return False, "TPM limit exceeded"

        # Check hourly cost
        if self._hour_cost >= self.config.max_cost_per_hour:
            return False, "Hourly cost limit exceeded"

        # Check daily cost
        if self._day_cost >= self.config.max_cost_per_day:
            return False, "Daily cost limit exceeded"

        return True, ""

    def _calculate_backoff(self) -> float:
        """Calculate backoff time with exponential increase and jitter.

        Uses consecutive throttles (reset on success) instead of cumulative
        to avoid excessive backoff after recovery. Adds jitter to prevent
        thundering herd when multiple coroutines are throttled simultaneously.

        Backoff progression (with 0.5s base, before jitter):
          - 0 consecutive: 0.5s
          - 1 consecutive: 0.75s
          - 2 consecutive: 1.125s
          - 5 consecutive: 3.8s
          - 10 consecutive: 28.8s (capped at backoff_max)

        Returns:
            Backoff time in seconds with jitter applied
        """
        # Cap the exponent to prevent excessive backoff
        throttle_count = min(self._consecutive_throttles, 10)
        base_backoff = self.config.backoff_base * (1.5 ** throttle_count)
        capped_backoff = min(base_backoff, self.config.backoff_max)

        # Add jitter to prevent synchronized retries
        jitter_range = capped_backoff * self.config.backoff_jitter
        jitter = random.uniform(-jitter_range, jitter_range)
        final_backoff = max(0.1, capped_backoff + jitter)  # Minimum 100ms

        if throttle_count > 0:
            logger.debug(
                f"Rate limit backoff: {final_backoff:.2f}s "
                f"(consecutive throttles: {throttle_count})"
            )

        return final_backoff

    async def acquire(
        self,
        estimated_tokens: int = 0,
        timeout: Optional[float] = None,
    ) -> RateLimitContext:
        """
        Acquire rate limit permission.

        Args:
            estimated_tokens: Estimated token usage
            timeout: Maximum time to wait

        Returns:
            RateLimitContext for the operation

        Raises:
            asyncio.TimeoutError: If timeout exceeded
        """
        start = time.monotonic()

        while True:
            async with self._lock:
                allowed, reason = await self._check_limits(estimated_tokens)

                if allowed:
                    # Record that we're starting a request
                    now = datetime.now()
                    self._minute_requests.append(now)
                    self._hour_requests.append(now)
                    # Reset consecutive throttles on success
                    self._consecutive_throttles = 0
                    return RateLimitContext(self)

                # Check timeout
                if timeout is not None:
                    elapsed = time.monotonic() - start
                    if elapsed >= timeout:
                        self.stats.throttled_requests += 1
                        self._consecutive_throttles += 1
                        raise asyncio.TimeoutError(f"Rate limit timeout: {reason}")

                # Track throttle for backoff calculation
                self.stats.throttled_requests += 1
                self._consecutive_throttles += 1

            # Sleep outside lock with exponential backoff
            # Uses consecutive throttle count (resets on success) for responsive recovery
            backoff_time = self._calculate_backoff()
            await asyncio.sleep(backoff_time)

    async def record_usage(self, tokens: int = 0, cost: float = 0.0) -> None:
        """
        Record usage after an operation.

        Args:
            tokens: Tokens used
            cost: Cost incurred
        """
        async with self._lock:
            now = datetime.now()

            # Update stats
            self.stats.total_requests += 1
            self.stats.total_tokens += tokens
            self.stats.total_cost += cost
            self.stats.last_request_time = now

            # Track for rate limiting
            self._minute_requests.append(now)
            self._hour_requests.append(now)

            if not hasattr(self, '_minute_tokens'):
                self._minute_tokens = []
            self._minute_tokens.append(tokens)

            # Update costs
            self._hour_cost += cost
            self._day_cost += cost

            # Update current rates
            self.stats.current_rpm = len(self._minute_requests)
            self.stats.current_tpm = sum(self._minute_tokens)

            # Cleanup old minute tokens
            minute_ago = now - timedelta(minutes=1)
            while self._minute_tokens and self._minute_requests and self._minute_requests[0] <= minute_ago:
                self._minute_requests.pop(0)
                self._minute_tokens.pop(0)

    def get_stats(self) -> RateLimitStats:
        """Get current statistics."""
        return self.stats

    async def wait_for_capacity(self, tokens: int = 0) -> None:
        """
        Wait until there's capacity for the requested tokens.

        Args:
            tokens: Tokens needed
        """
        while True:
            allowed, _ = await self._check_limits(tokens)
            if allowed:
                return
            await asyncio.sleep(0.1)


# Global rate limiter registry with thread safety
import threading
_rate_limiters: Dict[str, AsyncRateLimiter] = {}
_registry_lock = threading.Lock()


def get_rate_limiter(
    name: str,
    config: Optional[RateLimitConfig] = None,
) -> AsyncRateLimiter:
    """
    Get or create a rate limiter by name (thread-safe).

    Args:
        name: Limiter name
        config: Configuration (only used if creating new)

    Returns:
        AsyncRateLimiter instance
    """
    with _registry_lock:
        if name not in _rate_limiters:
            _rate_limiters[name] = AsyncRateLimiter(config=config, name=name)
        return _rate_limiters[name]


def get_all_rate_limiters() -> Dict[str, AsyncRateLimiter]:
    """Get all registered rate limiters (thread-safe)."""
    with _registry_lock:
        return dict(_rate_limiters)


# Predefined configurations for common services
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
    max_cost_per_hour=15.0,
    max_cost_per_day=150.0,
)
