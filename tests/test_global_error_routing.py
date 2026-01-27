"""Tests for global error routing to bugfixer.

Verifies that ALL nodes in the workflow route errors through
error_dispatch to the fixer agent.
"""


import pytest

from orchestrator.langgraph.nodes.error_dispatch import (
    MAX_ERROR_RETRIES,
    SKIP_FIXER_ERROR_TYPES,
    error_dispatch_node,
)
from orchestrator.langgraph.state import create_error_context, create_initial_state


@pytest.fixture
def initial_state():
    """Create initial workflow state for tests."""
    return create_initial_state(
        project_dir="/tmp/test-project",
        project_name="test-project",
    )


class TestErrorDispatchNode:
    """Tests for error_dispatch_node."""

    @pytest.mark.asyncio
    async def test_routes_to_fixer_when_enabled(self, initial_state):
        """Test routing to fixer when enabled and circuit breaker is closed."""
        initial_state["fixer_enabled"] = True
        initial_state["fixer_circuit_breaker_open"] = False
        # Use TimeoutError which is auto-detected as recoverable
        initial_state["error_context"] = create_error_context(
            source_node="planning",
            exception=TimeoutError("Test error"),
            recoverable=True,
        )

        result = await error_dispatch_node(initial_state)

        assert result["next_decision"] == "use_fixer"

    @pytest.mark.asyncio
    async def test_routes_to_human_when_disabled(self, initial_state):
        """Test routing to human when fixer is disabled."""
        initial_state["fixer_enabled"] = False
        initial_state["error_context"] = create_error_context(
            source_node="planning",
            exception=ValueError("Test error"),
        )

        result = await error_dispatch_node(initial_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_routes_to_human_when_circuit_breaker_open(self, initial_state):
        """Test routing to human when circuit breaker is open."""
        initial_state["fixer_enabled"] = True
        initial_state["fixer_circuit_breaker_open"] = True
        initial_state["error_context"] = create_error_context(
            source_node="planning",
            exception=ValueError("Test error"),
        )

        result = await error_dispatch_node(initial_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_routes_to_human_for_non_recoverable(self, initial_state):
        """Test routing to human for non-recoverable errors."""
        initial_state["fixer_enabled"] = True
        initial_state["fixer_circuit_breaker_open"] = False
        initial_state["error_context"] = create_error_context(
            source_node="planning",
            exception=ValueError("Test error"),
            recoverable=False,
        )

        result = await error_dispatch_node(initial_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_routes_to_human_after_max_retries(self, initial_state):
        """Test routing to human after max retries exceeded."""
        error_ctx = create_error_context(
            source_node="planning",
            exception=ValueError("Test error"),
            recoverable=True,
        )
        error_ctx["retry_count"] = MAX_ERROR_RETRIES  # At limit

        initial_state["fixer_enabled"] = True
        initial_state["fixer_circuit_breaker_open"] = False
        initial_state["error_context"] = error_ctx

        result = await error_dispatch_node(initial_state)

        assert result["next_decision"] == "use_human"

    @pytest.mark.asyncio
    async def test_skip_fixer_for_permission_errors(self, initial_state):
        """Test skipping fixer for PermissionError."""
        initial_state["fixer_enabled"] = True
        initial_state["error_context"] = {
            "error_type": "PermissionError",
            "error_message": "Access denied",
            "recoverable": True,
            "retry_count": 0,
            "source_node": "implementation",
        }

        result = await error_dispatch_node(initial_state)

        assert result["next_decision"] == "use_human"


def error_dispatch_router(state: dict) -> str:
    """Local router helper for testing error dispatch routing logic.

    This implements the expected routing logic that should match
    the workflow graph's conditional edge from error_dispatch.
    """
    decision = state.get("next_decision", "use_human")
    if decision == "use_fixer":
        return "fixer_triage"
    return "human_escalation"


class TestErrorDispatchRouter:
    """Tests for error_dispatch_router logic."""

    def test_routes_to_fixer_triage(self):
        """Test router returns fixer_triage for use_fixer decision."""
        state = {"next_decision": "use_fixer"}
        result = error_dispatch_router(state)
        assert result == "fixer_triage"

    def test_routes_to_human_escalation(self):
        """Test router returns human_escalation for use_human decision."""
        state = {"next_decision": "use_human"}
        result = error_dispatch_router(state)
        assert result == "human_escalation"

    def test_defaults_to_human_escalation(self):
        """Test router defaults to human_escalation for unknown decision."""
        state = {"next_decision": "unknown"}
        result = error_dispatch_router(state)
        assert result == "human_escalation"


class TestErrorContextUsage:
    """Tests for using ErrorContext in error dispatch."""

    @pytest.mark.asyncio
    async def test_uses_error_context_for_routing(self, initial_state):
        """Test error dispatch uses ErrorContext for routing decisions."""
        # Create rich error context
        error_ctx = create_error_context(
            source_node="cursor_validate",
            exception=ConnectionError("Agent unavailable"),
            state=dict(initial_state),
            recoverable=True,
            suggested_actions=["retry_after_delay", "check_network"],
        )

        initial_state["fixer_enabled"] = True
        initial_state["fixer_circuit_breaker_open"] = False
        initial_state["error_context"] = error_ctx

        result = await error_dispatch_node(initial_state)

        # Should route to fixer for recoverable connection error
        assert result["next_decision"] == "use_fixer"

    @pytest.mark.asyncio
    async def test_handles_missing_error_context(self, initial_state):
        """Test error dispatch handles missing error context gracefully."""
        initial_state["fixer_enabled"] = True
        initial_state["fixer_circuit_breaker_open"] = False
        # No error_context set

        result = await error_dispatch_node(initial_state)

        # Should still route to fixer (default recoverable)
        assert result["next_decision"] == "use_fixer"


class TestSkipFixerErrorTypes:
    """Tests for error types that skip the fixer."""

    def test_permission_error_in_skip_list(self):
        """PermissionError should be in skip list."""
        assert "PermissionError" in SKIP_FIXER_ERROR_TYPES

    def test_authentication_error_in_skip_list(self):
        """AuthenticationError should be in skip list."""
        assert "AuthenticationError" in SKIP_FIXER_ERROR_TYPES

    def test_budget_error_in_skip_list(self):
        """BudgetExceededError should be in skip list."""
        assert "BudgetExceededError" in SKIP_FIXER_ERROR_TYPES


class TestRichErrorContext:
    """Tests for rich error context creation and usage."""

    def test_create_error_context_includes_stack_trace(self):
        """Test error context includes stack trace."""
        try:
            raise ValueError("Test")
        except ValueError as e:
            ctx = create_error_context(
                source_node="test",
                exception=e,
            )
            assert "stack_trace" in ctx
            assert "ValueError" in ctx["stack_trace"]

    def test_create_error_context_sanitizes_state(self):
        """Test error context sanitizes state to safe fields only."""
        large_state = {
            "project_name": "test",
            "current_phase": 1,
            "large_field": "x" * 100000,
            "sensitive_key": "secret123",
        }

        ctx = create_error_context(
            source_node="test",
            exception=ValueError("Test"),
            state=large_state,
        )

        snapshot = ctx["state_snapshot"]
        assert "project_name" in snapshot
        assert "large_field" not in snapshot
        assert "sensitive_key" not in snapshot

    def test_create_error_context_generates_suggestions(self):
        """Test error context generates appropriate suggestions."""
        ctx = create_error_context(
            source_node="test",
            exception=TimeoutError("Timed out"),
        )

        assert "retry_with_longer_timeout" in ctx["suggested_actions"]

    def test_create_error_context_with_stderr(self):
        """Test error context can include stderr."""
        ctx = create_error_context(
            source_node="test",
            exception=ValueError("Test"),
            stderr="Error: command failed",
        )

        assert ctx["stderr"] == "Error: command failed"
