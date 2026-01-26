"""Tests for agent adapter layer.

Tests the universal agent interface, CLI command building,
completion detection, and iteration execution.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.agents.adapter import (
    ADAPTER_REGISTRY,
    AgentAdapter,
    AgentCapabilities,
    AgentType,
    ClaudeAdapter,
    CursorAdapter,
    GeminiAdapter,
    IterationResult,
    create_adapter,
    get_agent_capabilities,
    get_agent_for_task,
    get_available_agents,
)


class TestAgentType:
    """Tests for AgentType enum."""

    def test_agent_type_values(self):
        """Test that all agent types have correct values."""
        assert AgentType.CLAUDE.value == "claude"
        assert AgentType.CURSOR.value == "cursor"
        assert AgentType.GEMINI.value == "gemini"

    def test_agent_type_from_string(self):
        """Test creating AgentType from string."""
        assert AgentType("claude") == AgentType.CLAUDE
        assert AgentType("cursor") == AgentType.CURSOR
        assert AgentType("gemini") == AgentType.GEMINI

    def test_agent_type_invalid_raises(self):
        """Test that invalid agent type raises ValueError."""
        with pytest.raises(ValueError):
            AgentType("invalid")


class TestAgentCapabilities:
    """Tests for AgentCapabilities dataclass."""

    def test_capabilities_defaults(self):
        """Test default capability values."""
        caps = AgentCapabilities()
        assert caps.supports_json_output is False
        assert caps.supports_session is False
        assert caps.supports_model_selection is False
        assert caps.supports_plan_mode is False
        assert caps.supports_budget_flag is False
        assert caps.available_models == []
        assert caps.completion_patterns == []
        assert caps.default_model is None

    def test_capabilities_custom_values(self):
        """Test custom capability values."""
        caps = AgentCapabilities(
            supports_json_output=True,
            supports_session=True,
            available_models=["model1", "model2"],
            completion_patterns=["DONE"],
            default_model="model1",
        )
        assert caps.supports_json_output is True
        assert caps.supports_session is True
        assert caps.available_models == ["model1", "model2"]
        assert caps.completion_patterns == ["DONE"]
        assert caps.default_model == "model1"


class TestIterationResult:
    """Tests for IterationResult dataclass."""

    def test_iteration_result_defaults(self):
        """Test default iteration result values."""
        result = IterationResult(success=True)
        assert result.success is True
        assert result.output == ""
        assert result.parsed_output is None
        assert result.completion_detected is False
        assert result.exit_code == 0
        assert result.duration_seconds == 0.0
        assert result.error is None
        assert result.files_changed == []
        assert result.session_id is None
        assert result.cost_usd is None
        assert result.model is None

    def test_iteration_result_to_dict(self, sample_iteration_result):
        """Test serialization to dictionary."""
        d = sample_iteration_result.to_dict()
        assert d["success"] is True
        assert d["exit_code"] == 0
        assert d["completion_detected"] is True
        assert d["files_changed"] == ["src/calc.py"]
        assert d["session_id"] == "session-123"
        assert d["cost_usd"] == 0.05
        assert d["model"] == "sonnet"

    def test_iteration_result_output_truncation(self):
        """Test that long output is truncated in to_dict."""
        long_output = "x" * 3000
        result = IterationResult(success=True, output=long_output)
        d = result.to_dict()
        assert len(d["output"]) == 2000


class TestClaudeAdapter:
    """Tests for ClaudeAdapter."""

    def test_agent_type(self, claude_adapter):
        """Test agent type property."""
        assert claude_adapter.agent_type == AgentType.CLAUDE

    def test_capabilities(self, claude_adapter):
        """Test Claude capabilities."""
        caps = claude_adapter.capabilities
        assert caps.supports_json_output is True
        assert caps.supports_session is True
        assert caps.supports_model_selection is True
        assert caps.supports_plan_mode is True
        assert caps.supports_budget_flag is True
        # Model names include version (e.g., claude-4-5-sonnet)
        assert any("sonnet" in m for m in caps.available_models)
        assert caps.default_model is not None

    def test_build_command_basic(self, claude_adapter):
        """Test basic command building."""
        cmd = claude_adapter.build_command("Test prompt")
        assert "claude" in cmd
        assert "-p" in cmd
        assert "Test prompt" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_build_command_with_model(self, claude_adapter):
        """Test command with model selection."""
        # Use a valid model from CLAUDE_MODELS
        cmd = claude_adapter.build_command("Test", model="claude-4-5-sonnet")
        assert "--model" in cmd
        assert "claude-4-5-sonnet" in cmd

    def test_build_command_with_session_id(self, claude_adapter):
        """Test command with session ID."""
        cmd = claude_adapter.build_command("Test", session_id="session-123")
        assert "--session-id" in cmd
        assert "session-123" in cmd

    def test_build_command_with_resume_session(self, claude_adapter):
        """Test command with session resume."""
        cmd = claude_adapter.build_command("Test", session_id="session-123", resume_session=True)
        assert "--resume" in cmd
        assert "session-123" in cmd
        assert "--session-id" not in cmd

    def test_build_command_with_plan_mode(self, claude_adapter):
        """Test command with plan mode."""
        cmd = claude_adapter.build_command("Test", use_plan_mode=True)
        assert "--permission-mode" in cmd
        assert "plan" in cmd

    def test_build_command_with_budget(self, claude_adapter):
        """Test command with budget limit."""
        cmd = claude_adapter.build_command("Test", budget_usd=2.50)
        assert "--max-budget-usd" in cmd
        assert "2.5" in cmd or "2.50" in cmd

    def test_build_command_with_json_schema(self, claude_adapter):
        """Test command with JSON schema."""
        cmd = claude_adapter.build_command("Test", json_schema="plan-schema.json")
        assert "--json-schema" in cmd
        assert "plan-schema.json" in cmd

    def test_build_command_with_fallback_model(self, claude_adapter):
        """Test command with fallback model."""
        cmd = claude_adapter.build_command("Test", fallback_model="haiku")
        assert "--fallback-model" in cmd
        assert "haiku" in cmd

    def test_build_command_with_allowed_tools(self, claude_adapter):
        """Test command with allowed tools."""
        cmd = claude_adapter.build_command("Test", allowed_tools=["Read", "Write", "Edit"])
        assert "--allowedTools" in cmd
        assert "Read,Write,Edit" in cmd

    def test_build_command_with_max_turns(self, claude_adapter):
        """Test command includes max turns."""
        cmd = claude_adapter.build_command("Test", max_turns=10)
        assert "--max-turns" in cmd
        assert "10" in cmd

    def test_detect_completion_promise_done(self, claude_adapter):
        """Test completion detection with promise signal."""
        output = "Working...\n<promise>DONE</promise>\nFinished"
        assert claude_adapter.detect_completion(output) is True

    def test_detect_completion_status_completed(self, claude_adapter):
        """Test completion detection with status completed."""
        output = '{"status": "completed", "result": "success"}'
        assert claude_adapter.detect_completion(output) is True

    def test_detect_completion_no_signal(self, claude_adapter):
        """Test no completion when signal absent."""
        output = "Still working on the task..."
        assert claude_adapter.detect_completion(output) is False


class TestCursorAdapter:
    """Tests for CursorAdapter."""

    def test_agent_type(self, cursor_adapter):
        """Test agent type property."""
        assert cursor_adapter.agent_type == AgentType.CURSOR

    def test_capabilities(self, cursor_adapter):
        """Test Cursor capabilities."""
        caps = cursor_adapter.capabilities
        assert caps.supports_json_output is True
        assert caps.supports_session is False
        assert caps.supports_model_selection is True
        assert caps.supports_plan_mode is False
        assert caps.supports_budget_flag is False

    def test_build_command_basic(self, cursor_adapter):
        """Test basic command building."""
        cmd = cursor_adapter.build_command("Review code")
        assert "cursor-agent" in cmd
        assert "--print" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        # Prompt should be at end (positional)
        assert cmd[-1] == "Review code"

    def test_build_command_with_model(self, cursor_adapter):
        """Test command with model selection."""
        cmd = cursor_adapter.build_command("Review", model="codex-5.2")
        assert "--model" in cmd
        assert "codex-5.2" in cmd

    def test_build_command_with_force(self, cursor_adapter):
        """Test command includes force flag."""
        cmd = cursor_adapter.build_command("Review", force=True)
        assert "--force" in cmd

    def test_build_command_without_force(self, cursor_adapter):
        """Test command without force flag."""
        cmd = cursor_adapter.build_command("Review", force=False)
        assert "--force" not in cmd

    def test_detect_completion_status_done(self, cursor_adapter):
        """Test completion detection with status done."""
        output = '{"status": "done", "issues": []}'
        assert cursor_adapter.detect_completion(output) is True

    def test_detect_completion_status_completed(self, cursor_adapter):
        """Test completion detection with status completed."""
        output = '{"status": "completed"}'
        assert cursor_adapter.detect_completion(output) is True

    def test_detect_completion_no_signal(self, cursor_adapter):
        """Test no completion when signal absent."""
        output = '{"status": "in_progress"}'
        assert cursor_adapter.detect_completion(output) is False


class TestGeminiAdapter:
    """Tests for GeminiAdapter."""

    def test_agent_type(self, gemini_adapter):
        """Test agent type property."""
        assert gemini_adapter.agent_type == AgentType.GEMINI

    def test_capabilities(self, gemini_adapter):
        """Test Gemini capabilities."""
        caps = gemini_adapter.capabilities
        assert caps.supports_json_output is False  # Gemini doesn't support --output-format
        assert caps.supports_session is False
        assert caps.supports_model_selection is True
        assert caps.supports_plan_mode is False
        assert caps.supports_budget_flag is False

    def test_build_command_basic(self, gemini_adapter):
        """Test basic command building."""
        cmd = gemini_adapter.build_command("Analyze architecture")
        assert "gemini" in cmd
        assert "--yolo" in cmd
        # Prompt should be at end (positional)
        assert cmd[-1] == "Analyze architecture"
        # Should NOT have --output-format
        assert "--output-format" not in cmd

    def test_build_command_with_model(self, gemini_adapter):
        """Test command with model selection."""
        cmd = gemini_adapter.build_command("Analyze", model="gemini-2.0-pro")
        assert "--model" in cmd
        assert "gemini-2.0-pro" in cmd

    def test_detect_completion_done_text(self, gemini_adapter):
        """Test completion detection with DONE text."""
        output = "Analysis complete.\nDONE"
        assert gemini_adapter.detect_completion(output) is True

    def test_detect_completion_complete_text(self, gemini_adapter):
        """Test completion detection with COMPLETE text."""
        output = "Task COMPLETE"
        assert gemini_adapter.detect_completion(output) is True

    def test_detect_completion_finished_text(self, gemini_adapter):
        """Test completion detection with FINISHED text."""
        output = "FINISHED processing"
        assert gemini_adapter.detect_completion(output) is True

    def test_detect_completion_case_insensitive(self, gemini_adapter):
        """Test completion detection is case insensitive."""
        output = "done"
        assert gemini_adapter.detect_completion(output) is True

    def test_detect_completion_json_status(self, gemini_adapter):
        """Test completion detection from JSON output."""
        output = '{"status": "done"}'
        assert gemini_adapter.detect_completion(output) is True

    def test_detect_completion_no_signal(self, gemini_adapter):
        """Test no completion when signal absent."""
        output = "Still analyzing the codebase..."
        assert gemini_adapter.detect_completion(output) is False


class TestCreateAdapter:
    """Tests for create_adapter factory function."""

    def test_create_claude_adapter(self, temp_project_dir):
        """Test creating Claude adapter."""
        adapter = create_adapter(AgentType.CLAUDE, temp_project_dir)
        assert isinstance(adapter, ClaudeAdapter)
        assert adapter.agent_type == AgentType.CLAUDE

    def test_create_cursor_adapter(self, temp_project_dir):
        """Test creating Cursor adapter."""
        adapter = create_adapter(AgentType.CURSOR, temp_project_dir)
        assert isinstance(adapter, CursorAdapter)
        assert adapter.agent_type == AgentType.CURSOR

    def test_create_gemini_adapter(self, temp_project_dir):
        """Test creating Gemini adapter."""
        adapter = create_adapter(AgentType.GEMINI, temp_project_dir)
        assert isinstance(adapter, GeminiAdapter)
        assert adapter.agent_type == AgentType.GEMINI

    def test_create_adapter_from_string(self, temp_project_dir):
        """Test creating adapter from string type."""
        adapter = create_adapter("claude", temp_project_dir)
        assert isinstance(adapter, ClaudeAdapter)

    def test_create_adapter_case_insensitive(self, temp_project_dir):
        """Test creating adapter is case insensitive."""
        adapter = create_adapter("CLAUDE", temp_project_dir)
        assert isinstance(adapter, ClaudeAdapter)

    def test_create_adapter_with_model(self, temp_project_dir):
        """Test creating adapter with model override."""
        adapter = create_adapter(AgentType.CLAUDE, temp_project_dir, model="opus")
        assert adapter.model == "opus"

    def test_create_adapter_with_timeout(self, temp_project_dir):
        """Test creating adapter with custom timeout."""
        adapter = create_adapter(AgentType.CLAUDE, temp_project_dir, timeout=600)
        assert adapter.timeout == 600

    def test_create_adapter_unknown_type_raises(self, temp_project_dir):
        """Test that unknown agent type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown agent type"):
            create_adapter("unknown", temp_project_dir)


class TestGetAgentCapabilities:
    """Tests for get_agent_capabilities function."""

    def test_get_claude_capabilities(self):
        """Test getting Claude capabilities."""
        caps = get_agent_capabilities(AgentType.CLAUDE)
        assert caps.supports_json_output is True
        assert caps.supports_session is True

    def test_get_cursor_capabilities(self):
        """Test getting Cursor capabilities."""
        caps = get_agent_capabilities(AgentType.CURSOR)
        assert caps.supports_json_output is True
        assert caps.supports_session is False

    def test_get_gemini_capabilities(self):
        """Test getting Gemini capabilities."""
        caps = get_agent_capabilities(AgentType.GEMINI)
        assert caps.supports_json_output is False

    def test_get_capabilities_from_string(self):
        """Test getting capabilities from string type."""
        caps = get_agent_capabilities("claude")
        assert caps.supports_json_output is True

    def test_get_capabilities_unknown_raises(self):
        """Test that unknown type raises ValueError."""
        with pytest.raises(ValueError):
            get_agent_capabilities("unknown")


class TestGetAvailableAgents:
    """Tests for get_available_agents function."""

    def test_returns_all_agent_types(self):
        """Test that all agent types are returned."""
        agents = get_available_agents()
        assert AgentType.CLAUDE in agents
        assert AgentType.CURSOR in agents
        assert AgentType.GEMINI in agents

    def test_returns_list(self):
        """Test that result is a list."""
        agents = get_available_agents()
        assert isinstance(agents, list)
        assert len(agents) == 3


class TestGetAgentForTask:
    """Tests for get_agent_for_task function."""

    def test_default_agent(self):
        """Test default agent when no hints provided."""
        task = {"id": "T1", "title": "Test task"}
        agent_type, model = get_agent_for_task(task)
        # Should return claude as default or inferred
        assert agent_type in [AgentType.CLAUDE, AgentType.CURSOR, AgentType.GEMINI]

    def test_task_with_agent_type_hint(self):
        """Test agent selection from task hint."""
        task = {"id": "T1", "agent_type": "cursor"}
        agent_type, model = get_agent_for_task(task)
        assert agent_type == AgentType.CURSOR

    def test_task_with_primary_cli_hint(self):
        """Test agent selection from primary_cli hint."""
        task = {"id": "T1", "primary_cli": "gemini"}
        agent_type, model = get_agent_for_task(task)
        assert agent_type == AgentType.GEMINI

    def test_task_with_model_hint(self):
        """Test model selection from task hint."""
        # Use a valid model from CLAUDE_MODELS
        task = {"id": "T1", "agent_type": "claude", "model": "claude-4-5-opus"}
        agent_type, model = get_agent_for_task(task)
        assert agent_type == AgentType.CLAUDE
        assert model == "claude-4-5-opus"

    def test_env_override_agent(self, monkeypatch):
        """Test environment variable overrides task hint."""
        monkeypatch.setenv("LOOP_AGENT", "cursor")
        task = {"id": "T1", "agent_type": "claude"}
        agent_type, model = get_agent_for_task(task)
        assert agent_type == AgentType.CURSOR

    def test_env_override_model(self, monkeypatch):
        """Test environment variable overrides model."""
        # Use a valid Claude model since Claude is default
        monkeypatch.setenv("LOOP_AGENT", "claude")
        monkeypatch.setenv("LOOP_MODEL", "claude-4-5-haiku")
        task = {"id": "T1", "model": "claude-4-5-opus"}
        agent_type, model = get_agent_for_task(task)
        assert model == "claude-4-5-haiku"

    def test_invalid_env_agent_uses_default(self, monkeypatch):
        """Test invalid env agent falls back to default."""
        monkeypatch.setenv("LOOP_AGENT", "invalid")
        task = {"id": "T1"}
        agent_type, model = get_agent_for_task(task, default_agent=AgentType.GEMINI)
        assert agent_type == AgentType.GEMINI


class TestAdapterRunIteration:
    """Tests for AgentAdapter.run_iteration method."""

    @pytest.mark.asyncio
    async def test_run_iteration_success(self, claude_adapter, mock_subprocess):
        """Test successful iteration execution."""
        with patch("asyncio.create_subprocess_exec", return_value=mock_subprocess):
            result = await claude_adapter.run_iteration("Test prompt", timeout=60)

        assert result.success is True
        assert result.exit_code == 0
        assert result.completion_detected is True
        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_run_iteration_failure(self, claude_adapter):
        """Test iteration with non-zero exit code."""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error occurred"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await claude_adapter.run_iteration("Test prompt")

        assert result.success is False
        assert result.exit_code == 1
        assert "Error occurred" in result.error

    @pytest.mark.asyncio
    async def test_run_iteration_timeout(self, claude_adapter, mock_subprocess):
        """Test iteration timeout handling."""
        mock_subprocess.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_subprocess.terminate = MagicMock()
        mock_subprocess.kill = MagicMock()
        mock_subprocess.wait = AsyncMock()
        mock_subprocess.returncode = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_subprocess):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                result = await claude_adapter.run_iteration("Test prompt", timeout=1)

        assert result.success is False
        assert result.exit_code == -1
        assert "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_run_iteration_parses_json_output(self, claude_adapter):
        """Test that JSON output is parsed."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b'{"result": "success", "data": 123}', b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await claude_adapter.run_iteration("Test prompt")

        assert result.parsed_output is not None
        assert result.parsed_output["result"] == "success"
        assert result.parsed_output["data"] == 123

    @pytest.mark.asyncio
    async def test_run_iteration_extracts_session_id(self, claude_adapter):
        """Test that session ID is extracted from output."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b'{"session_id": "extracted-123", "status": "done"}', b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await claude_adapter.run_iteration("Test prompt")

        assert result.session_id == "extracted-123"

    @pytest.mark.asyncio
    async def test_run_iteration_extracts_cost(self, claude_adapter):
        """Test that cost is extracted from output."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b'{"cost_usd": 0.05, "status": "done"}', b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await claude_adapter.run_iteration("Test prompt")

        assert result.cost_usd == 0.05

    @pytest.mark.asyncio
    async def test_run_iteration_extracts_files_changed(self, claude_adapter):
        """Test that changed files are extracted from output."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(
                b'{"files_modified": ["a.py"], "files_created": ["b.py"], "status": "done"}',
                b"",
            )
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await claude_adapter.run_iteration("Test prompt")

        assert "a.py" in result.files_changed
        assert "b.py" in result.files_changed


class TestAdapterRegistry:
    """Tests for adapter registry."""

    def test_registry_contains_all_types(self):
        """Test that registry contains all agent types."""
        assert AgentType.CLAUDE in ADAPTER_REGISTRY
        assert AgentType.CURSOR in ADAPTER_REGISTRY
        assert AgentType.GEMINI in ADAPTER_REGISTRY

    def test_registry_types_are_classes(self):
        """Test that registry values are adapter classes."""
        for _agent_type, adapter_class in ADAPTER_REGISTRY.items():
            assert issubclass(adapter_class, AgentAdapter)
