"""Tests for agent adapter layer.

Tests the universal agent adapter interface that allows the unified loop
to work with any agent (Claude, Cursor, Gemini).
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.config.models import (
    CLAUDE_MODELS, CLAUDE_SONNET, CLAUDE_OPUS, CLAUDE_HAIKU, DEFAULT_CLAUDE_MODEL,
    GEMINI_MODELS, GEMINI_FLASH, GEMINI_PRO, DEFAULT_GEMINI_MODEL,
    CURSOR_MODELS, CURSOR_CODEX, CURSOR_COMPOSER, DEFAULT_CURSOR_MODEL
)
from orchestrator.agents.adapter import (
    AgentType,
    AgentCapabilities,
    IterationResult,
    AgentAdapter,
    ClaudeAdapter,
    CursorAdapter,
    GeminiAdapter,
    create_adapter,
    get_agent_capabilities,
    get_available_agents,
    get_agent_for_task,
)


class TestAgentType:
    """Tests for AgentType enum."""

    def test_agent_types_exist(self):
        """Test that all expected agent types exist."""
        assert AgentType.CLAUDE == "claude"
        assert AgentType.CURSOR == "cursor"
        assert AgentType.GEMINI == "gemini"

    def test_agent_type_from_string(self):
        """Test creating AgentType from string."""
        assert AgentType("claude") == AgentType.CLAUDE
        assert AgentType("cursor") == AgentType.CURSOR
        assert AgentType("gemini") == AgentType.GEMINI

    def test_invalid_agent_type_raises(self):
        """Test that invalid agent type raises ValueError."""
        with pytest.raises(ValueError):
            AgentType("invalid")


class TestAgentCapabilities:
    """Tests for AgentCapabilities dataclass."""

    def test_default_capabilities(self):
        """Test default capability values."""
        caps = AgentCapabilities()
        assert caps.supports_json_output is False
        assert caps.supports_session is False
        assert caps.supports_model_selection is False
        assert caps.available_models == []
        assert caps.completion_patterns == []

    def test_custom_capabilities(self):
        """Test creating capabilities with custom values."""
        caps = AgentCapabilities(
            supports_json_output=True,
            supports_session=True,
            available_models=["model1", "model2"],
            completion_patterns=["DONE", "COMPLETE"],
        )
        assert caps.supports_json_output is True
        assert caps.supports_session is True
        assert caps.available_models == ["model1", "model2"]
        assert caps.completion_patterns == ["DONE", "COMPLETE"]


class TestIterationResult:
    """Tests for IterationResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful iteration result."""
        result = IterationResult(
            success=True,
            output="test output",
            completion_detected=True,
            exit_code=0,
            duration_seconds=5.0,
        )
        assert result.success is True
        assert result.output == "test output"
        assert result.completion_detected is True

    def test_failed_result(self):
        """Test creating a failed iteration result."""
        result = IterationResult(
            success=False,
            error="Command failed",
            exit_code=1,
        )
        assert result.success is False
        assert result.error == "Command failed"
        assert result.exit_code == 1

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = IterationResult(
            success=True,
            output="test" * 1000,  # Long output
            files_changed=["file1.py", "file2.py"],
        )
        d = result.to_dict()
        assert d["success"] is True
        assert len(d["output"]) <= 2000  # Truncated
        assert d["files_changed"] == ["file1.py", "file2.py"]


class TestClaudeAdapter:
    """Tests for ClaudeAdapter."""

    def test_agent_type(self, tmp_path):
        """Test agent type is claude."""
        adapter = ClaudeAdapter(tmp_path)
        assert adapter.agent_type == AgentType.CLAUDE

    def test_capabilities(self, tmp_path):
        """Test Claude capabilities."""
        adapter = ClaudeAdapter(tmp_path)
        caps = adapter.capabilities
        assert caps.supports_json_output is True
        assert caps.supports_session is True
        assert caps.supports_model_selection is True
        assert caps.supports_plan_mode is True
        assert caps.supports_budget_flag is True
        assert CLAUDE_SONNET in caps.available_models
        assert CLAUDE_OPUS in caps.available_models
        assert CLAUDE_HAIKU in caps.available_models

    def test_build_command_basic(self, tmp_path):
        """Test basic command building."""
        adapter = ClaudeAdapter(tmp_path)
        cmd = adapter.build_command("test prompt")
        assert "claude" in cmd
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_build_command_with_model(self, tmp_path):
        """Test command building with model selection."""
        adapter = ClaudeAdapter(tmp_path)
        cmd = adapter.build_command("test prompt", model=CLAUDE_OPUS)
        assert "--model" in cmd
        assert CLAUDE_OPUS in cmd

    def test_build_command_with_session(self, tmp_path):
        """Test command building with session."""
        adapter = ClaudeAdapter(tmp_path)
        cmd = adapter.build_command(
            "test prompt",
            session_id="session-123",
            resume_session=True,
        )
        assert "--resume" in cmd
        assert "session-123" in cmd

    def test_build_command_with_budget(self, tmp_path):
        """Test command building with budget."""
        adapter = ClaudeAdapter(tmp_path)
        cmd = adapter.build_command("test prompt", budget_usd=0.50)
        assert "--max-budget-usd" in cmd
        assert "0.5" in cmd

    def test_build_command_with_plan_mode(self, tmp_path):
        """Test command building with plan mode."""
        adapter = ClaudeAdapter(tmp_path)
        cmd = adapter.build_command("test prompt", use_plan_mode=True)
        assert "--permission-mode" in cmd
        assert "plan" in cmd

    def test_detect_completion(self, tmp_path):
        """Test completion detection."""
        adapter = ClaudeAdapter(tmp_path)

        # Should detect promise pattern
        assert adapter.detect_completion("<promise>DONE</promise>") is True

        # Should detect status pattern
        assert adapter.detect_completion('{"status": "completed"}') is True

        # Should not detect incomplete output
        assert adapter.detect_completion("still working...") is False


class TestCursorAdapter:
    """Tests for CursorAdapter."""

    def test_agent_type(self, tmp_path):
        """Test agent type is cursor."""
        adapter = CursorAdapter(tmp_path)
        assert adapter.agent_type == AgentType.CURSOR

    def test_capabilities(self, tmp_path):
        """Test Cursor capabilities."""
        adapter = CursorAdapter(tmp_path)
        caps = adapter.capabilities
        assert caps.supports_json_output is True
        assert caps.supports_session is False
        assert caps.supports_model_selection is True
        assert CURSOR_CODEX in caps.available_models
        assert CURSOR_COMPOSER in caps.available_models

    def test_build_command_basic(self, tmp_path):
        """Test basic command building."""
        adapter = CursorAdapter(tmp_path)
        cmd = adapter.build_command("test prompt")
        assert "cursor-agent" in cmd
        assert "--print" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        # Prompt should be last (positional)
        assert cmd[-1] == "test prompt"

    def test_build_command_with_model(self, tmp_path):
        """Test command building with model selection."""
        adapter = CursorAdapter(tmp_path)
        cmd = adapter.build_command("test prompt", model="composer")
        assert "--model" in cmd
        assert "composer" in cmd

    def test_detect_completion(self, tmp_path):
        """Test completion detection."""
        adapter = CursorAdapter(tmp_path)

        # Should detect done pattern
        assert adapter.detect_completion('{"status": "done"}') is True
        assert adapter.detect_completion('{"status": "completed"}') is True

        # Should not detect incomplete output
        assert adapter.detect_completion("still working...") is False


class TestGeminiAdapter:
    """Tests for GeminiAdapter."""

    def test_agent_type(self, tmp_path):
        """Test agent type is gemini."""
        adapter = GeminiAdapter(tmp_path)
        assert adapter.agent_type == AgentType.GEMINI

    def test_capabilities(self, tmp_path):
        """Test Gemini capabilities."""
        adapter = GeminiAdapter(tmp_path)
        caps = adapter.capabilities
        assert caps.supports_json_output is False  # Gemini CLI doesn't support --output-format
        assert caps.supports_session is False
        assert caps.supports_model_selection is True
        assert GEMINI_FLASH in caps.available_models
        assert GEMINI_PRO in caps.available_models

    def test_build_command_basic(self, tmp_path):
        """Test basic command building."""
        adapter = GeminiAdapter(tmp_path)
        cmd = adapter.build_command("test prompt")
        assert "gemini" in cmd
        assert "--yolo" in cmd
        assert "test prompt" in cmd

    def test_build_command_with_model(self, tmp_path):
        """Test command building with model selection."""
        adapter = GeminiAdapter(tmp_path)
        cmd = adapter.build_command("test prompt", model=GEMINI_PRO)
        assert "--model" in cmd
        assert GEMINI_PRO in cmd

    def test_detect_completion(self, tmp_path):
        """Test completion detection."""
        adapter = GeminiAdapter(tmp_path)

        # Should detect text patterns (case-insensitive)
        assert adapter.detect_completion("DONE") is True
        assert adapter.detect_completion("Done") is True
        assert adapter.detect_completion("COMPLETE") is True
        assert adapter.detect_completion("FINISHED") is True

        # Should detect JSON status
        assert adapter.detect_completion('{"status": "done"}') is True

        # Should not detect incomplete output
        assert adapter.detect_completion("still working...") is False


class TestCreateAdapter:
    """Tests for create_adapter factory function."""

    def test_create_claude_adapter(self, tmp_path):
        """Test creating Claude adapter."""
        adapter = create_adapter(AgentType.CLAUDE, tmp_path)
        assert isinstance(adapter, ClaudeAdapter)

    def test_create_cursor_adapter(self, tmp_path):
        """Test creating Cursor adapter."""
        adapter = create_adapter(AgentType.CURSOR, tmp_path)
        assert isinstance(adapter, CursorAdapter)

    def test_create_gemini_adapter(self, tmp_path):
        """Test creating Gemini adapter."""
        adapter = create_adapter(AgentType.GEMINI, tmp_path)
        assert isinstance(adapter, GeminiAdapter)

    def test_create_adapter_from_string(self, tmp_path):
        """Test creating adapter from string."""
        adapter = create_adapter("claude", tmp_path)
        assert isinstance(adapter, ClaudeAdapter)

    def test_create_adapter_with_model(self, tmp_path):
        """Test creating adapter with model."""
        adapter = create_adapter("cursor", tmp_path, model=CURSOR_COMPOSER)
        assert adapter.model == CURSOR_COMPOSER

    def test_create_adapter_with_timeout(self, tmp_path):
        """Test creating adapter with timeout."""
        adapter = create_adapter("gemini", tmp_path, timeout=600)
        assert adapter.timeout == 600

    def test_invalid_agent_type_raises(self, tmp_path):
        """Test that invalid agent type raises ValueError."""
        with pytest.raises(ValueError):
            create_adapter("invalid", tmp_path)


class TestGetAgentCapabilities:
    """Tests for get_agent_capabilities function."""

    def test_get_claude_capabilities(self):
        """Test getting Claude capabilities."""
        caps = get_agent_capabilities(AgentType.CLAUDE)
        assert caps.supports_session is True

    def test_get_cursor_capabilities(self):
        """Test getting Cursor capabilities."""
        caps = get_agent_capabilities("cursor")
        assert caps.supports_session is False

    def test_get_gemini_capabilities(self):
        """Test getting Gemini capabilities."""
        caps = get_agent_capabilities("gemini")
        assert caps.supports_json_output is False


class TestGetAvailableAgents:
    """Tests for get_available_agents function."""

    def test_returns_all_agents(self):
        """Test that all agent types are returned."""
        agents = get_available_agents()
        assert AgentType.CLAUDE in agents
        assert AgentType.CURSOR in agents
        assert AgentType.GEMINI in agents


class TestGetAgentForTask:
    """Tests for get_agent_for_task function."""

    def test_default_agent(self):
        """Test default agent selection."""
        agent_type, model = get_agent_for_task({})
        assert agent_type == AgentType.CLAUDE

    def test_task_specified_agent(self):
        """Test task-specified agent."""
        agent_type, model = get_agent_for_task({"agent_type": "cursor"})
        assert agent_type == AgentType.CURSOR

    def test_task_specified_model(self):
        """Test task-specified model."""
        agent_type, model = get_agent_for_task({"model": CLAUDE_OPUS})
        assert model == CLAUDE_OPUS

    def test_env_override(self, monkeypatch):
        """Test environment variable override."""
        monkeypatch.setenv("LOOP_AGENT", "gemini")
        agent_type, model = get_agent_for_task({})
        assert agent_type == AgentType.GEMINI

    def test_invalid_model_fallback(self):
        """Test fallback when model is invalid for agent."""
        agent_type, model = get_agent_for_task({
            "agent_type": "cursor",
            "model": CLAUDE_OPUS,  # Claude model, not valid for Cursor
        })
        assert agent_type == AgentType.CURSOR
        # Should fall back to default cursor model
        assert model == DEFAULT_CURSOR_MODEL


class TestAdapterRunIteration:
    """Tests for adapter run_iteration method."""

    @pytest.mark.asyncio
    async def test_run_iteration_success(self, tmp_path):
        """Test successful iteration run."""
        adapter = ClaudeAdapter(tmp_path)

        # Mock subprocess
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (
                b'{"status": "completed"}',
                b"",
            )
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            result = await adapter.run_iteration("test prompt", timeout=10)

            assert result.success is True
            assert result.completion_detected is True
            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_run_iteration_failure(self, tmp_path):
        """Test failed iteration run."""
        adapter = ClaudeAdapter(tmp_path)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Error occurred")
            mock_process.returncode = 1
            mock_exec.return_value = mock_process

            result = await adapter.run_iteration("test prompt", timeout=10)

            assert result.success is False
            assert result.exit_code == 1
            assert "Error" in result.error

    @pytest.mark.asyncio
    async def test_run_iteration_timeout(self, tmp_path):
        """Test iteration timeout."""
        adapter = ClaudeAdapter(tmp_path)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_process.returncode = None
            mock_exec.return_value = mock_process

            result = await adapter.run_iteration("test prompt", timeout=1)

            assert result.success is False
            assert "Timeout" in result.error
