"""Tests for fixer circuit breaker."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from orchestrator.fixer.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitStats,
)


class TestCircuitStats:
    """Tests for CircuitStats dataclass."""

    def test_to_dict(self):
        stats = CircuitStats(
            total_attempts=10,
            total_successes=7,
            total_failures=3,
        )
        result = stats.to_dict()
        assert result["total_attempts"] == 10
        assert result["total_successes"] == 7
        assert result["total_failures"] == 3

    def test_from_dict(self):
        data = {
            "total_attempts": 5,
            "consecutive_failures": 2,
        }
        stats = CircuitStats.from_dict(data)
        assert stats.total_attempts == 5
        assert stats.consecutive_failures == 2


class TestCircuitBreakerInit:
    """Tests for CircuitBreaker initialization."""

    def test_init_creates_state_file(self, tmp_path):
        """Circuit breaker creates state file on init."""
        cb = CircuitBreaker(tmp_path, failure_threshold=3)
        # Force a state save
        cb.record_success()
        assert (tmp_path / "fixer" / "circuit_breaker.json").exists()

    def test_init_loads_existing_state(self, tmp_path):
        """Circuit breaker loads existing state from disk."""
        # Create initial state file
        fixer_dir = tmp_path / "fixer"
        fixer_dir.mkdir(parents=True)
        state_file = fixer_dir / "circuit_breaker.json"
        state_file.write_text(json.dumps({
            "state": "open",
            "opened_at": time.time() - 1000,  # Far in the past
            "stats": {"consecutive_failures": 5},
        }))

        cb = CircuitBreaker(tmp_path, failure_threshold=3)
        # State should be HALF_OPEN since timeout expired
        assert cb.state in (CircuitState.OPEN, CircuitState.HALF_OPEN)


class TestCircuitBreakerCanAttempt:
    """Tests for can_attempt method."""

    def test_can_attempt_when_closed(self, tmp_path):
        """Can attempt when circuit is closed."""
        cb = CircuitBreaker(tmp_path)
        assert cb.can_attempt() is True

    def test_cannot_attempt_when_open(self, tmp_path):
        """Cannot attempt when circuit is open."""
        cb = CircuitBreaker(tmp_path, failure_threshold=2)
        # Trip the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.can_attempt() is False

    def test_can_attempt_when_half_open(self, tmp_path):
        """Can attempt when circuit is half-open (testing recovery)."""
        cb = CircuitBreaker(tmp_path, failure_threshold=2, reset_timeout_seconds=0)
        # Trip circuit
        cb.record_failure()
        cb.record_failure()
        # Wait for timeout (0 seconds)
        time.sleep(0.01)
        # Should transition to half-open
        assert cb.can_attempt() is True


class TestCircuitBreakerRecordSuccess:
    """Tests for record_success method."""

    def test_success_when_closed(self, tmp_path):
        """Success increments counters when closed."""
        cb = CircuitBreaker(tmp_path)
        cb.record_success()
        assert cb.stats.total_successes == 1
        assert cb.stats.consecutive_successes == 1

    def test_success_clears_failure_count(self, tmp_path):
        """Success resets consecutive failure count."""
        cb = CircuitBreaker(tmp_path, failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.stats.consecutive_failures == 0

    def test_success_when_half_open_partial(self, tmp_path):
        """Success in half-open doesn't close immediately."""
        cb = CircuitBreaker(
            tmp_path,
            failure_threshold=2,
            reset_timeout_seconds=0,
            half_open_success_threshold=2,
        )
        # Trip and wait
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)
        _ = cb.can_attempt()  # Trigger transition to half-open

        cb.record_success()
        # Still half-open (need 2 successes)
        assert cb.state == CircuitState.HALF_OPEN

    def test_success_when_half_open_closes(self, tmp_path):
        """Enough successes in half-open closes circuit."""
        cb = CircuitBreaker(
            tmp_path,
            failure_threshold=2,
            reset_timeout_seconds=0,
            half_open_success_threshold=2,
        )
        # Trip and wait
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)
        _ = cb.can_attempt()

        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerRecordFailure:
    """Tests for record_failure method."""

    def test_failure_increments_count(self, tmp_path):
        """Failure increments consecutive failure count."""
        cb = CircuitBreaker(tmp_path, failure_threshold=5)
        cb.record_failure()
        assert cb.stats.consecutive_failures == 1
        cb.record_failure()
        assert cb.stats.consecutive_failures == 2

    def test_failure_trips_circuit(self, tmp_path):
        """Enough failures trips the circuit."""
        cb = CircuitBreaker(tmp_path, failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_failure_in_half_open_reopens(self, tmp_path):
        """Failure in half-open reopens circuit immediately."""
        cb = CircuitBreaker(
            tmp_path,
            failure_threshold=2,
            reset_timeout_seconds=300,  # Use longer timeout
        )
        # Trip the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb._state == CircuitState.OPEN

        # Manually transition to half-open for testing
        cb._state = CircuitState.HALF_OPEN
        cb._stats.consecutive_successes = 0

        # Failure in half-open should reopen immediately
        cb.record_failure()
        assert cb._state == CircuitState.OPEN


class TestCircuitBreakerReset:
    """Tests for reset method."""

    def test_reset_clears_state(self, tmp_path):
        """Reset returns circuit to initial state."""
        cb = CircuitBreaker(tmp_path, failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.stats.consecutive_failures == 0


class TestCircuitBreakerGetStatus:
    """Tests for get_status method."""

    def test_get_status_closed(self, tmp_path):
        """Status shows closed state."""
        cb = CircuitBreaker(tmp_path, failure_threshold=5)
        status = cb.get_status()
        assert status["state"] == "closed"
        assert status["is_open"] is False

    def test_get_status_open(self, tmp_path):
        """Status shows open state with time until recovery."""
        cb = CircuitBreaker(tmp_path, failure_threshold=2, reset_timeout_seconds=300)
        cb.record_failure()
        cb.record_failure()
        status = cb.get_status()
        assert status["state"] == "open"
        assert status["is_open"] is True
        assert status["time_until_half_open"] is not None
        assert status["time_until_half_open"] > 0


class TestCircuitBreakerPersistence:
    """Tests for state persistence."""

    def test_state_persists_across_instances(self, tmp_path):
        """State persists when creating new instance."""
        cb1 = CircuitBreaker(tmp_path, failure_threshold=3)
        cb1.record_failure()
        cb1.record_failure()

        # Create new instance pointing to same directory
        cb2 = CircuitBreaker(tmp_path, failure_threshold=3)
        assert cb2.stats.consecutive_failures == 2

    def test_state_file_is_valid_json(self, tmp_path):
        """State file is valid JSON."""
        cb = CircuitBreaker(tmp_path)
        cb.record_success()

        state_file = tmp_path / "fixer" / "circuit_breaker.json"
        data = json.loads(state_file.read_text())
        assert "state" in data
        assert "stats" in data


class TestCircuitBreakerForce:
    """Tests for force_open and force_close."""

    def test_force_open(self, tmp_path):
        """Force open the circuit."""
        cb = CircuitBreaker(tmp_path)
        assert cb.state == CircuitState.CLOSED
        cb.force_open("testing")
        assert cb.state == CircuitState.OPEN

    def test_force_close(self, tmp_path):
        """Force close the circuit."""
        cb = CircuitBreaker(tmp_path, failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.force_close("testing")
        assert cb.state == CircuitState.CLOSED
