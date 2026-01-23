"""Tests for agent wrappers."""

import subprocess
from unittest.mock import MagicMock, patch

from orchestrator.agents.base import AgentResult
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


class TestBaseAgentTimeoutMapping:
    """Tests for BaseAgent phase timeout mapping."""

    def test_default_timeout(self, temp_project_dir):
        """Test default timeout is used."""
        agent = ClaudeAgent(temp_project_dir, timeout=300)
        assert agent.get_timeout_for_phase(None) == 300

    def test_phase_specific_timeouts(self, temp_project_dir):
        """Test phase-specific timeouts are used."""
        agent = ClaudeAgent(temp_project_dir)

        # Default phase timeouts from PHASE_TIMEOUTS
        assert agent.get_timeout_for_phase(1) == 900  # Planning: 15 min
        assert agent.get_timeout_for_phase(2) == 600  # Validation: 10 min
        assert agent.get_timeout_for_phase(3) == 1800  # Implementation: 30 min
        assert agent.get_timeout_for_phase(4) == 600  # Verification: 10 min
        assert agent.get_timeout_for_phase(5) == 300  # Completion: 5 min

    def test_custom_phase_timeouts(self, temp_project_dir):
        """Test custom phase timeout overrides."""
        custom_timeouts = {1: 1200, 3: 3600}
        agent = ClaudeAgent(temp_project_dir, phase_timeouts=custom_timeouts)

        assert agent.get_timeout_for_phase(1) == 1200  # Custom
        assert agent.get_timeout_for_phase(3) == 3600  # Custom
        # Default for phases not in custom dict falls back to default timeout
        assert agent.get_timeout_for_phase(None) == agent.timeout


class TestBaseAgentErrorHandling:
    """Tests for BaseAgent error handling."""

    @patch("subprocess.run")
    def test_timeout_error(self, mock_run, temp_project_dir):
        """Test handling of timeout errors."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=300)

        agent = ClaudeAgent(temp_project_dir)
        result = agent.run("test prompt")

        assert result.success is False
        assert "timed out" in result.error.lower()
        assert result.exit_code == -1

    @patch("subprocess.run")
    def test_file_not_found_error(self, mock_run, temp_project_dir):
        """Test handling of CLI not found errors."""
        mock_run.side_effect = FileNotFoundError("claude not found")

        agent = ClaudeAgent(temp_project_dir)
        result = agent.run("test prompt")

        assert result.success is False
        assert "CLI not found" in result.error or "not found" in result.error.lower()
        assert result.exit_code == -1

    @patch("subprocess.run")
    def test_permission_error(self, mock_run, temp_project_dir):
        """Test handling of permission errors."""
        mock_run.side_effect = PermissionError("Permission denied")

        agent = ClaudeAgent(temp_project_dir)
        result = agent.run("test prompt")

        assert result.success is False
        assert "permission" in result.error.lower()
        assert result.exit_code == -1

    @patch("subprocess.run")
    def test_os_error(self, mock_run, temp_project_dir):
        """Test handling of general OS errors."""
        mock_run.side_effect = OSError("OS error")

        agent = ClaudeAgent(temp_project_dir)
        result = agent.run("test prompt")

        assert result.success is False
        assert "OS error" in result.error
        assert result.exit_code == -1


class TestBaseAgentAuditIntegration:
    """Tests for BaseAgent audit trail integration."""

    @patch("subprocess.run")
    def test_audit_disabled_by_default_runs(self, mock_run, temp_project_dir):
        """Test that agent runs work without audit trail."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"result": "success"}',
            stderr="",
        )

        agent = ClaudeAgent(temp_project_dir, enable_audit=False)
        result = agent.run("test prompt", task_id="T1")

        assert result.success is True
        assert agent._audit_trail is None

    @patch("subprocess.run")
    def test_cost_extraction_from_output(self, mock_run, temp_project_dir):
        """Test that cost is extracted from parsed output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"result": "success", "cost_usd": 0.05, "model": "claude-3-opus"}',
            stderr="",
        )

        agent = ClaudeAgent(temp_project_dir, enable_audit=False)
        result = agent.run("test prompt")

        assert result.success is True
        assert result.cost_usd == 0.05
        assert result.model == "claude-3-opus"


class TestCursorAgentValidation:
    """Tests for Cursor agent validation methods."""

    @patch("subprocess.run")
    def test_run_validation_success(self, mock_run, temp_project_dir):
        """Test successful validation run."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"reviewer": "cursor", "approved": true, "score": 8}',
            stderr="",
        )

        agent = CursorAgent(temp_project_dir)
        result = agent.run("Validate this plan")

        assert result.success is True
        assert result.parsed_output["approved"] is True
        assert result.parsed_output["score"] == 8

    @patch("subprocess.run")
    def test_run_with_force_flag(self, mock_run, temp_project_dir):
        """Test that --force flag is included."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="{}",
            stderr="",
        )

        agent = CursorAgent(temp_project_dir)
        cmd = agent.build_command("test prompt")

        assert "--force" in cmd


class TestCursorAgentEdgeCases:
    """Tests for Cursor agent edge cases."""

    @patch("subprocess.run")
    def test_non_json_output(self, mock_run, temp_project_dir):
        """Test handling of non-JSON output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Plain text output with no JSON",
            stderr="",
        )

        agent = CursorAgent(temp_project_dir)
        result = agent.run("test prompt")

        assert result.success is True
        assert result.output == "Plain text output with no JSON"
        assert result.parsed_output is None

    @patch("subprocess.run")
    def test_partial_json_output(self, mock_run, temp_project_dir):
        """Test handling of malformed JSON output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"incomplete": true',  # Invalid JSON
            stderr="",
        )

        agent = CursorAgent(temp_project_dir)
        result = agent.run("test prompt")

        assert result.success is True
        assert result.parsed_output is None  # Should not crash

    def test_missing_context_file(self, temp_project_dir):
        """Test reading missing context file."""
        agent = CursorAgent(temp_project_dir)
        content = agent.read_context_file()

        assert content is None


class TestGeminiAgentValidation:
    """Tests for Gemini agent validation methods."""

    @patch("subprocess.run")
    def test_run_architecture_review(self, mock_run, temp_project_dir):
        """Test architecture review execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"reviewer": "gemini", "architecture_score": 9}',
            stderr="",
        )

        agent = GeminiAgent(temp_project_dir)
        result = agent.run("Review architecture")

        assert result.success is True
        assert result.parsed_output["architecture_score"] == 9


class TestAgentAvailability:
    """Tests for agent availability checks."""

    @patch("subprocess.run")
    def test_check_available_success(self, mock_run, temp_project_dir):
        """Test successful availability check."""
        mock_run.return_value = MagicMock(returncode=0)

        agent = ClaudeAgent(temp_project_dir)
        assert agent.check_available() is True

    @patch("subprocess.run")
    def test_check_available_not_found(self, mock_run, temp_project_dir):
        """Test availability check when CLI not found."""
        mock_run.side_effect = FileNotFoundError()

        agent = ClaudeAgent(temp_project_dir)
        assert agent.check_available() is False

    @patch("subprocess.run")
    def test_check_available_timeout(self, mock_run, temp_project_dir):
        """Test availability check timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=10)

        agent = ClaudeAgent(temp_project_dir)
        assert agent.check_available() is False

    @patch("subprocess.run")
    def test_check_available_nonzero_exit(self, mock_run, temp_project_dir):
        """Test availability check with non-zero exit code."""
        mock_run.return_value = MagicMock(returncode=1)

        agent = ClaudeAgent(temp_project_dir)
        assert agent.check_available() is False


class TestOutputFileWriting:
    """Tests for output file writing."""

    @patch("subprocess.run")
    def test_output_file_written_json(self, mock_run, temp_project_dir):
        """Test JSON output is written to file."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"result": "test"}',
            stderr="",
        )

        output_file = temp_project_dir / "output" / "test_output.json"
        agent = ClaudeAgent(temp_project_dir)
        result = agent.run("test prompt", output_file=output_file)

        assert result.success is True
        assert output_file.exists()

        import json

        content = json.loads(output_file.read_text())
        assert content["result"] == "test"

    @patch("subprocess.run")
    def test_output_file_written_text(self, mock_run, temp_project_dir):
        """Test plain text output is written to file."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Plain text output",
            stderr="",
        )

        output_file = temp_project_dir / "output" / "test_output.txt"
        agent = ClaudeAgent(temp_project_dir)
        result = agent.run("test prompt", output_file=output_file)

        assert result.success is True
        assert output_file.exists()
        assert output_file.read_text() == "Plain text output"
