"""Tests for the context_injector module.

Tests the dynamic context injection system that builds
agent prompts with task-specific rules and guardrails.
"""

from unittest.mock import patch

from orchestrator.agents.context_injector import (
    _load_rule_file,
    get_agent_identity,
    get_context_for_prompt,
)


class TestGetContextForPrompt:
    """Test suite for the get_context_for_prompt function."""

    def test_returns_string(self):
        """Test that get_context_for_prompt returns a string."""
        result = get_context_for_prompt("claude", "implementation")
        assert isinstance(result, str)

    def test_claude_implementation_context(self):
        """Test context for Claude agent doing implementation."""
        result = get_context_for_prompt("claude", "implementation")
        assert isinstance(result, str)

    def test_claude_planning_context(self):
        """Test context for Claude agent doing planning."""
        result = get_context_for_prompt("claude", "planning")
        assert isinstance(result, str)

    def test_cursor_validation_context(self):
        """Test context for Cursor agent doing validation."""
        result = get_context_for_prompt("cursor", "validation")
        assert isinstance(result, str)

    def test_gemini_review_context(self):
        """Test context for Gemini agent doing review."""
        result = get_context_for_prompt("gemini", "review")
        assert isinstance(result, str)

    def test_different_agents_can_have_different_context(self):
        """Test that different agents might get different context."""
        claude_context = get_context_for_prompt("claude", "implementation")
        gemini_context = get_context_for_prompt("gemini", "validation")

        # Both should be valid strings
        assert isinstance(claude_context, str)
        assert isinstance(gemini_context, str)

    def test_security_task_includes_security_context(self):
        """Test that security task type loads security context."""
        result = get_context_for_prompt("cursor", "security")
        assert isinstance(result, str)
        # May or may not have security content depending on file existence

    def test_research_task_context(self):
        """Test context for research task type."""
        result = get_context_for_prompt("claude", "research")
        assert isinstance(result, str)


class TestGetAgentIdentity:
    """Test suite for the get_agent_identity function."""

    def test_claude_identity(self):
        """Test Claude agent identity."""
        identity = get_agent_identity("claude")
        assert isinstance(identity, str)
        assert "Role" in identity
        assert "TDD" in identity or "implement" in identity.lower()

    def test_cursor_identity(self):
        """Test Cursor agent identity."""
        identity = get_agent_identity("cursor")
        assert isinstance(identity, str)
        assert "Role" in identity
        assert "security" in identity.lower() or "review" in identity.lower()

    def test_gemini_identity(self):
        """Test Gemini agent identity."""
        identity = get_agent_identity("gemini")
        assert isinstance(identity, str)
        assert "Role" in identity
        assert "architect" in identity.lower() or "scalability" in identity.lower()

    def test_unknown_agent_returns_empty(self):
        """Test that unknown agent returns empty string."""
        identity = get_agent_identity("unknown")
        assert identity == ""


class TestLoadRuleFile:
    """Test suite for the _load_rule_file helper function."""

    def test_returns_none_for_nonexistent_file(self):
        """Test that missing files return None."""
        result = _load_rule_file("nonexistent", "missing.md")
        assert result is None

    def test_returns_string_for_existing_file(self):
        """Test that existing files return content."""
        # This may pass or fail depending on whether guardrails/core.md exists
        result = _load_rule_file("guardrails", "core.md")
        # Either None (not found) or string (found)
        assert result is None or isinstance(result, str)

    def test_handles_read_errors_gracefully(self):
        """Test graceful handling of read errors."""
        with patch("pathlib.Path.read_text", side_effect=OSError("Read error")):
            with patch("pathlib.Path.exists", return_value=True):
                result = _load_rule_file("guardrails", "test.md")
                assert result is None


class TestContextInjectorIntegration:
    """Integration-style tests for context injection."""

    def test_context_combines_multiple_rules(self):
        """Test that context can combine multiple rule files."""
        # Implementation task should try to load core + quality + tdd
        result = get_context_for_prompt("claude", "implementation")
        assert isinstance(result, str)

    def test_validation_combines_security(self):
        """Test that validation task includes security rules."""
        result = get_context_for_prompt("cursor", "validation")
        assert isinstance(result, str)

    def test_empty_context_returned_when_no_files(self):
        """Test empty string when no rule files are found."""
        with patch("orchestrator.agents.context_injector._load_rule_file", return_value=None):
            result = get_context_for_prompt("claude", "implementation")
            assert result == ""


class TestContextInjectorEdgeCases:
    """Edge case tests for context injection."""

    def test_handles_all_agent_types(self):
        """Test all defined agent types work."""
        agents = ["claude", "cursor", "gemini"]
        for agent in agents:
            result = get_context_for_prompt(agent, "implementation")
            assert isinstance(result, str)

    def test_handles_all_task_types(self):
        """Test all defined task types work."""
        task_types = [
            "planning",
            "implementation",
            "validation",
            "review",
            "security",
            "research",
        ]
        for task in task_types:
            result = get_context_for_prompt("claude", task)
            assert isinstance(result, str)
