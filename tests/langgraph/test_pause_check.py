"""Tests for pause_check node."""

from datetime import datetime
from unittest.mock import patch

import pytest

from orchestrator.langgraph.nodes.pause_check import (
    pause_check_node,
    pause_router,
    should_check_pause,
)


class TestPauseCheckNode:
    """Tests for pause_check_node function."""

    @pytest.mark.asyncio
    async def test_no_pause_requested_continues(self):
        """Test that node continues when no pause requested."""
        state = {
            "pause_requested": False,
            "current_phase": 2,
        }

        result = await pause_check_node(state)

        assert "updated_at" in result
        # Should not have pause-related fields cleared (they weren't set)
        assert "next_decision" not in result

    @pytest.mark.asyncio
    async def test_pause_requested_false_by_default(self):
        """Test that missing pause_requested is treated as False."""
        state = {"current_phase": 1}

        result = await pause_check_node(state)

        assert "updated_at" in result
        assert "next_decision" not in result

    @pytest.mark.asyncio
    async def test_pause_requested_triggers_interrupt(self):
        """Test that pause_requested=True triggers interrupt."""
        state = {
            "pause_requested": True,
            "current_phase": 2,
            "paused_at_node": "validation",
            "pause_reason": "User requested pause",
            "paused_at_timestamp": "2026-01-26T10:00:00",
        }

        # Mock interrupt to return resume action
        with patch("orchestrator.langgraph.nodes.pause_check.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"action": "resume"}

            result = await pause_check_node(state)

            # Verify interrupt was called with correct params
            mock_interrupt.assert_called_once()
            call_args = mock_interrupt.call_args[0][0]
            assert call_args["type"] == "pause"
            assert call_args["paused_at_node"] == "validation"
            assert call_args["paused_at_phase"] == 2
            assert call_args["reason"] == "User requested pause"
            assert call_args["options"] == ["resume", "abort"]

            # Resume should clear pause flags
            assert result["pause_requested"] is False
            assert result["paused_at_node"] is None
            assert result["pause_reason"] is None

    @pytest.mark.asyncio
    async def test_abort_action_sets_next_decision(self):
        """Test that abort action sets next_decision to abort."""
        state = {
            "pause_requested": True,
            "current_phase": 3,
            "pause_reason": "Testing abort",
        }

        with patch("orchestrator.langgraph.nodes.pause_check.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"action": "abort"}

            result = await pause_check_node(state)

            assert result["next_decision"] == "abort"
            assert result["pause_requested"] is False
            assert result["paused_at_node"] is None

    @pytest.mark.asyncio
    async def test_none_response_defaults_to_resume(self):
        """Test that None response from interrupt defaults to resume."""
        state = {
            "pause_requested": True,
            "current_phase": 2,
        }

        with patch("orchestrator.langgraph.nodes.pause_check.interrupt") as mock_interrupt:
            mock_interrupt.return_value = None

            result = await pause_check_node(state)

            # Should resume (clear flags, no abort)
            assert result["pause_requested"] is False
            assert "next_decision" not in result or result.get("next_decision") != "abort"

    @pytest.mark.asyncio
    async def test_empty_response_defaults_to_resume(self):
        """Test that empty dict response defaults to resume."""
        state = {
            "pause_requested": True,
            "current_phase": 2,
        }

        with patch("orchestrator.langgraph.nodes.pause_check.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {}

            result = await pause_check_node(state)

            # Should resume (clear flags, no abort)
            assert result["pause_requested"] is False
            assert "next_decision" not in result

    @pytest.mark.asyncio
    async def test_updated_at_is_set(self):
        """Test that updated_at timestamp is always set."""
        state = {"pause_requested": False}

        result = await pause_check_node(state)

        assert "updated_at" in result
        # Should be a valid ISO format timestamp
        datetime.fromisoformat(result["updated_at"])


class TestShouldCheckPause:
    """Tests for should_check_pause function."""

    def test_returns_true_when_pause_requested(self):
        """Test returns True when pause_requested is True."""
        state = {"pause_requested": True}

        assert should_check_pause(state) is True

    def test_returns_false_when_not_requested(self):
        """Test returns False when pause_requested is False."""
        state = {"pause_requested": False}

        assert should_check_pause(state) is False

    def test_returns_false_when_missing(self):
        """Test returns False when pause_requested is missing."""
        state = {}

        assert should_check_pause(state) is False


class TestPauseRouter:
    """Tests for pause_router function."""

    def test_returns_pause_check_when_requested(self):
        """Test returns 'pause_check' when pause requested."""
        state = {"pause_requested": True}

        assert pause_router(state) == "pause_check"

    def test_returns_continue_when_not_requested(self):
        """Test returns 'continue' when no pause requested."""
        state = {"pause_requested": False}

        assert pause_router(state) == "continue"

    def test_returns_continue_when_missing(self):
        """Test returns 'continue' when pause_requested missing."""
        state = {}

        assert pause_router(state) == "continue"

    def test_with_other_state_fields(self):
        """Test router works with other state fields present."""
        state = {
            "pause_requested": True,
            "current_phase": 3,
            "project_name": "test-project",
            "errors": [],
        }

        assert pause_router(state) == "pause_check"


class TestPauseCheckIntegration:
    """Integration-style tests for pause check flow."""

    @pytest.mark.asyncio
    async def test_full_pause_resume_cycle(self):
        """Test a complete pause and resume cycle."""
        # Initial state with pause requested
        state = {
            "pause_requested": True,
            "current_phase": 2,
            "paused_at_node": "validation_fan_in",
            "pause_reason": "Need to review results",
            "paused_at_timestamp": datetime.now().isoformat(),
        }

        # First, router should direct to pause_check
        assert pause_router(state) == "pause_check"
        assert should_check_pause(state) is True

        # Then pause_check_node handles the pause
        with patch("orchestrator.langgraph.nodes.pause_check.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"action": "resume"}

            result = await pause_check_node(state)

            # All pause flags should be cleared
            assert result["pause_requested"] is False
            assert result["paused_at_node"] is None
            assert result["pause_reason"] is None
            assert result["paused_at_timestamp"] is None
            assert "updated_at" in result

        # After resume, state should allow normal routing
        resumed_state = {**state, **result}
        assert pause_router(resumed_state) == "continue"
        assert should_check_pause(resumed_state) is False

    @pytest.mark.asyncio
    async def test_full_pause_abort_cycle(self):
        """Test a complete pause and abort cycle."""
        state = {
            "pause_requested": True,
            "current_phase": 3,
            "paused_at_node": "implementation",
            "pause_reason": "Found critical issue",
        }

        with patch("orchestrator.langgraph.nodes.pause_check.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"action": "abort"}

            result = await pause_check_node(state)

            # Should set abort decision
            assert result["next_decision"] == "abort"
            # Pause flags should still be cleared
            assert result["pause_requested"] is False

    @pytest.mark.asyncio
    async def test_no_pause_fast_path(self):
        """Test fast path when no pause is requested."""
        state = {
            "pause_requested": False,
            "current_phase": 2,
            "project_name": "test-project",
        }

        # Router should skip pause_check
        assert pause_router(state) == "continue"

        # But if node is called anyway, it should be fast
        result = await pause_check_node(state)
        assert "updated_at" in result
        # No interrupt should be triggered (we can verify by not mocking)
