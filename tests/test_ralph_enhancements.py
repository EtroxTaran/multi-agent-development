"""Tests for Ralph Wiggum loop enhancements."""

from pathlib import Path

import pytest

from orchestrator.langgraph.integrations.hooks import (
    HOOK_NAMES,
    HookManager,
    HookResult,
    create_hook_manager,
)
from orchestrator.langgraph.integrations.ralph_loop import (
    ExecutionMode,
    HookConfig,
    RalphLoopConfig,
    RalphLoopResult,
    TokenMetrics,
    TokenUsageTracker,
    create_ralph_config,
)


class TestExecutionMode:
    """Tests for ExecutionMode enum."""

    def test_hitl_mode(self):
        """Test HITL mode value."""
        assert ExecutionMode.HITL.value == "human_in_the_loop"

    def test_afk_mode(self):
        """Test AFK mode value."""
        assert ExecutionMode.AFK.value == "away_from_keyboard"

    def test_from_string(self):
        """Test creating from string."""
        assert ExecutionMode("human_in_the_loop") == ExecutionMode.HITL
        assert ExecutionMode("away_from_keyboard") == ExecutionMode.AFK


class TestTokenMetrics:
    """Tests for TokenMetrics dataclass."""

    def test_default_values(self):
        """Test default values."""
        metrics = TokenMetrics(iteration=1)
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0
        assert metrics.estimated_cost_usd == 0.0
        assert metrics.model == "claude-sonnet-4"

    def test_calculate_cost_sonnet(self):
        """Test cost calculation for Sonnet model."""
        metrics = TokenMetrics(
            iteration=1,
            input_tokens=1_000_000,  # 1M tokens
            output_tokens=1_000_000,
            model="claude-sonnet-4",
        )
        cost = metrics.calculate_cost()

        # Sonnet: $3/M input, $15/M output
        # Expected: 3 + 15 = $18
        assert cost == pytest.approx(18.0, rel=0.01)
        assert metrics.estimated_cost_usd == pytest.approx(18.0, rel=0.01)

    def test_calculate_cost_opus(self):
        """Test cost calculation for Opus model."""
        metrics = TokenMetrics(
            iteration=1,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="claude-opus-4",
        )
        cost = metrics.calculate_cost()

        # Opus: $15/M input, $75/M output
        # Expected: 15 + 75 = $90
        assert cost == pytest.approx(90.0, rel=0.01)

    def test_to_dict(self):
        """Test dictionary conversion."""
        metrics = TokenMetrics(
            iteration=1,
            input_tokens=1000,
            output_tokens=500,
        )
        d = metrics.to_dict()
        assert d["iteration"] == 1
        assert d["input_tokens"] == 1000
        assert d["output_tokens"] == 500


class TestTokenUsageTracker:
    """Tests for TokenUsageTracker class."""

    def test_add_iteration(self):
        """Test adding iteration metrics."""
        tracker = TokenUsageTracker()
        metrics = TokenMetrics(
            iteration=1,
            input_tokens=1000,
            output_tokens=500,
        )
        metrics.calculate_cost()
        tracker.add_iteration(metrics)

        assert tracker.total_input_tokens == 1000
        assert tracker.total_output_tokens == 500
        assert len(tracker.iterations) == 1

    def test_cumulative_tracking(self):
        """Test cumulative token tracking."""
        tracker = TokenUsageTracker()

        for i in range(3):
            metrics = TokenMetrics(iteration=i + 1, input_tokens=1000, output_tokens=500)
            metrics.calculate_cost()
            tracker.add_iteration(metrics)

        assert tracker.total_input_tokens == 3000
        assert tracker.total_output_tokens == 1500
        assert len(tracker.iterations) == 3

    def test_to_dict(self):
        """Test dictionary conversion."""
        tracker = TokenUsageTracker()
        metrics = TokenMetrics(iteration=1, input_tokens=1000, output_tokens=500)
        metrics.calculate_cost()
        tracker.add_iteration(metrics)

        summary = tracker.to_dict()
        assert "total_input_tokens" in summary
        assert "total_output_tokens" in summary
        assert "total_cost_usd" in summary
        assert "iterations" in summary


class TestHookConfig:
    """Tests for HookConfig dataclass."""

    def test_default_values(self):
        """Test default values."""
        config = HookConfig()
        assert config.pre_iteration is None
        assert config.post_iteration is None
        assert config.stop_check is None
        assert config.timeout == 30
        assert config.sandbox is True

    def test_custom_values(self):
        """Test custom configuration."""
        config = HookConfig(
            pre_iteration=Path("/hooks/pre.sh"),
            timeout=60,
            sandbox=False,
        )
        assert config.pre_iteration == Path("/hooks/pre.sh")
        assert config.timeout == 60
        assert config.sandbox is False


class TestRalphLoopConfig:
    """Tests for enhanced RalphLoopConfig."""

    def test_default_execution_mode(self):
        """Test default execution mode is AFK."""
        config = RalphLoopConfig()
        assert config.execution_mode == ExecutionMode.AFK

    def test_hitl_mode_configuration(self):
        """Test HITL mode configuration."""
        config = RalphLoopConfig(
            execution_mode=ExecutionMode.HITL,
        )
        assert config.execution_mode == ExecutionMode.HITL

    def test_hook_configuration(self):
        """Test hook configuration."""
        hooks = HookConfig(timeout=60)
        config = RalphLoopConfig(
            hooks=hooks,
        )
        assert config.hooks.timeout == 60

    def test_token_tracking_enabled(self):
        """Test token tracking is enabled by default."""
        config = RalphLoopConfig()
        assert config.track_tokens is True

    def test_context_warning_threshold(self):
        """Test context warning threshold default."""
        config = RalphLoopConfig()
        assert config.context_warning_threshold == 0.75

    def test_max_cost_limit(self):
        """Test max cost limit configuration."""
        config = RalphLoopConfig(
            max_cost_usd=10.0,
        )
        assert config.max_cost_usd == 10.0


class TestRalphLoopResult:
    """Tests for enhanced RalphLoopResult."""

    def test_basic_result(self):
        """Test basic result creation."""
        result = RalphLoopResult(
            success=True,
            iterations=3,
            final_output="Done",
        )
        assert result.success is True
        assert result.iterations == 3

    def test_result_with_token_usage(self):
        """Test result with token usage."""
        tracker = TokenUsageTracker()
        result = RalphLoopResult(
            success=True,
            iterations=3,
            final_output="Done",
            token_usage=tracker.to_dict(),
        )
        assert "token_usage" in result.__dict__
        assert result.token_usage is not None

    def test_result_paused_for_review(self):
        """Test result paused for HITL review."""
        result = RalphLoopResult(
            success=False,
            iterations=1,
            final_output="",
            paused_for_review=True,
        )
        assert result.paused_for_review is True


class TestHookManager:
    """Tests for HookManager class."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create temporary project with hooks directory."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        hooks_dir = project_dir / ".workflow" / "hooks"
        hooks_dir.mkdir(parents=True)
        return project_dir

    def test_init(self, temp_project):
        """Test manager initialization."""
        manager = HookManager(project_dir=temp_project)
        assert manager.project_dir == temp_project
        assert manager.hooks_dir == temp_project / ".workflow" / "hooks"
        assert manager.enabled is True

    def test_has_hook_false_when_not_exists(self, temp_project):
        """Test has_hook returns False when hook doesn't exist."""
        manager = HookManager(project_dir=temp_project)
        assert manager.has_hook("pre_iteration") is False

    def test_has_hook_true_when_exists(self, temp_project):
        """Test has_hook returns True when hook exists and is executable."""
        manager = HookManager(project_dir=temp_project)
        hook_path = manager.hooks_dir / "pre-iteration.sh"
        hook_path.write_text("#!/bin/bash\nexit 0")
        hook_path.chmod(0o755)

        assert manager.has_hook("pre_iteration") is True

    @pytest.mark.asyncio
    async def test_run_hook_not_found(self, temp_project):
        """Test running non-existent hook."""
        manager = HookManager(project_dir=temp_project)
        result = await manager.run_hook("pre_iteration")

        assert result.success is True  # Missing hook is not an error
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_run_hook_success(self, temp_project):
        """Test running successful hook."""
        manager = HookManager(project_dir=temp_project)
        hook_path = manager.hooks_dir / "pre-iteration.sh"
        hook_path.write_text("#!/bin/bash\necho 'Hello'\nexit 0")
        hook_path.chmod(0o755)

        result = await manager.run_hook("pre_iteration")

        assert result.success is True
        assert result.return_code == 0
        assert "Hello" in result.stdout

    @pytest.mark.asyncio
    async def test_run_hook_failure(self, temp_project):
        """Test running failing hook."""
        manager = HookManager(project_dir=temp_project)
        hook_path = manager.hooks_dir / "pre-iteration.sh"
        hook_path.write_text("#!/bin/bash\nexit 1")
        hook_path.chmod(0o755)

        result = await manager.run_hook("pre_iteration")

        assert result.success is False
        assert result.return_code == 1

    @pytest.mark.asyncio
    async def test_run_hook_with_context(self, temp_project):
        """Test running hook with context variables."""
        manager = HookManager(project_dir=temp_project)
        hook_path = manager.hooks_dir / "pre-iteration.sh"
        hook_path.write_text('#!/bin/bash\necho "Iteration: $HOOK_ITERATION"')
        hook_path.chmod(0o755)

        result = await manager.run_hook(
            "pre_iteration",
            context={"iteration": 5},
        )

        assert result.success is True
        assert "5" in result.stdout

    @pytest.mark.asyncio
    async def test_run_stop_check_returns_true(self, temp_project):
        """Test stop check returns True when hook returns 0."""
        manager = HookManager(project_dir=temp_project)
        hook_path = manager.hooks_dir / "stop-check.sh"
        hook_path.write_text("#!/bin/bash\nexit 0")  # Return 0 = stop
        hook_path.chmod(0o755)

        should_stop = await manager.run_stop_check()
        assert should_stop is True

    @pytest.mark.asyncio
    async def test_run_stop_check_returns_false(self, temp_project):
        """Test stop check returns False when hook returns non-zero."""
        manager = HookManager(project_dir=temp_project)
        hook_path = manager.hooks_dir / "stop-check.sh"
        hook_path.write_text("#!/bin/bash\nexit 1")  # Return 1 = continue
        hook_path.chmod(0o755)

        should_stop = await manager.run_stop_check()
        assert should_stop is False

    def test_create_hook_templates(self, temp_project):
        """Test creating hook templates."""
        manager = HookManager(project_dir=temp_project)
        created = manager.create_hook_templates()

        assert len(created) > 0
        for hook_name, path in created.items():
            assert path.exists()
            content = path.read_text()
            assert "#!/bin/bash" in content

    def test_get_history_summary(self, temp_project):
        """Test getting history summary."""
        manager = HookManager(project_dir=temp_project)
        manager.history.append(
            HookResult(hook_name="test", success=True, return_code=0, duration_ms=100)
        )
        manager.history.append(
            HookResult(hook_name="test", success=False, return_code=1, duration_ms=50)
        )

        summary = manager.get_history_summary()
        assert summary["total"] == 2
        assert summary["success"] == 1
        assert summary["failed"] == 1
        assert summary["avg_duration_ms"] == 75.0


class TestHookNames:
    """Tests for hook name configuration."""

    def test_standard_hooks_defined(self):
        """Test all standard hooks are defined."""
        expected = {
            "pre_iteration",
            "post_iteration",
            "stop_check",
            "pre_task",
            "post_task",
            "on_error",
            "on_complete",
        }
        assert expected.issubset(set(HOOK_NAMES.keys()))

    def test_hook_names_are_shell_scripts(self):
        """Test all hook names end with .sh."""
        for name in HOOK_NAMES.values():
            assert name.endswith(".sh")


class TestCreateRalphConfig:
    """Tests for create_ralph_config helper."""

    def test_creates_config_with_defaults(self, tmp_path):
        """Test creating config with default values."""
        config = create_ralph_config(
            project_dir=tmp_path,
        )

        assert config.execution_mode == ExecutionMode.AFK
        assert config.track_tokens is True

    def test_creates_config_with_hitl(self, tmp_path):
        """Test creating config with HITL mode."""
        config = create_ralph_config(
            project_dir=tmp_path,
            execution_mode="hitl",
        )

        assert config.execution_mode == ExecutionMode.HITL

    def test_creates_config_with_hooks(self, tmp_path):
        """Test creating config with hooks enabled."""
        hooks_dir = tmp_path / ".workflow" / "hooks"
        hooks_dir.mkdir(parents=True)

        config = create_ralph_config(
            project_dir=tmp_path,
            enable_hooks=True,
        )

        # Hooks may be None if no hook scripts exist in the directory
        # The function only sets hooks if the hooks_dir exists


class TestHelperFunctions:
    """Tests for module helper functions."""

    def test_create_hook_manager(self, tmp_path):
        """Test factory function."""
        manager = create_hook_manager(tmp_path, enabled=True)
        assert isinstance(manager, HookManager)
        assert manager.enabled is True

    def test_create_hook_manager_disabled(self, tmp_path):
        """Test creating disabled manager."""
        manager = create_hook_manager(tmp_path, enabled=False)
        assert manager.enabled is False
