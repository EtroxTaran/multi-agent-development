"""Unit tests for enhanced ClaudeAgent features."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.agents.claude_agent import (
    ClaudeAgent,
    PLAN_MODE_FILE_THRESHOLD,
    PLAN_MODE_ALWAYS_COMPLEXITIES,
)


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project = tmp_path / "test-project"
    project.mkdir()

    # Create schemas directory
    schemas = project / "schemas"
    schemas.mkdir()
    (schemas / "plan-schema.json").write_text('{"type": "object"}')
    (schemas / "tasks-schema.json").write_text('{"type": "object"}')

    return project


@pytest.fixture
def claude_agent(temp_project: Path) -> ClaudeAgent:
    """Create a Claude agent for testing."""
    return ClaudeAgent(temp_project)


class TestPlanModeDetection:
    """Tests for plan mode detection."""

    def test_should_use_plan_mode_high_complexity(self, claude_agent: ClaudeAgent):
        """Test plan mode is used for high complexity tasks."""
        result = claude_agent.should_use_plan_mode(
            estimated_complexity="high",
        )
        assert result is True

    def test_should_use_plan_mode_many_files(self, claude_agent: ClaudeAgent):
        """Test plan mode is used when touching many files."""
        result = claude_agent.should_use_plan_mode(
            files_to_create=["a.py", "b.py"],
            files_to_modify=["c.py"],
        )
        # 3 files >= PLAN_MODE_FILE_THRESHOLD (3)
        assert result is True

    def test_should_not_use_plan_mode_few_files(self, claude_agent: ClaudeAgent):
        """Test plan mode is not used for few files."""
        result = claude_agent.should_use_plan_mode(
            files_to_create=["a.py"],
            files_to_modify=["b.py"],
        )
        # 2 files < PLAN_MODE_FILE_THRESHOLD (3)
        assert result is False

    def test_should_not_use_plan_mode_low_complexity(self, claude_agent: ClaudeAgent):
        """Test plan mode not used for low complexity simple tasks."""
        result = claude_agent.should_use_plan_mode(
            files_to_create=["a.py"],
            estimated_complexity="low",
        )
        assert result is False


class TestBuildCommand:
    """Tests for command building."""

    def test_basic_command(self, claude_agent: ClaudeAgent):
        """Test basic command building."""
        command = claude_agent.build_command("Test prompt")

        assert "claude" in command
        assert "-p" in command
        assert "Test prompt" in command
        assert "--output-format" in command
        assert "json" in command

    def test_plan_mode_flag(self, claude_agent: ClaudeAgent):
        """Test plan mode flag is added."""
        command = claude_agent.build_command(
            "Test prompt",
            use_plan_mode=True,
        )

        assert "--permission-mode" in command
        idx = command.index("--permission-mode")
        assert command[idx + 1] == "plan"

    def test_max_turns_flag(self, claude_agent: ClaudeAgent):
        """Test max turns flag is added."""
        command = claude_agent.build_command(
            "Test prompt",
            max_turns=20,
        )

        assert "--max-turns" in command
        idx = command.index("--max-turns")
        assert command[idx + 1] == "20"

    def test_budget_flag(self, claude_agent: ClaudeAgent):
        """Test budget flag is added."""
        command = claude_agent.build_command(
            "Test prompt",
            budget_usd=0.50,
        )

        assert "--max-budget-usd" in command
        idx = command.index("--max-budget-usd")
        assert command[idx + 1] == "0.5"

    def test_fallback_model_flag(self, claude_agent: ClaudeAgent):
        """Test fallback model flag is added."""
        command = claude_agent.build_command(
            "Test prompt",
            fallback_model="haiku",
        )

        assert "--fallback-model" in command
        idx = command.index("--fallback-model")
        assert command[idx + 1] == "haiku"

    def test_json_schema_flag(self, claude_agent: ClaudeAgent):
        """Test JSON schema flag is added."""
        command = claude_agent.build_command(
            "Test prompt",
            output_schema="plan-schema.json",
        )

        assert "--json-schema" in command

    def test_allowed_tools(self, claude_agent: ClaudeAgent):
        """Test allowed tools are included."""
        command = claude_agent.build_command("Test prompt")

        assert "--allowedTools" in command
        idx = command.index("--allowedTools")
        tools = command[idx + 1]
        assert "Read" in tools
        assert "Write" in tools

    def test_session_resume_with_existing_session(self, claude_agent: ClaudeAgent):
        """Test session resume when session exists.

        NOTE: With DB migration, we need to mock get_resume_args to return
        the expected session ID since the DB is mocked globally.
        """
        if claude_agent.session_manager:
            # Mock get_resume_args to return the expected session
            claude_agent.session_manager.get_resume_args = MagicMock(
                return_value=["--resume", "existing-session"]
            )

        command = claude_agent.build_command(
            "Test prompt",
            task_id="T1",
            resume_session=True,
        )

        assert "--resume" in command
        idx = command.index("--resume")
        assert command[idx + 1] == "existing-session"

    def test_session_id_for_new_session(self, claude_agent: ClaudeAgent):
        """Test session ID is set for new sessions."""
        command = claude_agent.build_command(
            "Test prompt",
            task_id="T2",
            resume_session=True,  # But no existing session
        )

        assert "--session-id" in command


class TestSessionManager:
    """Tests for session manager integration."""

    def test_session_manager_created(self, claude_agent: ClaudeAgent):
        """Test session manager is created when enabled."""
        assert claude_agent.session_manager is not None

    def test_session_manager_disabled(self, temp_project: Path):
        """Test session manager is not created when disabled."""
        agent = ClaudeAgent(temp_project, enable_session_continuity=False)
        assert agent.session_manager is None

    def test_close_task_session(self, claude_agent: ClaudeAgent):
        """Test closing a task session."""
        if claude_agent.session_manager:
            claude_agent.session_manager.create_session("T1")

        result = claude_agent.close_task_session("T1")
        assert result is True

        # Session should be inactive now
        session = claude_agent.session_manager.get_session("T1")
        assert session is None


class TestRunTask:
    """Tests for run_task method."""

    def test_run_task_prompt_format(self, claude_agent: ClaudeAgent):
        """Test that run_task creates proper prompt."""
        task = {
            "id": "T1",
            "title": "Implement calculator",
            "description": "Create a calculator module",
            "acceptance_criteria": ["Add function works", "Tests pass"],
            "files_to_create": ["src/calc.py"],
            "files_to_modify": [],
            "test_files": ["tests/test_calc.py"],
        }

        # Mock the run method to capture the prompt
        with patch.object(claude_agent, "run") as mock_run:
            mock_run.return_value = MagicMock(success=True)
            claude_agent.run_task(task)

            # Check that run was called with appropriate arguments
            call_args = mock_run.call_args
            prompt = call_args.kwargs.get("prompt", call_args.args[0] if call_args.args else "")

            assert "T1" in prompt
            assert "Implement calculator" in prompt
            assert "Add function works" in prompt
            assert "src/calc.py" in prompt


class TestDefaults:
    """Tests for default configuration."""

    def test_default_fallback_model(self, temp_project: Path):
        """Test default fallback model is sonnet."""
        agent = ClaudeAgent(temp_project)
        assert agent.default_fallback_model == "claude-4-5-sonnet"

    def test_custom_fallback_model(self, temp_project: Path):
        """Test custom fallback model."""
        agent = ClaudeAgent(temp_project, default_fallback_model="haiku")
        assert agent.default_fallback_model == "haiku"

    def test_default_budget(self, temp_project: Path):
        """Test default budget is None (unlimited)."""
        agent = ClaudeAgent(temp_project)
        assert agent.default_budget_usd is None

    def test_custom_budget(self, temp_project: Path):
        """Test custom default budget."""
        agent = ClaudeAgent(temp_project, default_budget_usd=1.00)
        assert agent.default_budget_usd == 1.00


class TestHelperMethods:
    """Tests for helper methods."""

    def test_format_criteria_with_items(self, claude_agent: ClaudeAgent):
        """Test formatting acceptance criteria."""
        criteria = ["Test passes", "No lint errors"]
        result = claude_agent._format_criteria(criteria)

        assert "- [ ] Test passes" in result
        assert "- [ ] No lint errors" in result

    def test_format_criteria_empty(self, claude_agent: ClaudeAgent):
        """Test formatting empty criteria."""
        result = claude_agent._format_criteria([])
        assert "No specific criteria defined" in result

    def test_format_list_with_items(self, claude_agent: ClaudeAgent):
        """Test formatting file list."""
        files = ["src/main.py", "src/utils.py"]
        result = claude_agent._format_list(files)

        assert "- src/main.py" in result
        assert "- src/utils.py" in result

    def test_format_list_empty(self, claude_agent: ClaudeAgent):
        """Test formatting empty list."""
        result = claude_agent._format_list([])
        assert "- None" in result


class TestSchemaDir:
    """Tests for schema directory finding."""

    def test_find_schema_dir_exists(self, temp_project: Path):
        """Test finding existing schema directory."""
        agent = ClaudeAgent(temp_project)
        assert agent.schema_dir is not None
        assert agent.schema_dir.name == "schemas"

    def test_find_schema_dir_parent(self, tmp_path: Path):
        """Test finding schema dir in parent."""
        parent = tmp_path / "parent"
        parent.mkdir()
        schemas = parent / "schemas"
        schemas.mkdir()
        (schemas / "test.json").write_text("{}")

        child = parent / "child"
        child.mkdir()

        agent = ClaudeAgent(child)
        assert agent.schema_dir is not None

    def test_custom_schema_dir(self, temp_project: Path):
        """Test custom schema directory."""
        custom = temp_project / "custom_schemas"
        custom.mkdir()

        agent = ClaudeAgent(temp_project, schema_dir=custom)
        assert agent.schema_dir == custom
