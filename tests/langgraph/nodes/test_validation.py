"""Tests for validation nodes.

Tests cursor_validate_node, gemini_validate_node, and validation_fan_in_node.
"""

from unittest.mock import patch

import pytest

from orchestrator.langgraph.nodes.validation import (
    _build_validation_correction_prompt,
    validation_fan_in_node,
)
from orchestrator.langgraph.state import PhaseState


@pytest.mark.integration
class TestCursorValidateNode:
    """Tests for cursor_validate_node - requires full infrastructure setup."""

    @pytest.mark.skip(reason="Integration test - requires SpecialistRunner infrastructure")
    @pytest.mark.asyncio
    async def test_successful_validation(self, workflow_state_phase_2):
        """Test successful cursor validation."""
        pass


@pytest.mark.integration
class TestGeminiValidateNode:
    """Tests for gemini_validate_node - requires full infrastructure setup."""

    @pytest.mark.skip(reason="Integration test - requires SpecialistRunner infrastructure")
    @pytest.mark.asyncio
    async def test_successful_validation(self, workflow_state_phase_2):
        """Test successful gemini validation."""
        pass


class TestValidationFanIn:
    """Tests for validation_fan_in_node."""

    @pytest.mark.asyncio
    async def test_missing_cursor_feedback(self, workflow_state_phase_2, gemini_feedback_approved):
        """Test fan-in with missing cursor feedback."""
        workflow_state_phase_2["validation_feedback"] = {
            "gemini": gemini_feedback_approved,
        }

        result = await validation_fan_in_node(workflow_state_phase_2)

        assert "errors" in result
        assert "cursor" in str(result["errors"])

    @pytest.mark.asyncio
    async def test_missing_gemini_feedback(self, workflow_state_phase_2, cursor_feedback_approved):
        """Test fan-in with missing gemini feedback."""
        workflow_state_phase_2["validation_feedback"] = {
            "cursor": cursor_feedback_approved,
        }

        result = await validation_fan_in_node(workflow_state_phase_2)

        assert "errors" in result
        assert "gemini" in str(result["errors"])

    @pytest.mark.asyncio
    async def test_both_approved(
        self, workflow_state_phase_2, cursor_feedback_approved, gemini_feedback_approved
    ):
        """Test fan-in when both agents approve."""
        workflow_state_phase_2["validation_feedback"] = {
            "cursor": cursor_feedback_approved,
            "gemini": gemini_feedback_approved,
        }

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await validation_fan_in_node(workflow_state_phase_2)

        assert result["next_decision"] == "continue"
        assert result["current_phase"] == 3

    @pytest.mark.asyncio
    async def test_cursor_rejects(
        self, workflow_state_phase_2, cursor_feedback_rejected, gemini_feedback_approved
    ):
        """Test fan-in when cursor rejects."""
        workflow_state_phase_2["validation_feedback"] = {
            "cursor": cursor_feedback_rejected,
            "gemini": gemini_feedback_approved,
        }

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await validation_fan_in_node(workflow_state_phase_2)

        # With cursor rejection for security issues, should not pass
        assert result["next_decision"] in ["retry", "escalate"]

    @pytest.mark.asyncio
    async def test_gemini_rejects(
        self, workflow_state_phase_2, cursor_feedback_approved, gemini_feedback_rejected
    ):
        """Test fan-in when gemini rejects."""
        workflow_state_phase_2["validation_feedback"] = {
            "cursor": cursor_feedback_approved,
            "gemini": gemini_feedback_rejected,
        }

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await validation_fan_in_node(workflow_state_phase_2)

        assert result["next_decision"] in ["retry", "escalate"]

    @pytest.mark.asyncio
    async def test_both_reject(
        self, workflow_state_phase_2, cursor_feedback_rejected, gemini_feedback_rejected
    ):
        """Test fan-in when both agents reject."""
        workflow_state_phase_2["validation_feedback"] = {
            "cursor": cursor_feedback_rejected,
            "gemini": gemini_feedback_rejected,
        }

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await validation_fan_in_node(workflow_state_phase_2)

        assert result["next_decision"] in ["retry", "escalate"]

    @pytest.mark.asyncio
    async def test_updates_phase_status(
        self, workflow_state_phase_2, cursor_feedback_approved, gemini_feedback_approved
    ):
        """Test fan-in updates phase status."""
        workflow_state_phase_2["validation_feedback"] = {
            "cursor": cursor_feedback_approved,
            "gemini": gemini_feedback_approved,
        }
        workflow_state_phase_2["phase_status"] = {"2": PhaseState()}

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await validation_fan_in_node(workflow_state_phase_2)

        assert "phase_status" in result

    @pytest.mark.asyncio
    async def test_dynamic_weights_for_security_task(
        self, workflow_state_phase_2, cursor_feedback_rejected, gemini_feedback_approved
    ):
        """Test dynamic weights favor cursor for security tasks."""
        # Set up a security-focused task
        workflow_state_phase_2["current_task"] = {
            "id": "T1",
            "title": "Implement authentication system",
            "type": "SECURITY",
        }
        workflow_state_phase_2["validation_feedback"] = {
            "cursor": cursor_feedback_rejected,  # Score 4.0
            "gemini": gemini_feedback_approved,  # Score 8.0
        }

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await validation_fan_in_node(workflow_state_phase_2)

        # For security tasks, cursor has higher weight (0.8)
        # So cursor rejection should carry more weight
        assert result["next_decision"] in ["retry", "escalate"]

    @pytest.mark.asyncio
    async def test_dynamic_weights_for_architecture_task(
        self, workflow_state_phase_2, cursor_feedback_approved, gemini_feedback_rejected
    ):
        """Test dynamic weights favor gemini for architecture tasks."""
        # Set up an architecture-focused task
        workflow_state_phase_2["current_task"] = {
            "id": "T1",
            "title": "Refactor service layer architecture",
            "type": "ARCHITECTURE",
        }
        workflow_state_phase_2["validation_feedback"] = {
            "cursor": cursor_feedback_approved,  # Score 8.5
            "gemini": gemini_feedback_rejected,  # Score 5.0
        }

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await validation_fan_in_node(workflow_state_phase_2)

        # For architecture tasks, gemini has higher weight (0.7)
        # So gemini rejection should carry more weight
        assert result["next_decision"] in ["retry", "escalate"]


class TestBuildValidationCorrectionPrompt:
    """Tests for _build_validation_correction_prompt helper."""

    def test_builds_prompt_with_blocking_issues(
        self, cursor_feedback_rejected, gemini_feedback_rejected
    ):
        """Test prompt includes blocking issues."""
        blocking = ["SQL injection vulnerability", "Missing authentication"]

        prompt = _build_validation_correction_prompt(
            cursor_feedback_rejected, gemini_feedback_rejected, blocking
        )

        assert "SQL injection vulnerability" in prompt
        assert "Missing authentication" in prompt
        assert "BLOCKING" in prompt.upper()

    def test_builds_prompt_with_cursor_findings(
        self, cursor_feedback_rejected, gemini_feedback_approved
    ):
        """Test prompt includes cursor findings."""
        prompt = _build_validation_correction_prompt(
            cursor_feedback_rejected, gemini_feedback_approved, []
        )

        # Should include security/code findings section
        assert "Security" in prompt or "Code" in prompt

    def test_builds_prompt_with_gemini_comments(
        self, cursor_feedback_approved, gemini_feedback_rejected
    ):
        """Test prompt includes gemini architecture comments."""
        prompt = _build_validation_correction_prompt(
            cursor_feedback_approved, gemini_feedback_rejected, []
        )

        assert "Architecture" in prompt

    def test_builds_prompt_with_instructions(
        self, cursor_feedback_approved, gemini_feedback_approved
    ):
        """Test prompt includes instructions."""
        prompt = _build_validation_correction_prompt(
            cursor_feedback_approved, gemini_feedback_approved, []
        )

        assert "Instructions" in prompt
