"""Tests for error dispatch node.

Tests error_dispatch_node routing decisions.
"""

from datetime import datetime

import pytest

from orchestrator.langgraph.nodes.error_dispatch import (
    MAX_ERROR_RETRIES,
    SKIP_FIXER_ERROR_TYPES,
    error_dispatch_node,
)


class TestErrorDispatchNode:
    """Tests for error_dispatch_node."""

    @pytest.mark.asyncio
    async def test_routes_recoverable_error_to_fixer(
        self, minimal_workflow_state, sample_error_context
    ):
        """Test recoverable error routes to fixer."""
        minimal_workflow_state["error_context"] = sample_error_context
        minimal_workflow_state["fixer_enabled"] = True
        minimal_workflow_state["fixer_circuit_breaker_open"] = False

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_fixer"

    @pytest.mark.asyncio
    async def test_routes_to_human_when_fixer_disabled(
        self, minimal_workflow_state, sample_error_context
    ):
        """Test routes to human when fixer is disabled."""
        minimal_workflow_state["error_context"] = sample_error_context
        minimal_workflow_state["fixer_enabled"] = False

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_routes_to_human_when_circuit_breaker_open(
        self, minimal_workflow_state, sample_error_context
    ):
        """Test routes to human when circuit breaker is open."""
        minimal_workflow_state["error_context"] = sample_error_context
        minimal_workflow_state["fixer_enabled"] = True
        minimal_workflow_state["fixer_circuit_breaker_open"] = True

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_routes_permission_error_to_human(self, minimal_workflow_state):
        """Test PermissionError routes directly to human."""
        minimal_workflow_state["error_context"] = {
            "error_type": "PermissionError",
            "error_message": "Access denied to /etc/passwd",
            "source_node": "file_write",
            "recoverable": True,
            "retry_count": 0,
        }
        minimal_workflow_state["fixer_enabled"] = True

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_routes_authentication_error_to_human(self, minimal_workflow_state):
        """Test AuthenticationError routes directly to human."""
        minimal_workflow_state["error_context"] = {
            "error_type": "AuthenticationError",
            "error_message": "Invalid API key",
            "source_node": "api_call",
            "recoverable": True,
            "retry_count": 0,
        }
        minimal_workflow_state["fixer_enabled"] = True

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_routes_budget_exceeded_to_human(self, minimal_workflow_state):
        """Test BudgetExceededError routes directly to human."""
        minimal_workflow_state["error_context"] = {
            "error_type": "BudgetExceededError",
            "error_message": "Task budget of $5.00 exceeded",
            "source_node": "implementation",
            "recoverable": False,
            "retry_count": 0,
        }
        minimal_workflow_state["fixer_enabled"] = True

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_routes_circuit_breaker_error_to_human(self, minimal_workflow_state):
        """Test CircuitBreakerError routes directly to human."""
        minimal_workflow_state["error_context"] = {
            "error_type": "CircuitBreakerError",
            "error_message": "Fixer failed too many times",
            "source_node": "fixer",
            "recoverable": False,
            "retry_count": 5,
        }
        minimal_workflow_state["fixer_enabled"] = True

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_routes_non_recoverable_to_human(self, minimal_workflow_state):
        """Test non-recoverable error routes to human."""
        minimal_workflow_state["error_context"] = {
            "error_type": "CriticalError",
            "error_message": "Unrecoverable system error",
            "source_node": "core",
            "recoverable": False,
            "retry_count": 0,
        }
        minimal_workflow_state["fixer_enabled"] = True

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_routes_max_retries_to_human(self, minimal_workflow_state):
        """Test max retries exceeded routes to human."""
        minimal_workflow_state["error_context"] = {
            "error_type": "AssertionError",
            "error_message": "Test still failing",
            "source_node": "implementation",
            "recoverable": True,
            "retry_count": MAX_ERROR_RETRIES,  # At max
        }
        minimal_workflow_state["fixer_enabled"] = True

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_routes_timeout_error_to_fixer(self, minimal_workflow_state):
        """Test TimeoutError routes to fixer (recoverable)."""
        minimal_workflow_state["error_context"] = {
            "error_type": "TimeoutError",
            "error_message": "Agent timeout after 300s",
            "source_node": "implementation",
            "recoverable": True,
            "retry_count": 0,
        }
        minimal_workflow_state["fixer_enabled"] = True
        minimal_workflow_state["fixer_circuit_breaker_open"] = False

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_fixer"

    @pytest.mark.asyncio
    async def test_routes_assertion_error_to_fixer(self, minimal_workflow_state):
        """Test AssertionError routes to fixer (recoverable)."""
        minimal_workflow_state["error_context"] = {
            "error_type": "AssertionError",
            "error_message": "expected 5, got 3",
            "source_node": "verification",
            "recoverable": True,
            "retry_count": 1,
        }
        minimal_workflow_state["fixer_enabled"] = True
        minimal_workflow_state["fixer_circuit_breaker_open"] = False

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_fixer"

    @pytest.mark.asyncio
    async def test_handles_missing_error_context(self, minimal_workflow_state):
        """Test handles missing error context gracefully."""
        minimal_workflow_state["error_context"] = None
        minimal_workflow_state["fixer_enabled"] = True
        minimal_workflow_state["fixer_circuit_breaker_open"] = False

        result = await error_dispatch_node(minimal_workflow_state)

        # With no error context and fixer enabled, should try fixer
        assert result["next_decision"] == "use_fixer"

    @pytest.mark.asyncio
    async def test_updates_timestamp(self, minimal_workflow_state, sample_error_context):
        """Test result includes updated timestamp."""
        minimal_workflow_state["error_context"] = sample_error_context

        result = await error_dispatch_node(minimal_workflow_state)

        assert "updated_at" in result
        # Should be valid ISO timestamp
        datetime.fromisoformat(result["updated_at"])

    @pytest.mark.asyncio
    async def test_default_fixer_enabled(self, minimal_workflow_state, sample_error_context):
        """Test fixer is enabled by default."""
        minimal_workflow_state["error_context"] = sample_error_context
        # Don't set fixer_enabled explicitly

        result = await error_dispatch_node(minimal_workflow_state)

        # Should use fixer when not explicitly disabled
        assert result["next_decision"] == "use_fixer"


class TestSkipFixerErrorTypes:
    """Tests for SKIP_FIXER_ERROR_TYPES constant."""

    def test_contains_permission_error(self):
        """Test PermissionError is in skip list."""
        assert "PermissionError" in SKIP_FIXER_ERROR_TYPES

    def test_contains_authentication_error(self):
        """Test AuthenticationError is in skip list."""
        assert "AuthenticationError" in SKIP_FIXER_ERROR_TYPES

    def test_contains_budget_exceeded_error(self):
        """Test BudgetExceededError is in skip list."""
        assert "BudgetExceededError" in SKIP_FIXER_ERROR_TYPES

    def test_contains_circuit_breaker_error(self):
        """Test CircuitBreakerError is in skip list."""
        assert "CircuitBreakerError" in SKIP_FIXER_ERROR_TYPES

    def test_does_not_contain_timeout_error(self):
        """Test TimeoutError is not in skip list (recoverable)."""
        assert "TimeoutError" not in SKIP_FIXER_ERROR_TYPES

    def test_does_not_contain_assertion_error(self):
        """Test AssertionError is not in skip list (recoverable)."""
        assert "AssertionError" not in SKIP_FIXER_ERROR_TYPES


class TestMaxErrorRetries:
    """Tests for MAX_ERROR_RETRIES constant."""

    def test_max_retries_is_positive(self):
        """Test MAX_ERROR_RETRIES is a positive number."""
        assert MAX_ERROR_RETRIES > 0

    def test_max_retries_is_reasonable(self):
        """Test MAX_ERROR_RETRIES is a reasonable limit."""
        # Should be between 1 and 10
        assert 1 <= MAX_ERROR_RETRIES <= 10


class TestErrorDispatchDecisionPriority:
    """Tests for decision priority in error dispatch."""

    @pytest.mark.asyncio
    async def test_fixer_disabled_takes_priority_over_recoverable(self, minimal_workflow_state):
        """Test fixer disabled takes priority over recoverable status."""
        minimal_workflow_state["error_context"] = {
            "error_type": "TimeoutError",
            "error_message": "Timeout",
            "source_node": "test",
            "recoverable": True,
            "retry_count": 0,
        }
        minimal_workflow_state["fixer_enabled"] = False

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_circuit_breaker_takes_priority_over_recoverable(self, minimal_workflow_state):
        """Test circuit breaker takes priority over recoverable status."""
        minimal_workflow_state["error_context"] = {
            "error_type": "TimeoutError",
            "error_message": "Timeout",
            "source_node": "test",
            "recoverable": True,
            "retry_count": 0,
        }
        minimal_workflow_state["fixer_enabled"] = True
        minimal_workflow_state["fixer_circuit_breaker_open"] = True

        result = await error_dispatch_node(minimal_workflow_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_error_type_takes_priority_over_retry_count(self, minimal_workflow_state):
        """Test error type check happens before retry count check."""
        minimal_workflow_state["error_context"] = {
            "error_type": "PermissionError",
            "error_message": "Access denied",
            "source_node": "test",
            "recoverable": True,
            "retry_count": 0,  # Would normally use fixer
        }
        minimal_workflow_state["fixer_enabled"] = True
        minimal_workflow_state["fixer_circuit_breaker_open"] = False

        result = await error_dispatch_node(minimal_workflow_state)

        # Should go to human despite low retry count
        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_non_recoverable_takes_priority_over_retry_count(self, minimal_workflow_state):
        """Test non-recoverable check happens before retry count check."""
        minimal_workflow_state["error_context"] = {
            "error_type": "GenericError",
            "error_message": "Something broke",
            "source_node": "test",
            "recoverable": False,
            "retry_count": 0,  # Would normally use fixer
        }
        minimal_workflow_state["fixer_enabled"] = True
        minimal_workflow_state["fixer_circuit_breaker_open"] = False

        result = await error_dispatch_node(minimal_workflow_state)

        # Should go to human despite low retry count
        assert result["next_decision"] == "use_human"
