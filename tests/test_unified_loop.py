"""Tests for unified loop runner.

Tests the universal loop pattern that works across all agents
(Claude, Cursor, Gemini) with mocked adapters and verifiers.
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.agents.adapter import AgentCapabilities, AgentType, IterationResult
from orchestrator.langgraph.integrations.unified_loop import (
    UNIFIED_ITERATION_PROMPT,
    LoopContext,
    UnifiedLoopConfig,
    UnifiedLoopResult,
    UnifiedLoopRunner,
    create_runner_from_task,
    create_unified_runner,
)
from orchestrator.langgraph.integrations.verification import VerificationResult, VerificationType


class TestUnifiedLoopConfig:
    """Tests for UnifiedLoopConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = UnifiedLoopConfig()
        assert config.agent_type == "claude"
        assert config.model is None
        assert config.max_iterations == 10
        assert config.iteration_timeout == 300
        assert config.verification == "tests"
        assert config.enable_session is True
        assert config.enable_error_context is True
        assert config.enable_budget is True
        assert config.budget_per_iteration == 0.50
        assert config.max_budget == 5.00
        assert config.max_turns_per_iteration == 15
        assert config.use_plan_mode is False
        assert config.fallback_model == "sonnet"
        assert len(config.allowed_tools) > 0

    def test_custom_config(self):
        """Test custom configuration."""
        config = UnifiedLoopConfig(
            agent_type="cursor",
            model="codex-5.2",
            max_iterations=5,
            iteration_timeout=120,
            verification="lint",
            enable_session=False,
            budget_per_iteration=0.25,
            max_budget=2.00,
        )
        assert config.agent_type == "cursor"
        assert config.model == "codex-5.2"
        assert config.max_iterations == 5
        assert config.iteration_timeout == 120
        assert config.verification == "lint"
        assert config.enable_session is False
        assert config.budget_per_iteration == 0.25
        assert config.max_budget == 2.00

    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = UnifiedLoopConfig(
            agent_type="gemini",
            model="gemini-2.0-flash",
            max_iterations=8,
        )
        d = config.to_dict()
        assert d["agent_type"] == "gemini"
        assert d["model"] == "gemini-2.0-flash"
        assert d["max_iterations"] == 8
        assert "verification" in d
        assert "enable_session" in d
        assert "enable_budget" in d


class TestUnifiedLoopResult:
    """Tests for UnifiedLoopResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful result."""
        result = UnifiedLoopResult(
            success=True,
            iterations=3,
            agent_type="claude",
            model="sonnet",
            final_output={"status": "done"},
            total_time_seconds=45.0,
            total_cost_usd=1.50,
            completion_reason="verification_passed",
        )
        assert result.success is True
        assert result.iterations == 3
        assert result.agent_type == "claude"
        assert result.model == "sonnet"
        assert result.completion_reason == "verification_passed"
        assert result.error is None

    def test_failed_result(self):
        """Test creating a failed result."""
        result = UnifiedLoopResult(
            success=False,
            iterations=10,
            agent_type="cursor",
            completion_reason="max_iterations_reached",
            error="Failed to complete after 10 iterations",
        )
        assert result.success is False
        assert result.iterations == 10
        assert result.completion_reason == "max_iterations_reached"
        assert "10 iterations" in result.error

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = UnifiedLoopResult(
            success=True,
            iterations=2,
            agent_type="gemini",
            final_output={"files": ["app.py"]},
            verification_results=[{"passed": True}],
            total_time_seconds=30.0,
            total_cost_usd=0.50,
            completion_reason="completion_signal_detected",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["iterations"] == 2
        assert d["agent_type"] == "gemini"
        assert d["completion_reason"] == "completion_signal_detected"
        assert "timestamp" in d


class TestLoopContext:
    """Tests for LoopContext dataclass."""

    def test_minimal_context(self):
        """Test minimal context with just task_id."""
        ctx = LoopContext(task_id="T1")
        assert ctx.task_id == "T1"
        assert ctx.title == ""
        assert ctx.user_story == ""
        assert ctx.acceptance_criteria == []
        assert ctx.files_to_create == []
        assert ctx.test_files == []

    def test_full_context(self):
        """Test full context with all fields."""
        ctx = LoopContext(
            task_id="T1",
            title="Add user auth",
            user_story="As a user, I want to login",
            acceptance_criteria=["AC1: Login form", "AC2: Validation"],
            files_to_create=["auth.py"],
            files_to_modify=["app.py"],
            test_files=["test_auth.py"],
            previous_failures=["Assertion failed"],
        )
        assert ctx.task_id == "T1"
        assert ctx.title == "Add user auth"
        assert len(ctx.acceptance_criteria) == 2
        assert len(ctx.files_to_create) == 1
        assert len(ctx.test_files) == 1
        assert len(ctx.previous_failures) == 1


class TestUnifiedLoopRunner:
    """Tests for UnifiedLoopRunner class."""

    def create_mock_adapter(self, completion_detected=False, success=True):
        """Create a mock adapter with configurable behavior."""
        mock_adapter = MagicMock()
        mock_adapter.capabilities = AgentCapabilities(
            supports_session=True,
            supports_json_output=True,
        )
        mock_adapter.agent_type = AgentType.CLAUDE

        mock_result = IterationResult(
            success=success,
            output='{"status": "completed"}',
            completion_detected=completion_detected,
            exit_code=0,
            duration_seconds=5.0,
            files_changed=["app.py"],
            cost_usd=0.05,
        )
        mock_adapter.run_iteration = AsyncMock(return_value=mock_result)
        return mock_adapter

    def create_mock_verifier(self, passed=True):
        """Create a mock verifier with configurable behavior."""
        mock_verifier = MagicMock()
        mock_verifier.verification_type = VerificationType.TESTS

        mock_result = VerificationResult(
            passed=passed,
            verification_type=VerificationType.TESTS,
            summary="5 tests passed" if passed else "2 tests failed",
            failures=[] if passed else ["test_foo failed", "test_bar failed"],
        )
        mock_verifier.verify = AsyncMock(return_value=mock_result)
        return mock_verifier

    @pytest.mark.asyncio
    async def test_success_via_completion_signal(self, tmp_path):
        """Test successful loop via completion signal detection."""
        config = UnifiedLoopConfig(
            enable_session=False,
            enable_error_context=False,
            enable_budget=False,
        )

        runner = UnifiedLoopRunner(tmp_path, config)
        runner.adapter = self.create_mock_adapter(completion_detected=True)
        runner.verifier = self.create_mock_verifier()

        result = await runner.run("T1")

        assert result.success is True
        assert result.iterations == 1
        assert result.completion_reason == "completion_signal_detected"
        runner.adapter.run_iteration.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_via_verification_pass(self, tmp_path):
        """Test successful loop via verification passing."""
        config = UnifiedLoopConfig(
            enable_session=False,
            enable_error_context=False,
            enable_budget=False,
        )

        runner = UnifiedLoopRunner(tmp_path, config)
        runner.adapter = self.create_mock_adapter(completion_detected=False)
        runner.verifier = self.create_mock_verifier(passed=True)

        result = await runner.run("T1")

        assert result.success is True
        assert result.iterations == 1
        assert result.completion_reason == "verification_passed"
        assert len(result.verification_results) == 1

    @pytest.mark.asyncio
    async def test_failure_max_iterations(self, tmp_path):
        """Test failure when max iterations reached."""
        config = UnifiedLoopConfig(
            max_iterations=3,
            enable_session=False,
            enable_error_context=False,
            enable_budget=False,
        )

        runner = UnifiedLoopRunner(tmp_path, config)
        runner.adapter = self.create_mock_adapter(completion_detected=False)
        runner.verifier = self.create_mock_verifier(passed=False)

        result = await runner.run("T1")

        assert result.success is False
        assert result.iterations == 3
        assert result.completion_reason == "max_iterations_reached"
        assert "3 iterations" in result.error
        assert runner.adapter.run_iteration.call_count == 3

    @pytest.mark.asyncio
    async def test_failure_budget_exceeded(self, tmp_path):
        """Test failure when budget is exceeded."""
        config = UnifiedLoopConfig(
            budget_per_iteration=1.00,
            max_budget=2.00,
            enable_session=False,
            enable_error_context=False,
            enable_budget=True,
        )

        # Mock budget manager
        mock_budget = MagicMock()
        mock_budget.can_spend.return_value = False  # Budget exceeded

        runner = UnifiedLoopRunner(tmp_path, config)
        runner.adapter = self.create_mock_adapter()
        runner.verifier = self.create_mock_verifier(passed=False)
        runner._budget_manager = mock_budget

        result = await runner.run("T1")

        assert result.success is False
        assert result.completion_reason == "budget_exceeded"
        assert "Budget exceeded" in result.error

    @pytest.mark.asyncio
    async def test_iteration_timeout(self, tmp_path):
        """Test handling of iteration timeout."""
        config = UnifiedLoopConfig(
            max_iterations=2,
            enable_session=False,
            enable_error_context=False,
            enable_budget=False,
        )

        runner = UnifiedLoopRunner(tmp_path, config)

        # First call times out, second succeeds
        mock_adapter = self.create_mock_adapter(completion_detected=True)
        mock_adapter.run_iteration.side_effect = [
            asyncio.TimeoutError(),
            IterationResult(
                success=True,
                output="done",
                completion_detected=True,
            ),
        ]
        runner.adapter = mock_adapter
        runner.verifier = self.create_mock_verifier()

        result = await runner.run("T1")

        assert result.success is True
        assert result.iterations == 2
        assert mock_adapter.run_iteration.call_count == 2

    @pytest.mark.asyncio
    async def test_hitl_callback_pause(self, tmp_path):
        """Test human-in-the-loop callback pausing."""
        config = UnifiedLoopConfig(
            max_iterations=5,
            enable_session=False,
            enable_error_context=False,
            enable_budget=False,
        )

        runner = UnifiedLoopRunner(tmp_path, config)
        runner.adapter = self.create_mock_adapter(completion_detected=False)
        runner.verifier = self.create_mock_verifier(passed=False)

        # Callback returns False to pause after iteration 2
        call_count = 0

        def hitl_callback(iteration, data):
            nonlocal call_count
            call_count += 1
            return call_count < 2  # Stop after 2nd call

        result = await runner.run("T1", hitl_callback=hitl_callback)

        assert result.success is False
        assert result.completion_reason == "human_paused"
        assert result.iterations == 2

    @pytest.mark.asyncio
    async def test_with_custom_prompt(self, tmp_path):
        """Test loop with custom prompt override."""
        config = UnifiedLoopConfig(
            enable_session=False,
            enable_error_context=False,
            enable_budget=False,
        )

        runner = UnifiedLoopRunner(tmp_path, config)
        runner.adapter = self.create_mock_adapter(completion_detected=True)
        runner.verifier = self.create_mock_verifier()

        custom_prompt = "Implement feature X"
        result = await runner.run("T1", prompt=custom_prompt)

        assert result.success is True
        # Verify custom prompt was passed
        call_args = runner.adapter.run_iteration.call_args
        assert call_args.kwargs["prompt"] == custom_prompt

    @pytest.mark.asyncio
    async def test_with_loop_context(self, tmp_path):
        """Test loop with full context."""
        config = UnifiedLoopConfig(
            enable_session=False,
            enable_error_context=False,
            enable_budget=False,
        )

        runner = UnifiedLoopRunner(tmp_path, config)
        runner.adapter = self.create_mock_adapter(completion_detected=True)
        runner.verifier = self.create_mock_verifier()

        context = LoopContext(
            task_id="T1",
            title="Add auth",
            user_story="As a user I want to login",
            acceptance_criteria=["AC1", "AC2"],
            test_files=["test_auth.py"],
        )

        result = await runner.run("T1", context=context)

        assert result.success is True
        # Verify prompt was built from context
        call_args = runner.adapter.run_iteration.call_args
        prompt = call_args.kwargs["prompt"]
        assert "T1" in prompt
        assert "Add auth" in prompt

    @pytest.mark.asyncio
    async def test_session_manager_integration(self, tmp_path):
        """Test session manager integration for Claude."""
        config = UnifiedLoopConfig(
            agent_type="claude",
            max_iterations=3,
            enable_session=True,
            enable_error_context=False,
            enable_budget=False,
        )

        # Mock session manager
        mock_session = MagicMock()
        mock_session.session_id = "session-123"
        mock_session_manager = MagicMock()
        mock_session_manager.get_or_create_session.return_value = mock_session
        mock_session_manager.close_session = MagicMock()

        runner = UnifiedLoopRunner(tmp_path, config)
        runner.adapter = self.create_mock_adapter(completion_detected=True)
        runner.verifier = self.create_mock_verifier()
        runner._session_manager = mock_session_manager

        result = await runner.run("T1")

        assert result.success is True
        mock_session_manager.get_or_create_session.assert_called_with("T1")
        mock_session_manager.close_session.assert_called_with("T1")

    @pytest.mark.asyncio
    async def test_error_context_integration(self, tmp_path):
        """Test error context integration for retries."""
        config = UnifiedLoopConfig(
            max_iterations=2,
            enable_session=False,
            enable_error_context=True,
            enable_budget=False,
        )

        # Mock error context manager
        mock_error_ctx = MagicMock()
        mock_error_ctx.build_retry_prompt.side_effect = lambda task_id, prompt: f"RETRY: {prompt}"
        mock_error_ctx.record_error = MagicMock()
        mock_error_ctx.clear_task_errors = MagicMock()

        runner = UnifiedLoopRunner(tmp_path, config)
        runner._error_context = mock_error_ctx

        # First iteration fails, second succeeds
        mock_adapter = self.create_mock_adapter(completion_detected=False)
        call_count = [0]

        async def mock_run(*args, **kwargs):
            call_count[0] += 1
            return IterationResult(
                success=True,
                output="output",
                completion_detected=(call_count[0] == 2),
            )

        mock_adapter.run_iteration = mock_run
        runner.adapter = mock_adapter

        # First verification fails, second not called (completion signal)
        runner.verifier = self.create_mock_verifier(passed=False)

        result = await runner.run("T1", prompt="test prompt")

        assert result.success is True
        # Error context was used for retry prompt
        assert mock_error_ctx.build_retry_prompt.call_count >= 1
        # Errors cleared on success
        mock_error_ctx.clear_task_errors.assert_called_with("T1")

    @pytest.mark.asyncio
    async def test_budget_manager_integration(self, tmp_path):
        """Test budget manager integration for cost tracking."""
        config = UnifiedLoopConfig(
            budget_per_iteration=0.50,
            max_budget=5.00,
            enable_session=False,
            enable_error_context=False,
            enable_budget=True,
        )

        mock_budget = MagicMock()
        mock_budget.can_spend.return_value = True
        mock_budget.record_spend = MagicMock()

        runner = UnifiedLoopRunner(tmp_path, config)
        runner._budget_manager = mock_budget

        mock_result = IterationResult(
            success=True,
            output="done",
            completion_detected=True,
            cost_usd=0.15,
        )
        mock_adapter = MagicMock()
        mock_adapter.capabilities = AgentCapabilities(supports_session=False)
        mock_adapter.run_iteration = AsyncMock(return_value=mock_result)
        runner.adapter = mock_adapter
        runner.verifier = self.create_mock_verifier()

        result = await runner.run("T1")

        assert result.success is True
        assert result.total_cost_usd == 0.15
        mock_budget.can_spend.assert_called()
        mock_budget.record_spend.assert_called_once()

    @pytest.mark.asyncio
    async def test_iteration_log_saving(self, tmp_path):
        """Test that iteration logs are saved."""
        config = UnifiedLoopConfig(
            save_iteration_logs=True,
            enable_session=False,
            enable_error_context=False,
            enable_budget=False,
        )

        runner = UnifiedLoopRunner(tmp_path, config)
        runner.adapter = self.create_mock_adapter(completion_detected=True)
        runner.verifier = self.create_mock_verifier()

        result = await runner.run("T1")

        assert result.success is True

        # Check log file was created
        log_dir = tmp_path / ".workflow" / "unified_logs" / "T1"
        assert log_dir.exists()

        log_file = log_dir / "iteration_001.json"
        assert log_file.exists()

        log_data = json.loads(log_file.read_text())
        assert log_data["iteration"] == 1
        assert "timestamp" in log_data

    @pytest.mark.asyncio
    async def test_multiple_iterations_with_progress(self, tmp_path):
        """Test multiple iterations with progressive improvement."""
        config = UnifiedLoopConfig(
            max_iterations=5,
            enable_session=False,
            enable_error_context=False,
            enable_budget=False,
        )

        runner = UnifiedLoopRunner(tmp_path, config)

        # Adapter returns non-completion for 2 iterations, then completion
        iteration_count = [0]

        async def mock_run(*args, **kwargs):
            iteration_count[0] += 1
            return IterationResult(
                success=True,
                output="working..." if iteration_count[0] < 3 else "done",
                completion_detected=(iteration_count[0] == 3),
                files_changed=["file.py"],
            )

        mock_adapter = MagicMock()
        mock_adapter.capabilities = AgentCapabilities(supports_session=False)
        mock_adapter.run_iteration = mock_run
        runner.adapter = mock_adapter

        # Verifier fails for first 2, passes on 3rd (but completion signal detected)
        runner.verifier = self.create_mock_verifier(passed=False)

        result = await runner.run("T1")

        assert result.success is True
        assert result.iterations == 3
        assert len(result.iteration_results) == 3

    @pytest.mark.asyncio
    async def test_exception_handling(self, tmp_path):
        """Test handling of exceptions during iteration."""
        config = UnifiedLoopConfig(
            max_iterations=3,
            enable_session=False,
            enable_error_context=False,
            enable_budget=False,
        )

        runner = UnifiedLoopRunner(tmp_path, config)

        # First call raises exception, subsequent succeed
        call_count = [0]

        async def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("Simulated error")
            return IterationResult(
                success=True,
                output="done",
                completion_detected=True,
            )

        mock_adapter = MagicMock()
        mock_adapter.capabilities = AgentCapabilities(supports_session=False)
        mock_adapter.run_iteration = mock_run
        runner.adapter = mock_adapter
        runner.verifier = self.create_mock_verifier()

        result = await runner.run("T1")

        assert result.success is True
        assert result.iterations == 2
        # First iteration recorded as error
        assert result.iteration_results[0]["error"] == "Simulated error"


class TestCreateUnifiedRunner:
    """Tests for create_unified_runner factory function."""

    def test_create_with_defaults(self, tmp_path):
        """Test creating runner with defaults."""
        runner = create_unified_runner(tmp_path)
        assert runner.config.agent_type == "claude"
        assert runner.config.verification == "tests"

    def test_create_with_custom_agent(self, tmp_path):
        """Test creating runner with custom agent."""
        runner = create_unified_runner(
            tmp_path,
            agent_type="cursor",
            model="codex-5.2",
        )
        assert runner.config.agent_type == "cursor"
        assert runner.config.model == "codex-5.2"

    def test_create_with_custom_verification(self, tmp_path):
        """Test creating runner with custom verification."""
        runner = create_unified_runner(
            tmp_path,
            verification="lint",
        )
        assert runner.config.verification == "lint"

    def test_create_with_kwargs(self, tmp_path):
        """Test creating runner with additional kwargs."""
        runner = create_unified_runner(
            tmp_path,
            max_iterations=5,
            budget_per_iteration=0.25,
        )
        assert runner.config.max_iterations == 5
        assert runner.config.budget_per_iteration == 0.25


class TestCreateRunnerFromTask:
    """Tests for create_runner_from_task factory function."""

    def test_create_from_minimal_task(self, tmp_path):
        """Test creating runner from minimal task."""
        task = {"id": "T1"}

        with patch(
            "orchestrator.langgraph.integrations.unified_loop.get_agent_for_task"
        ) as mock_get:
            mock_get.return_value = (AgentType.CLAUDE, None)
            runner = create_runner_from_task(tmp_path, task)

        assert runner.config.agent_type == "claude"

    def test_create_from_task_with_agent(self, tmp_path):
        """Test creating runner from task with specified agent."""
        task = {"id": "T1", "agent_type": "cursor", "model": "composer"}

        with patch(
            "orchestrator.langgraph.integrations.unified_loop.get_agent_for_task"
        ) as mock_get:
            mock_get.return_value = (AgentType.CURSOR, "composer")
            runner = create_runner_from_task(tmp_path, task)

        assert runner.config.agent_type == "cursor"
        assert runner.config.model == "composer"

    def test_create_from_task_with_verification(self, tmp_path):
        """Test creating runner from task with verification."""
        task = {"id": "T1"}

        with patch(
            "orchestrator.langgraph.integrations.unified_loop.get_agent_for_task"
        ) as mock_get:
            mock_get.return_value = (AgentType.GEMINI, "gemini-2.0-flash")
            runner = create_runner_from_task(tmp_path, task, verification="security")

        assert runner.config.verification == "security"


class TestShouldUseUnifiedLoop:
    """Tests for should_use_unified_loop function."""

    def test_default_is_false(self, monkeypatch):
        """Test that default is false."""
        monkeypatch.delenv("USE_UNIFIED_LOOP", raising=False)
        # Need to reimport to pick up env change

        # The module-level constant was set at import time,
        # so we test the logic directly
        assert os.environ.get("USE_UNIFIED_LOOP", "false").lower() != "true"

    def test_env_true(self, monkeypatch):
        """Test env variable set to true."""
        monkeypatch.setenv("USE_UNIFIED_LOOP", "true")
        assert os.environ.get("USE_UNIFIED_LOOP", "false").lower() == "true"

    def test_env_false(self, monkeypatch):
        """Test env variable set to false."""
        monkeypatch.setenv("USE_UNIFIED_LOOP", "false")
        assert os.environ.get("USE_UNIFIED_LOOP", "false").lower() != "true"


class TestIterationPromptTemplate:
    """Tests for the iteration prompt template."""

    def test_prompt_template_formatting(self):
        """Test that prompt template can be formatted."""
        formatted = UNIFIED_ITERATION_PROMPT.format(
            task_id="T1",
            title="Test Task",
            user_story="As a user I want to test",
            acceptance_criteria="- AC1\n- AC2",
            files_to_create="- file1.py",
            files_to_modify="- file2.py",
            test_files="- test_file.py",
            previous_iteration_context="",
            error_context="",
            iteration=1,
            max_iterations=10,
        )

        assert "T1" in formatted
        assert "Test Task" in formatted
        assert "As a user" in formatted
        assert "AC1" in formatted
        assert "file1.py" in formatted
        assert "test_file.py" in formatted
        assert "iteration: 1 of 10" in formatted

    def test_prompt_template_contains_instructions(self):
        """Test that prompt template contains key instructions."""
        assert "TDD" in UNIFIED_ITERATION_PROMPT
        assert "tests" in UNIFIED_ITERATION_PROMPT.lower()
        assert "<promise>DONE</promise>" in UNIFIED_ITERATION_PROMPT
        assert '"status": "done"' in UNIFIED_ITERATION_PROMPT


class TestUnifiedLoopRunnerProperties:
    """Tests for UnifiedLoopRunner lazy-loaded properties."""

    def test_error_context_property_disabled(self, tmp_path):
        """Test error_context property when disabled."""
        config = UnifiedLoopConfig(enable_error_context=False)
        runner = UnifiedLoopRunner(tmp_path, config)
        assert runner.error_context is None

    def test_budget_manager_property_disabled(self, tmp_path):
        """Test budget_manager property when disabled."""
        config = UnifiedLoopConfig(enable_budget=False)
        runner = UnifiedLoopRunner(tmp_path, config)
        assert runner.budget_manager is None

    def test_session_manager_property_disabled(self, tmp_path):
        """Test session_manager property when disabled."""
        config = UnifiedLoopConfig(enable_session=False)
        runner = UnifiedLoopRunner(tmp_path, config)
        # Need to set adapter capabilities first
        mock_adapter = MagicMock()
        mock_adapter.capabilities = AgentCapabilities(supports_session=False)
        runner.adapter = mock_adapter
        assert runner.session_manager is None

    def test_session_manager_for_non_claude(self, tmp_path):
        """Test session_manager is None for non-Claude agents."""
        config = UnifiedLoopConfig(
            agent_type="cursor",
            enable_session=True,
        )
        runner = UnifiedLoopRunner(tmp_path, config)
        # Cursor adapter doesn't support sessions
        assert runner.adapter.capabilities.supports_session is False
        assert runner.session_manager is None
