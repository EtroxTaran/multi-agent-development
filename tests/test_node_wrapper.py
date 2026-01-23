"""Tests for universal node wrapper."""

import asyncio

import pytest

from orchestrator.langgraph.state import create_initial_state
from orchestrator.langgraph.wrappers import (
    AGENT_NODES,
    NodeWrapper,
    get_node_metadata,
    wrapped_node,
)


@pytest.fixture
def initial_state():
    """Create initial workflow state for tests."""
    return create_initial_state(
        project_dir="/tmp/test-project",
        project_name="test-project",
    )


class TestWrappedNodeDecorator:
    """Tests for the @wrapped_node decorator."""

    def test_decorator_without_parentheses(self):
        """Test decorator used without parentheses."""

        @wrapped_node
        async def my_node(state):
            return {"status": "ok"}

        assert isinstance(my_node, NodeWrapper)
        assert my_node.node_name == "my_node"

    def test_decorator_with_parentheses(self):
        """Test decorator used with explicit parameters."""

        @wrapped_node(name="custom_name", agent="claude", template="planning")
        async def planning_node(state):
            return {"status": "ok"}

        assert isinstance(planning_node, NodeWrapper)
        assert planning_node.node_name == "custom_name"
        assert planning_node.agent == "claude"
        assert planning_node.template == "planning"

    def test_auto_detect_agent_info(self):
        """Test auto-detection of agent info from AGENT_NODES registry."""

        @wrapped_node
        async def planning(state):  # Name matches AGENT_NODES key
            return {"status": "ok"}

        # Should auto-detect from AGENT_NODES
        assert planning.agent == "claude"
        assert planning.template == "planning"


class TestNodeWrapperExecution:
    """Tests for NodeWrapper execution behavior."""

    @pytest.mark.asyncio
    async def test_successful_execution(self, initial_state):
        """Test wrapper handles successful execution."""

        @wrapped_node
        async def my_node(state):
            return {"result": "success", "next_decision": "continue"}

        result = await my_node(initial_state)

        assert result["result"] == "success"
        assert result["next_decision"] == "continue"

    @pytest.mark.asyncio
    async def test_exception_handling(self, initial_state):
        """Test wrapper catches exceptions and creates ErrorContext."""

        @wrapped_node
        async def failing_node(state):
            raise ValueError("Something went wrong")

        result = await failing_node(initial_state)

        # Should have error context
        assert "error_context" in result
        error_ctx = result["error_context"]
        assert error_ctx["source_node"] == "failing_node"
        assert error_ctx["error_type"] == "ValueError"
        assert "Something went wrong" in error_ctx["error_message"]
        assert "stack_trace" in error_ctx

        # Should have errors list
        assert "errors" in result
        assert len(result["errors"]) == 1
        assert result["errors"][0]["type"] == "ValueError"

        # Should set next_decision to escalate
        assert result["next_decision"] == "escalate"

    @pytest.mark.asyncio
    async def test_agent_execution_tracking(self, initial_state):
        """Test wrapper tracks agent execution for agent nodes."""

        @wrapped_node(agent="claude", template="planning")
        async def agent_node(state):
            return {
                "_prompt": "Test prompt",
                "_output": "Test output",
                "_exit_code": 0,
                "result": "done",
            }

        result = await agent_node(initial_state)

        # Should have execution tracking
        assert "last_agent_execution" in result
        execution = result["last_agent_execution"]
        assert execution["agent"] == "claude"
        assert execution["template_name"] == "planning"
        assert execution["success"] is True

        # Should have execution history
        assert "execution_history" in result
        assert len(result["execution_history"]) == 1

    @pytest.mark.asyncio
    async def test_failed_agent_execution_tracking(self, initial_state):
        """Test wrapper tracks failed agent execution."""

        @wrapped_node(agent="cursor", template="validation")
        async def failing_agent_node(state):
            raise ConnectionError("Agent unavailable")

        result = await failing_agent_node(initial_state)

        # Should have execution tracking for failure
        assert "last_agent_execution" in result
        execution = result["last_agent_execution"]
        assert execution["agent"] == "cursor"
        assert execution["success"] is False
        assert execution["error_context"] is not None

    @pytest.mark.asyncio
    async def test_sync_function_support(self, initial_state):
        """Test wrapper works with sync functions."""

        @wrapped_node
        def sync_node(state):
            return {"result": "sync_ok"}

        # Should still work (wrapper detects sync vs async)
        result = await sync_node(initial_state)
        assert result["result"] == "sync_ok"


class TestRecoverableErrors:
    """Tests for error recoverability detection."""

    @pytest.mark.asyncio
    async def test_recoverable_timeout_error(self, initial_state):
        """TimeoutError should be marked as recoverable."""

        @wrapped_node
        async def timeout_node(state):
            raise TimeoutError("Operation timed out")

        result = await timeout_node(initial_state)
        assert result["error_context"]["recoverable"] is True
        assert "retry_with_longer_timeout" in result["error_context"]["suggested_actions"]

    @pytest.mark.asyncio
    async def test_recoverable_connection_error(self, initial_state):
        """ConnectionError should be marked as recoverable."""

        @wrapped_node
        async def connection_node(state):
            raise ConnectionError("Network error")

        result = await connection_node(initial_state)
        assert result["error_context"]["recoverable"] is True
        assert "retry_after_delay" in result["error_context"]["suggested_actions"]

    @pytest.mark.asyncio
    async def test_recoverable_assertion_error(self, initial_state):
        """AssertionError (test failure) should be recoverable."""

        @wrapped_node
        async def test_node(state):
            raise AssertionError("Expected 5, got 3")

        result = await test_node(initial_state)
        assert result["error_context"]["recoverable"] is True
        assert "iterate_with_ralph_loop" in result["error_context"]["suggested_actions"]


class TestNodeRegistry:
    """Tests for node metadata registry."""

    def test_agent_nodes_defined(self):
        """Test AGENT_NODES has expected entries."""
        assert "planning" in AGENT_NODES
        assert "cursor_validate" in AGENT_NODES
        assert "gemini_validate" in AGENT_NODES
        assert "implement_task" in AGENT_NODES
        assert "cursor_review" in AGENT_NODES
        assert "gemini_review" in AGENT_NODES

    def test_get_node_metadata(self):
        """Test retrieving node metadata."""

        @wrapped_node(agent="claude", template="test")
        async def test_node(state):
            return {}

        metadata = get_node_metadata("test_node")
        assert metadata["agent"] == "claude"
        assert metadata["template"] == "test"
        assert metadata["is_agent_node"] is True

    def test_get_unknown_node_metadata(self):
        """Test retrieving metadata for unknown node."""
        metadata = get_node_metadata("nonexistent_node")
        assert metadata is None


class TestErrorContext:
    """Tests for ErrorContext creation."""

    def test_error_context_structure(self, initial_state):
        """Test ErrorContext has all required fields."""

        @wrapped_node
        async def error_node(state):
            raise RuntimeError("Test error")

        result = asyncio.get_event_loop().run_until_complete(error_node(initial_state))

        error_ctx = result["error_context"]

        # Check required fields
        assert "error_id" in error_ctx
        assert "source_node" in error_ctx
        assert "error_type" in error_ctx
        assert "error_message" in error_ctx
        assert "stack_trace" in error_ctx
        assert "timestamp" in error_ctx
        assert "recoverable" in error_ctx
        assert "suggested_actions" in error_ctx

    def test_state_snapshot_sanitization(self, initial_state):
        """Test state snapshot is sanitized (no large fields)."""

        # Add large field to state
        initial_state["large_output"] = "x" * 100000

        @wrapped_node
        async def error_node(state):
            raise ValueError("Test")

        result = asyncio.get_event_loop().run_until_complete(error_node(initial_state))

        # State snapshot should only have safe fields
        snapshot = result["error_context"]["state_snapshot"]
        assert "large_output" not in snapshot
        assert "project_name" in snapshot or len(snapshot) == 0
