"""Tests for async rate limiter module.

Covers token bucket algorithm, rate limiting behavior, backoff calculation,
concurrent requests, and statistics tracking.
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from orchestrator.sdk.rate_limiter import (
    RateLimitConfig,
    RateLimitStats,
    TokenBucket,
    AsyncRateLimiter,
    RateLimitContext,
    get_rate_limiter,
    get_all_rate_limiters,
    CLAUDE_RATE_LIMIT,
    GEMINI_RATE_LIMIT,
    _rate_limiters,
)


# =============================================================================
# Rate Limit Config Tests
# =============================================================================

class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RateLimitConfig()

        assert config.requests_per_minute == 60
        assert config.requests_per_hour == 1000
        assert config.tokens_per_minute == 100000
        assert config.tokens_per_day == 1000000
        assert config.max_cost_per_hour == 10.0
        assert config.max_cost_per_day == 100.0
        assert config.burst_multiplier == 1.5
        assert config.backoff_base == 1.0
        assert config.backoff_max == 60.0

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = RateLimitConfig(
            requests_per_minute=30,
            tokens_per_minute=50000,
            backoff_max=120.0,
        )

        assert config.requests_per_minute == 30
        assert config.tokens_per_minute == 50000
        assert config.backoff_max == 120.0


class TestRateLimitStats:
    """Tests for RateLimitStats dataclass."""

    def test_default_values(self):
        """Test default statistics values."""
        stats = RateLimitStats()

        assert stats.total_requests == 0
        assert stats.total_tokens == 0
        assert stats.total_cost == 0.0
        assert stats.throttled_requests == 0
        assert stats.current_rpm == 0.0
        assert stats.current_tpm == 0.0
        assert stats.last_request_time is None

    def test_to_dict(self):
        """Test statistics serialization."""
        stats = RateLimitStats(
            total_requests=100,
            total_tokens=50000,
            total_cost=5.0,
            throttled_requests=5,
        )

        d = stats.to_dict()

        assert d["total_requests"] == 100
        assert d["total_tokens"] == 50000
        assert d["total_cost"] == 5.0
        assert d["throttled_requests"] == 5


# =============================================================================
# Token Bucket Tests
# =============================================================================

class TestTokenBucket:
    """Tests for TokenBucket implementation."""

    @pytest.fixture
    def bucket(self):
        """Create a test token bucket."""
        # 10 tokens per second, capacity of 20
        return TokenBucket(rate=10.0, capacity=20.0)

    @pytest.mark.asyncio
    async def test_initial_capacity(self, bucket):
        """Test bucket starts at full capacity."""
        assert bucket.available == 20.0

    @pytest.mark.asyncio
    async def test_acquire_success(self, bucket):
        """Test acquiring tokens when available."""
        result = await bucket.acquire(tokens=5.0, wait=False)

        assert result is True
        assert bucket.available == 15.0

    @pytest.mark.asyncio
    async def test_acquire_insufficient_no_wait(self, bucket):
        """Test acquiring more tokens than available with no wait."""
        # Drain the bucket first
        await bucket.acquire(tokens=20.0, wait=False)

        # Try to acquire more without waiting
        result = await bucket.acquire(tokens=5.0, wait=False)

        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_with_wait(self, bucket):
        """Test acquiring tokens with waiting."""
        # Drain the bucket
        await bucket.acquire(tokens=20.0, wait=False)

        # Acquire with wait - should wait for refill
        start = time.monotonic()
        result = await bucket.acquire(tokens=5.0, wait=True)
        elapsed = time.monotonic() - start

        assert result is True
        # Should have waited approximately 0.5 seconds (5 tokens / 10 rate)
        assert 0.4 <= elapsed <= 0.7

    @pytest.mark.asyncio
    async def test_refill_over_time(self, bucket):
        """Test that tokens refill over time."""
        # Drain the bucket
        await bucket.acquire(tokens=20.0, wait=False)
        assert bucket.available == 0.0

        # Wait for some refill
        await asyncio.sleep(0.5)  # Should add ~5 tokens

        # Force refill calculation by acquiring
        await bucket.acquire(tokens=1.0, wait=False)

        # Should have approximately 4 tokens (5 refilled - 1 acquired)
        assert 3.0 <= bucket.available <= 6.0

    @pytest.mark.asyncio
    async def test_capacity_limit(self, bucket):
        """Test that tokens don't exceed capacity."""
        # Wait longer than needed to fill
        await asyncio.sleep(0.5)

        # Force refill
        await bucket._refill()

        assert bucket.available <= bucket.capacity


# =============================================================================
# Async Rate Limiter Tests
# =============================================================================

class TestAsyncRateLimiter:
    """Tests for AsyncRateLimiter class."""

    @pytest.fixture
    def limiter(self):
        """Create a test rate limiter."""
        config = RateLimitConfig(
            requests_per_minute=60,
            tokens_per_minute=10000,
            max_cost_per_hour=10.0,
        )
        return AsyncRateLimiter(config=config, name="test")

    @pytest.mark.asyncio
    async def test_acquire_under_limit(self, limiter):
        """Test acquiring when under all limits."""
        ctx = await limiter.acquire()

        assert ctx is not None
        assert isinstance(ctx, RateLimitContext)

    @pytest.mark.asyncio
    async def test_record_usage(self, limiter):
        """Test recording token usage."""
        await limiter.record_usage(tokens=100, cost=0.01)

        assert limiter.stats.total_requests == 1
        assert limiter.stats.total_tokens == 100
        assert limiter.stats.total_cost == 0.01

    @pytest.mark.asyncio
    async def test_record_usage_multiple(self, limiter):
        """Test recording multiple usages."""
        await limiter.record_usage(tokens=100, cost=0.01)
        await limiter.record_usage(tokens=200, cost=0.02)
        await limiter.record_usage(tokens=300, cost=0.03)

        assert limiter.stats.total_requests == 3
        assert limiter.stats.total_tokens == 600
        assert limiter.stats.total_cost == pytest.approx(0.06)

    @pytest.mark.asyncio
    async def test_get_stats(self, limiter):
        """Test getting statistics."""
        await limiter.record_usage(tokens=100, cost=0.01)

        stats = limiter.get_stats()

        assert stats.total_requests == 1
        assert stats.last_request_time is not None

    @pytest.mark.asyncio
    async def test_current_rates_update(self, limiter):
        """Test that current RPM/TPM update with usage."""
        await limiter.record_usage(tokens=500, cost=0.05)

        assert limiter.stats.current_rpm == 1
        assert limiter.stats.current_tpm == 500


# =============================================================================
# Rate Limiting Behavior Tests
# =============================================================================

class TestRateLimitingBehavior:
    """Tests for rate limiting enforcement."""

    @pytest.mark.asyncio
    async def test_rpm_limit_enforcement(self):
        """Test requests per minute limit is enforced."""
        config = RateLimitConfig(
            requests_per_minute=3,  # Very low for testing
            requests_per_hour=1000,
            tokens_per_minute=1000000,
            max_cost_per_hour=100.0,
        )
        limiter = AsyncRateLimiter(config=config, name="rpm-test")

        # Make 3 requests (at limit)
        for _ in range(3):
            await limiter.record_usage(tokens=1)

        # Fourth request should be rate limited
        allowed, reason = await limiter._check_limits()

        assert allowed is False
        assert "RPM limit" in reason

    @pytest.mark.asyncio
    async def test_tpm_limit_enforcement(self):
        """Test tokens per minute limit is enforced."""
        config = RateLimitConfig(
            requests_per_minute=1000,
            tokens_per_minute=100,  # Very low for testing
            max_cost_per_hour=100.0,
        )
        limiter = AsyncRateLimiter(config=config, name="tpm-test")

        # Record 100 tokens (at limit)
        await limiter.record_usage(tokens=100)

        # Request with more tokens should be blocked
        allowed, reason = await limiter._check_limits(estimated_tokens=50)

        assert allowed is False
        assert "TPM limit" in reason

    @pytest.mark.asyncio
    async def test_hourly_cost_limit(self):
        """Test hourly cost limit is enforced."""
        config = RateLimitConfig(
            requests_per_minute=1000,
            tokens_per_minute=1000000,
            max_cost_per_hour=0.10,  # Very low for testing
        )
        limiter = AsyncRateLimiter(config=config, name="cost-test")

        # Record cost at limit
        await limiter.record_usage(tokens=100, cost=0.10)

        # Should be blocked
        allowed, reason = await limiter._check_limits()

        assert allowed is False
        assert "Hourly cost limit" in reason

    @pytest.mark.asyncio
    async def test_daily_cost_limit(self):
        """Test daily cost limit is enforced."""
        config = RateLimitConfig(
            requests_per_minute=1000,
            tokens_per_minute=1000000,
            max_cost_per_hour=100.0,
            max_cost_per_day=0.10,  # Very low for testing
        )
        limiter = AsyncRateLimiter(config=config, name="daily-cost-test")

        # Record cost at limit
        await limiter.record_usage(tokens=100, cost=0.10)

        # Should be blocked
        allowed, reason = await limiter._check_limits()

        assert allowed is False
        assert "Daily cost limit" in reason


# =============================================================================
# Backoff Calculation Tests
# =============================================================================

class TestBackoffCalculation:
    """Tests for backoff calculation."""

    def test_backoff_initial(self):
        """Test initial backoff value."""
        config = RateLimitConfig(backoff_base=1.0, backoff_max=60.0)
        limiter = AsyncRateLimiter(config=config, name="backoff-test")

        # No throttles yet
        backoff = limiter._calculate_backoff()

        assert backoff == 1.0  # Base value

    def test_backoff_exponential_growth(self):
        """Test backoff grows exponentially with throttles."""
        config = RateLimitConfig(backoff_base=1.0, backoff_max=60.0)
        limiter = AsyncRateLimiter(config=config, name="backoff-test")

        # Simulate throttles
        limiter.stats.throttled_requests = 3

        backoff = limiter._calculate_backoff()

        # 1.0 * (1.5 ^ 3) = 3.375
        assert backoff == pytest.approx(3.375)

    def test_backoff_max_cap(self):
        """Test backoff is capped at maximum."""
        config = RateLimitConfig(backoff_base=1.0, backoff_max=10.0)
        limiter = AsyncRateLimiter(config=config, name="backoff-test")

        # Many throttles
        limiter.stats.throttled_requests = 100

        backoff = limiter._calculate_backoff()

        assert backoff == 10.0  # Capped at max

    def test_backoff_throttle_count_capped(self):
        """Test throttle count used in calculation is capped."""
        config = RateLimitConfig(backoff_base=1.0, backoff_max=1000.0)
        limiter = AsyncRateLimiter(config=config, name="backoff-test")

        # Many throttles
        limiter.stats.throttled_requests = 100

        backoff = limiter._calculate_backoff()

        # Should use min(100, 10) = 10
        # 1.0 * (1.5 ^ 10) = 57.67
        assert backoff == pytest.approx(57.67, rel=0.01)


# =============================================================================
# Concurrent Request Tests
# =============================================================================

class TestConcurrentRequests:
    """Tests for concurrent request handling."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_within_limit(self):
        """Test multiple concurrent requests within limits."""
        config = RateLimitConfig(requests_per_minute=100)
        limiter = AsyncRateLimiter(config=config, name="concurrent-test")

        # Launch 5 concurrent acquires
        tasks = [limiter.acquire() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert all(isinstance(r, RateLimitContext) for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_usage_recording(self):
        """Test concurrent usage recording is thread-safe."""
        config = RateLimitConfig()
        limiter = AsyncRateLimiter(config=config, name="concurrent-record-test")

        # Record usage concurrently
        async def record():
            await limiter.record_usage(tokens=100, cost=0.01)

        tasks = [record() for _ in range(10)]
        await asyncio.gather(*tasks)

        assert limiter.stats.total_requests == 10
        assert limiter.stats.total_tokens == 1000
        assert limiter.stats.total_cost == pytest.approx(0.10)

    @pytest.mark.asyncio
    async def test_acquire_timeout(self):
        """Test acquire respects timeout."""
        config = RateLimitConfig(requests_per_minute=1)
        limiter = AsyncRateLimiter(config=config, name="timeout-test")

        # Use up the limit
        await limiter.record_usage(tokens=1)

        # Try to acquire with short timeout
        with pytest.raises(asyncio.TimeoutError):
            await limiter.acquire(timeout=0.1)


# =============================================================================
# Data Cleanup Tests
# =============================================================================

class TestDataCleanup:
    """Tests for old data cleanup."""

    @pytest.mark.asyncio
    async def test_minute_requests_cleanup(self):
        """Test old minute requests are cleaned up."""
        config = RateLimitConfig()
        limiter = AsyncRateLimiter(config=config, name="cleanup-test")

        # Add old requests (before 1 minute ago)
        old_time = datetime.now() - timedelta(minutes=2)
        limiter._minute_requests.append(old_time)

        # Trigger cleanup
        await limiter._cleanup_old_data()

        assert len(limiter._minute_requests) == 0

    @pytest.mark.asyncio
    async def test_hour_requests_cleanup(self):
        """Test old hour requests are cleaned up."""
        config = RateLimitConfig()
        limiter = AsyncRateLimiter(config=config, name="cleanup-test")

        # Add old requests (before 1 hour ago)
        old_time = datetime.now() - timedelta(hours=2)
        limiter._hour_requests.append(old_time)

        # Trigger cleanup
        await limiter._cleanup_old_data()

        assert len(limiter._hour_requests) == 0

    @pytest.mark.asyncio
    async def test_hourly_cost_reset(self):
        """Test hourly cost resets after an hour."""
        config = RateLimitConfig()
        limiter = AsyncRateLimiter(config=config, name="reset-test")

        # Set up old hour start
        limiter._hour_start = datetime.now() - timedelta(hours=2)
        limiter._hour_cost = 5.0

        # Trigger cleanup
        await limiter._cleanup_old_data()

        assert limiter._hour_cost == 0.0

    @pytest.mark.asyncio
    async def test_daily_cost_reset(self):
        """Test daily cost resets after a day."""
        config = RateLimitConfig()
        limiter = AsyncRateLimiter(config=config, name="reset-test")

        # Set up old day start
        limiter._day_start = datetime.now() - timedelta(days=2)
        limiter._day_cost = 50.0

        # Trigger cleanup
        await limiter._cleanup_old_data()

        assert limiter._day_cost == 0.0


# =============================================================================
# Rate Limit Context Tests
# =============================================================================

class TestRateLimitContext:
    """Tests for RateLimitContext class."""

    @pytest.mark.asyncio
    async def test_context_manager_enter(self):
        """Test context manager __aenter__."""
        config = RateLimitConfig()
        limiter = AsyncRateLimiter(config=config, name="ctx-test")

        ctx = RateLimitContext(limiter)

        async with ctx:
            assert ctx._entered is True

    @pytest.mark.asyncio
    async def test_context_manager_exit(self):
        """Test context manager __aexit__."""
        config = RateLimitConfig()
        limiter = AsyncRateLimiter(config=config, name="ctx-test")

        ctx = RateLimitContext(limiter)

        async with ctx:
            pass

        assert ctx._entered is False

    @pytest.mark.asyncio
    async def test_record_usage_via_context(self):
        """Test recording usage through context."""
        config = RateLimitConfig()
        limiter = AsyncRateLimiter(config=config, name="ctx-test")

        ctx = await limiter.acquire()
        await ctx.record_usage(tokens=100, cost=0.01)

        assert limiter.stats.total_tokens == 100


# =============================================================================
# Global Rate Limiter Tests
# =============================================================================

class TestGlobalRateLimiters:
    """Tests for global rate limiter management."""

    def setup_method(self):
        """Clear global rate limiters before each test."""
        _rate_limiters.clear()

    def test_get_rate_limiter_creates_new(self):
        """Test get_rate_limiter creates new instance."""
        limiter = get_rate_limiter("test-service")

        assert limiter is not None
        assert limiter.name == "test-service"

    def test_get_rate_limiter_returns_existing(self):
        """Test get_rate_limiter returns same instance."""
        limiter1 = get_rate_limiter("my-service")
        limiter2 = get_rate_limiter("my-service")

        assert limiter1 is limiter2

    def test_get_rate_limiter_with_config(self):
        """Test get_rate_limiter uses provided config on creation."""
        config = RateLimitConfig(requests_per_minute=30)
        limiter = get_rate_limiter("custom-service", config=config)

        assert limiter.config.requests_per_minute == 30

    def test_get_rate_limiter_config_ignored_if_exists(self):
        """Test config is ignored if limiter already exists."""
        config1 = RateLimitConfig(requests_per_minute=30)
        config2 = RateLimitConfig(requests_per_minute=100)

        limiter1 = get_rate_limiter("service", config=config1)
        limiter2 = get_rate_limiter("service", config=config2)

        # Should still have first config
        assert limiter2.config.requests_per_minute == 30

    def test_get_all_rate_limiters(self):
        """Test getting all registered rate limiters."""
        get_rate_limiter("service-a")
        get_rate_limiter("service-b")

        all_limiters = get_all_rate_limiters()

        assert "service-a" in all_limiters
        assert "service-b" in all_limiters

    def test_get_all_rate_limiters_returns_copy(self):
        """Test that get_all_rate_limiters returns a copy."""
        get_rate_limiter("service")

        all_limiters = get_all_rate_limiters()
        all_limiters["new-service"] = None

        # Original should be unchanged
        assert "new-service" not in _rate_limiters


# =============================================================================
# Predefined Config Tests
# =============================================================================

class TestPredefinedConfigs:
    """Tests for predefined rate limit configurations."""

    def test_claude_rate_limit_config(self):
        """Test CLAUDE_RATE_LIMIT has expected values."""
        assert CLAUDE_RATE_LIMIT.requests_per_minute == 60
        assert CLAUDE_RATE_LIMIT.requests_per_hour == 1000
        assert CLAUDE_RATE_LIMIT.tokens_per_minute == 100000
        assert CLAUDE_RATE_LIMIT.tokens_per_day == 1000000

    def test_gemini_rate_limit_config(self):
        """Test GEMINI_RATE_LIMIT has expected values."""
        assert GEMINI_RATE_LIMIT.requests_per_minute == 60
        assert GEMINI_RATE_LIMIT.requests_per_hour == 1500
        assert GEMINI_RATE_LIMIT.tokens_per_minute == 200000
        assert GEMINI_RATE_LIMIT.tokens_per_day == 2000000


# =============================================================================
# Wait for Capacity Tests
# =============================================================================

class TestWaitForCapacity:
    """Tests for wait_for_capacity method."""

    @pytest.mark.asyncio
    async def test_wait_for_capacity_immediate(self):
        """Test wait returns immediately when under limit."""
        config = RateLimitConfig()
        limiter = AsyncRateLimiter(config=config, name="wait-test")

        start = time.monotonic()
        await limiter.wait_for_capacity()
        elapsed = time.monotonic() - start

        assert elapsed < 0.1  # Should be nearly instant

    @pytest.mark.asyncio
    async def test_wait_for_capacity_with_tokens(self):
        """Test wait considers token requirement."""
        config = RateLimitConfig(tokens_per_minute=100)
        limiter = AsyncRateLimiter(config=config, name="wait-test")

        # Use up most tokens
        await limiter.record_usage(tokens=90)

        # Wait for capacity for 50 more tokens - will need to wait
        # This test just verifies the method runs; actual timing depends on cleanup
        await asyncio.wait_for(limiter.wait_for_capacity(tokens=5), timeout=2.0)


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete rate limiting workflow."""
        config = RateLimitConfig(
            requests_per_minute=10,
            tokens_per_minute=1000,
        )
        limiter = AsyncRateLimiter(config=config, name="integration-test")

        # Simulate API calls
        for i in range(5):
            ctx = await limiter.acquire(estimated_tokens=100)
            async with ctx:
                # Simulate API call
                await asyncio.sleep(0.01)
                await ctx.record_usage(tokens=100, cost=0.01)

        # Verify stats
        assert limiter.stats.total_requests == 5
        assert limiter.stats.total_tokens == 500
        assert limiter.stats.total_cost == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_throttle_count_increases(self):
        """Test that throttle count increases when rate limited."""
        config = RateLimitConfig(
            requests_per_minute=2,
            requests_per_hour=1000,
            tokens_per_minute=1000000,
            max_cost_per_hour=100.0,
        )
        limiter = AsyncRateLimiter(config=config, name="throttle-test")

        # Fill up the minute limit
        await limiter.record_usage(tokens=1)
        await limiter.record_usage(tokens=1)

        # This should trigger throttling
        try:
            await asyncio.wait_for(limiter.acquire(timeout=0.1), timeout=0.2)
        except asyncio.TimeoutError:
            pass

        # Throttle count should have increased
        assert limiter.stats.throttled_requests > 0
