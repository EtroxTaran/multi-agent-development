"""Tests for agent wrappers."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from orchestrator.agents.base import BaseAgent, AgentResult
from orchestrator.agents.claude_agent import ClaudeAgent
from orchestrator.agents.cursor_agent import CursorAgent
from orchestrator.agents.gemini_agent import GeminiAgent


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_success_result(self):
        """Test successful result."""
        result = AgentResult(
            success=True,
            output='{"data": "test"}',
            parsed_output={"data": "test"},
            exit_code=0,
            duration_seconds=1.5,
        )
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        """Test failure result."""
        result = AgentResult(
            success=False,
            error="Command failed",
            exit_code=1,
        )
        assert result.success is False
        assert result.error == "Command failed"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = AgentResult(success=True, output="test")
        d = result.to_dict()
        assert d["success"] is True
        assert d["output"] == "test"


class TestClaudeAgent:
    """Tests for Claude agent wrapper."""

    def test_initialization(self, temp_project_dir):
        """Test agent initialization."""
        agent = ClaudeAgent(temp_project_dir)
        assert agent.name == "claude"
        assert agent.project_dir == temp_project_dir
        assert agent.timeout == 600

    def test_get_cli_command(self, temp_project_dir):
        """Test CLI command name."""
        agent = ClaudeAgent(temp_project_dir)
        assert agent.get_cli_command() == "claude"

    def test_get_context_file(self, temp_project_dir):
        """Test context file path."""
        agent = ClaudeAgent(temp_project_dir)
        assert agent.get_context_file() == temp_project_dir / "CLAUDE.md"

    def test_build_command(self, temp_project_dir):
        """Test command building."""
        agent = ClaudeAgent(temp_project_dir)
        cmd = agent.build_command("test prompt")

        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_build_command_with_allowed_tools(self, temp_project_dir):
        """Test command with allowed tools."""
        agent = ClaudeAgent(
            temp_project_dir,
            allowed_tools=["Read", "Write"],
        )
        cmd = agent.build_command("test")

        assert "--allowedTools" in cmd
        tools_idx = cmd.index("--allowedTools") + 1
        assert "Read,Write" == cmd[tools_idx]

    @patch("subprocess.run")
    def test_run_success(self, mock_run, temp_project_dir):
        """Test successful command execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"result": "success"}',
            stderr="",
        )

        agent = ClaudeAgent(temp_project_dir)
        result = agent.run("test prompt")

        assert result.success is True
        assert result.parsed_output == {"result": "success"}

    @patch("subprocess.run")
    def test_run_failure(self, mock_run, temp_project_dir):
        """Test failed command execution."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error occurred",
        )

        agent = ClaudeAgent(temp_project_dir)
        result = agent.run("test prompt")

        assert result.success is False
        assert "Error occurred" in result.error


class TestCursorAgent:
    """Tests for Cursor agent wrapper."""

    def test_initialization(self, temp_project_dir):
        """Test agent initialization."""
        agent = CursorAgent(temp_project_dir)
        assert agent.name == "cursor"
        assert agent.project_dir == temp_project_dir

    def test_get_cli_command(self, temp_project_dir):
        """Test CLI command name."""
        agent = CursorAgent(temp_project_dir)
        assert agent.get_cli_command() == "cursor-agent"

    def test_get_context_file(self, temp_project_dir):
        """Test context file path."""
        agent = CursorAgent(temp_project_dir)
        assert agent.get_context_file() == temp_project_dir / "AGENTS.md"

    def test_build_command(self, temp_project_dir):
        """Test command building."""
        agent = CursorAgent(temp_project_dir)
        cmd = agent.build_command("test prompt")

        assert cmd[0] == "cursor-agent"
        assert "--print" in cmd  # Non-interactive mode flag
        assert "test prompt" in cmd
        assert "--force" in cmd


class TestGeminiAgent:
    """Tests for Gemini agent wrapper."""

    def test_initialization(self, temp_project_dir):
        """Test agent initialization."""
        agent = GeminiAgent(temp_project_dir)
        assert agent.name == "gemini"
        assert agent.project_dir == temp_project_dir

    def test_get_cli_command(self, temp_project_dir):
        """Test CLI command name."""
        agent = GeminiAgent(temp_project_dir)
        assert agent.get_cli_command() == "gemini"

    def test_get_context_file(self, temp_project_dir):
        """Test context file path."""
        agent = GeminiAgent(temp_project_dir)
        assert agent.get_context_file() == temp_project_dir / "GEMINI.md"

    def test_build_command(self, temp_project_dir):
        """Test command building."""
        agent = GeminiAgent(temp_project_dir)
        cmd = agent.build_command("test prompt")

        assert cmd[0] == "gemini"
        assert "--yolo" in cmd  # Auto-approve for non-interactive mode
        assert "test prompt" in cmd
        # Note: gemini CLI doesn't support --output-format
