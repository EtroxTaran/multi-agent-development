"""Tests for the deployment controller."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from orchestrator.optimization.deployer import (
    DeploymentController,
    DeploymentResult,
    DeploymentConfig,
)
from orchestrator.optimization.scheduler import (
    OptimizationScheduler,
    SchedulerConfig,
    OptimizationTrigger,
)
from orchestrator.db.repositories.prompts import (
    PromptStatus,
    OptimizationMethod,
)


class TestDeploymentResult:
    """Tests for deployment result."""

    def test_success_result(self):
        """Test successful deployment result."""
        result = DeploymentResult(
            success=True,
            version_id="pv-claude-test-v2",
            from_status="canary",
            to_status="production",
            metrics={"canary_score": 8.5},
        )
        assert result.success
        assert result.version_id == "pv-claude-test-v2"
        assert not result.rollback_performed

    def test_rollback_result(self):
        """Test rollback result."""
        result = DeploymentResult(
            success=False,
            version_id="pv-claude-test-v2",
            from_status="canary",
            to_status="draft",
            error="Score regression",
            rollback_performed=True,
        )
        assert not result.success
        assert result.rollback_performed

    def test_to_dict(self):
        """Test serialization."""
        result = DeploymentResult(
            success=True,
            version_id="test-v1",
            from_status="shadow",
            to_status="canary",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["version_id"] == "test-v1"


class TestDeploymentConfig:
    """Tests for deployment configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DeploymentConfig()
        assert config.shadow_test_count == 10
        assert config.canary_percentage == 0.1
        assert config.canary_test_count == 10
        assert config.rollback_threshold == -0.5
        assert config.minimum_score == 5.0
        assert config.auto_promote is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = DeploymentConfig(
            shadow_test_count=5,
            canary_percentage=0.2,
            auto_promote=False,
        )
        assert config.shadow_test_count == 5
        assert config.canary_percentage == 0.2
        assert config.auto_promote is False


class TestDeploymentController:
    """Tests for deployment controller."""

    @pytest.fixture
    def controller(self):
        """Create a controller with mocked repos."""
        controller = DeploymentController(
            project_name="test",
            config=DeploymentConfig(
                shadow_test_count=2,
                canary_test_count=2,
            ),
        )
        return controller

    @pytest.mark.asyncio
    async def test_start_shadow_testing_success(self, controller):
        """Test starting shadow testing."""
        # Mock the prompt repo
        controller._prompt_repo = MagicMock()
        controller._prompt_repo.find_by_id = AsyncMock(return_value={
            "version_id": "test-v1",
            "status": "draft",
        })
        controller._prompt_repo.update_status = AsyncMock()

        result = await controller.start_shadow_testing("test-v1")

        assert result.success
        assert result.from_status == "draft"
        assert result.to_status == "shadow"
        controller._prompt_repo.update_status.assert_called_once_with("test-v1", "shadow")

    @pytest.mark.asyncio
    async def test_start_shadow_testing_wrong_status(self, controller):
        """Test starting shadow testing from wrong status."""
        controller._prompt_repo = MagicMock()
        controller._prompt_repo.find_by_id = AsyncMock(return_value={
            "version_id": "test-v1",
            "status": "production",  # Wrong status
        })

        result = await controller.start_shadow_testing("test-v1")

        assert not result.success
        assert "draft versions" in result.error

    @pytest.mark.asyncio
    async def test_start_shadow_testing_not_found(self, controller):
        """Test starting shadow testing for non-existent version."""
        controller._prompt_repo = MagicMock()
        controller._prompt_repo.find_by_id = AsyncMock(return_value=None)

        result = await controller.start_shadow_testing("nonexistent")

        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_evaluate_shadow_insufficient_tests(self, controller):
        """Test shadow evaluation with insufficient tests."""
        controller._prompt_repo = MagicMock()
        controller._prompt_repo.find_by_id = AsyncMock(return_value={
            "version_id": "test-v1",
            "status": "shadow",
            "agent": "claude",
            "template_name": "default",
            "content": "test prompt",
        })

        controller._eval_repo = MagicMock()
        controller._eval_repo.get_by_prompt_hash = AsyncMock(return_value=[
            {"overall_score": 8.0},  # Only 1, need 2
        ])

        result = await controller.evaluate_shadow_test("test-v1")

        assert not result.success
        assert "Insufficient shadow tests" in result.error

    @pytest.mark.asyncio
    async def test_evaluate_shadow_promote_to_canary(self, controller):
        """Test shadow evaluation promoting to canary."""
        controller._prompt_repo = MagicMock()
        controller._prompt_repo.find_by_id = AsyncMock(return_value={
            "version_id": "test-v1",
            "status": "shadow",
            "agent": "claude",
            "template_name": "default",
            "content": "test prompt",
        })
        controller._prompt_repo.get_production_version = AsyncMock(return_value={
            "metrics": {"avg_score": 7.0},
        })
        controller._prompt_repo.update_status = AsyncMock()
        controller._prompt_repo.update_metrics = AsyncMock()

        controller._eval_repo = MagicMock()
        controller._eval_repo.get_by_prompt_hash = AsyncMock(return_value=[
            {"overall_score": 8.0},
            {"overall_score": 8.5},
        ])

        result = await controller.evaluate_shadow_test("test-v1")

        assert result.success
        assert result.to_status == "canary"
        assert result.metrics["shadow_avg_score"] == 8.25

    @pytest.mark.asyncio
    async def test_evaluate_shadow_reject_low_score(self, controller):
        """Test shadow evaluation rejecting low score."""
        controller._prompt_repo = MagicMock()
        controller._prompt_repo.find_by_id = AsyncMock(return_value={
            "version_id": "test-v1",
            "status": "shadow",
            "agent": "claude",
            "template_name": "default",
            "content": "test prompt",
        })
        controller._prompt_repo.get_production_version = AsyncMock(return_value=None)
        controller._prompt_repo.update_status = AsyncMock()

        controller._eval_repo = MagicMock()
        controller._eval_repo.get_by_prompt_hash = AsyncMock(return_value=[
            {"overall_score": 3.0},
            {"overall_score": 4.0},
        ])

        result = await controller.evaluate_shadow_test("test-v1")

        assert not result.success
        assert result.to_status == "draft"
        assert "below minimum" in result.error

    @pytest.mark.asyncio
    async def test_rollback(self, controller):
        """Test version rollback."""
        controller._prompt_repo = MagicMock()
        controller._prompt_repo.find_by_id = AsyncMock(return_value={
            "version_id": "test-v1",
            "status": "canary",
        })
        controller._prompt_repo.update_status = AsyncMock()
        controller._prompt_repo.update_metrics = AsyncMock()

        result = await controller.rollback("test-v1", "Test rollback")

        assert result.success
        assert result.rollback_performed
        assert result.to_status == "draft"

    @pytest.mark.asyncio
    async def test_rollback_production_fails(self, controller):
        """Test that rollback of production version fails."""
        controller._prompt_repo = MagicMock()
        controller._prompt_repo.find_by_id = AsyncMock(return_value={
            "version_id": "test-v1",
            "status": "production",
        })

        result = await controller.rollback("test-v1", "Should fail")

        assert not result.success
        assert "Cannot rollback production" in result.error


class TestOptimizationTrigger:
    """Tests for optimization trigger."""

    def test_trigger_creation(self):
        """Test creating an optimization trigger."""
        trigger = OptimizationTrigger(
            agent="claude",
            template_name="default",
            reason="Low score",
            priority=8,
        )
        assert trigger.agent == "claude"
        assert trigger.priority == 8
        assert trigger.triggered_at  # Should have timestamp


class TestSchedulerConfig:
    """Tests for scheduler configuration."""

    def test_default_config(self):
        """Test default configuration."""
        config = SchedulerConfig()
        assert config.score_threshold == 7.0
        assert config.min_samples == 10
        assert config.optimization_cooldown_hours == 24
        assert config.auto_optimize is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = SchedulerConfig(
            score_threshold=6.5,
            min_samples=5,
            auto_optimize=False,
        )
        assert config.score_threshold == 6.5
        assert config.min_samples == 5


class TestOptimizationScheduler:
    """Tests for optimization scheduler."""

    @pytest.fixture
    def scheduler(self):
        """Create a scheduler."""
        return OptimizationScheduler(
            project_dir="/test",
            project_name="test",
            config=SchedulerConfig(
                min_samples=5,
                optimization_cooldown_hours=1,
            ),
        )

    def test_queue_optimization(self, scheduler):
        """Test queuing an optimization."""
        result = scheduler.queue_optimization(
            agent="claude",
            template_name="default",
            reason="Test",
            priority=5,
        )
        assert result is True
        assert scheduler.queue_size == 1

    def test_queue_optimization_duplicate(self, scheduler):
        """Test queuing duplicate optimization."""
        scheduler.queue_optimization("claude", "default", "Test", 5)
        scheduler.queue_optimization("claude", "default", "Test 2", 7)

        # Should update priority instead of adding duplicate
        assert scheduler.queue_size == 1

    def test_queue_priority_ordering(self, scheduler):
        """Test that queue is ordered by priority."""
        scheduler.queue_optimization("claude", "low", "Low priority", 3)
        scheduler.queue_optimization("cursor", "high", "High priority", 9)
        scheduler.queue_optimization("gemini", "medium", "Medium priority", 5)

        status = scheduler.get_queue_status()
        assert status[0]["priority"] == 9
        assert status[1]["priority"] == 5
        assert status[2]["priority"] == 3

    def test_get_queue_status(self, scheduler):
        """Test getting queue status."""
        scheduler.queue_optimization("claude", "default", "Test", 5)

        status = scheduler.get_queue_status()
        assert len(status) == 1
        assert status[0]["agent"] == "claude"
        assert status[0]["template"] == "default"


class TestPromptStatus:
    """Tests for prompt status constants."""

    def test_status_values(self):
        """Test status constant values."""
        assert PromptStatus.DRAFT == "draft"
        assert PromptStatus.SHADOW == "shadow"
        assert PromptStatus.CANARY == "canary"
        assert PromptStatus.PRODUCTION == "production"
        assert PromptStatus.RETIRED == "retired"


class TestOptimizationMethod:
    """Tests for optimization method constants."""

    def test_method_values(self):
        """Test method constant values."""
        assert OptimizationMethod.MANUAL == "manual"
        assert OptimizationMethod.OPRO == "opro"
        assert OptimizationMethod.BOOTSTRAP == "bootstrap"
        assert OptimizationMethod.INSTRUCTION == "instruction"
