"""Tests for context injector module.

Tests the context injection system that loads context from collection/rules/
and injects into prompts at invocation time.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.agents.context_injector import (
    AgentType,
    TaskType,
    get_agent_identity,
    get_context_for_prompt,
)


class TestGetAgentIdentity:
    """Tests for get_agent_identity function."""

    def test_claude_identity(self):
        """Test Claude agent identity."""
        identity = get_agent_identity("claude")

        assert "Your Role" in identity
        assert "TDD" in identity
        assert len(identity) > 0

    def test_cursor_identity(self):
        """Test Cursor agent identity."""
        identity = get_agent_identity("cursor")

        assert "Your Role" in identity
        assert "Code Reviewer" in identity
        assert "OWASP" in identity or "security" in identity.lower()

    def test_gemini_identity(self):
        """Test Gemini agent identity."""
        identity = get_agent_identity("gemini")

        assert "Your Role" in identity
        assert "Architect" in identity
        assert "scalability" in identity.lower() or "architecture" in identity.lower()

    def test_unknown_agent_returns_empty(self):
        """Test that unknown agent returns empty string."""
        identity = get_agent_identity("unknown")
        assert identity == ""


class TestGetContextForPrompt:
    """Tests for get_context_for_prompt function."""

    def test_returns_string(self):
        """Test that function returns a string."""
        result = get_context_for_prompt("claude", "planning")
        assert isinstance(result, str)

    def test_claude_implementation_includes_tdd(self):
        """Test Claude implementation context includes TDD rules."""
        with patch("orchestrator.agents.context_injector._load_rule_file") as mock_load:
            mock_load.return_value = "# TDD Rules\nTest first"

            get_context_for_prompt("claude", "implementation")

            # Should have called for TDD workflow
            calls = [str(call) for call in mock_load.call_args_list]
            assert any("tdd" in str(call).lower() for call in calls)

    def test_cursor_validation_includes_security(self):
        """Test Cursor validation context includes security rules."""
        with patch("orchestrator.agents.context_injector._load_rule_file") as mock_load:
            mock_load.return_value = "# Security Rules"

            get_context_for_prompt("cursor", "validation")

            # Should have called for security guardrails
            calls = [str(call) for call in mock_load.call_args_list]
            assert any("security" in str(call).lower() for call in calls)

    def test_gemini_review_includes_architecture(self):
        """Test Gemini review context includes architecture rules."""
        with patch("orchestrator.agents.context_injector._load_rule_file") as mock_load:
            mock_load.return_value = "# Architecture Rules"

            get_context_for_prompt("gemini", "review")

            # Should have called for architecture
            calls = [str(call) for call in mock_load.call_args_list]
            assert any("architecture" in str(call).lower() for call in calls)

    def test_implementation_includes_code_quality(self):
        """Test implementation task includes code quality rules."""
        with patch("orchestrator.agents.context_injector._load_rule_file") as mock_load:
            mock_load.return_value = "# Code Quality"

            get_context_for_prompt("claude", "implementation")

            calls = [str(call) for call in mock_load.call_args_list]
            assert any("code-quality" in str(call).lower() for call in calls)

    def test_security_task_includes_security_guardrails(self):
        """Test security task includes security guardrails."""
        with patch("orchestrator.agents.context_injector._load_rule_file") as mock_load:
            mock_load.return_value = "# Security"

            get_context_for_prompt("cursor", "security")

            calls = [str(call) for call in mock_load.call_args_list]
            assert any("security" in str(call).lower() for call in calls)

    def test_missing_rules_returns_empty_gracefully(self):
        """Test that missing rule files don't cause errors."""
        with patch("orchestrator.agents.context_injector._load_rule_file") as mock_load:
            mock_load.return_value = None

            # Should not raise
            result = get_context_for_prompt("claude", "planning")

            assert result == ""

    def test_multiple_sections_joined(self):
        """Test that multiple rule sections are joined."""
        with patch("orchestrator.agents.context_injector._load_rule_file") as mock_load:
            mock_load.side_effect = ["Section 1", "Section 2", "Section 3"]

            result = get_context_for_prompt("claude", "implementation")

            # Should contain content from multiple sections
            assert "Section 1" in result or "Section 2" in result or "Section 3" in result


class TestAgentTypeLiteral:
    """Tests for AgentType literal."""

    def test_valid_agent_types(self):
        """Test that valid agent types work."""
        # These should not raise type errors
        agents: list[AgentType] = ["claude", "cursor", "gemini"]

        for agent in agents:
            identity = get_agent_identity(agent)
            assert isinstance(identity, str)


class TestTaskTypeLiteral:
    """Tests for TaskType literal."""

    def test_valid_task_types(self):
        """Test that valid task types work."""
        task_types: list[TaskType] = [
            "planning",
            "implementation",
            "validation",
            "review",
            "security",
            "research",
        ]

        for task_type in task_types:
            result = get_context_for_prompt("claude", task_type)
            assert isinstance(result, str)


class TestLoadRuleFile:
    """Tests for _load_rule_file internal function."""

    def test_load_existing_file(self):
        """Test loading an existing rule file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create collection/rules/guardrails structure
            rules_dir = Path(tmpdir) / "collection" / "rules" / "guardrails"
            rules_dir.mkdir(parents=True)

            # Create a test rule file
            rule_file = rules_dir / "test.md"
            rule_file.write_text("# Test Rule\nContent here")

            # Patch COLLECTION_DIR to use temp dir
            with patch(
                "orchestrator.agents.context_injector.COLLECTION_DIR",
                Path(tmpdir) / "collection",
            ):
                from orchestrator.agents.context_injector import _load_rule_file

                result = _load_rule_file("guardrails", "test.md")

                assert result is not None
                assert "Test Rule" in result
                assert "Content here" in result

    def test_load_nonexistent_file(self):
        """Test loading a non-existent rule file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "orchestrator.agents.context_injector.COLLECTION_DIR",
                Path(tmpdir) / "collection",
            ):
                from orchestrator.agents.context_injector import _load_rule_file

                result = _load_rule_file("guardrails", "nonexistent.md")

                assert result is None

    def test_load_file_strips_whitespace(self):
        """Test that loaded content is stripped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_dir = Path(tmpdir) / "collection" / "rules" / "guardrails"
            rules_dir.mkdir(parents=True)

            rule_file = rules_dir / "test.md"
            rule_file.write_text("\n\n  Content  \n\n")

            with patch(
                "orchestrator.agents.context_injector.COLLECTION_DIR",
                Path(tmpdir) / "collection",
            ):
                from orchestrator.agents.context_injector import _load_rule_file

                result = _load_rule_file("guardrails", "test.md")

                assert result == "Content"


class TestContextCombinations:
    """Tests for various agent/task combinations."""

    @pytest.mark.parametrize(
        "agent,task",
        [
            ("claude", "planning"),
            ("claude", "implementation"),
            ("cursor", "validation"),
            ("cursor", "review"),
            ("cursor", "security"),
            ("gemini", "review"),
            ("gemini", "validation"),
        ],
    )
    def test_all_combinations_work(self, agent, task):
        """Test that all expected combinations work without errors."""
        # Should not raise any exceptions
        result = get_context_for_prompt(agent, task)
        assert isinstance(result, str)

    @pytest.mark.parametrize("agent", ["claude", "cursor", "gemini"])
    def test_all_agents_have_identity(self, agent):
        """Test that all agents have defined identity."""
        identity = get_agent_identity(agent)
        assert len(identity) > 0
        assert "Role" in identity
