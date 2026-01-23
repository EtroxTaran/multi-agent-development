"""Tests for approval gate node.

Tests cover:
- Skipping when approval gates disabled
- Skipping when current phase not in approval_phases
- Context building for different phases
- LangGraph interrupt integration
- Response handling (approve/reject/request_changes)
- File persistence for context and response
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from orchestrator.langgraph.nodes.approval_gate import (
    approval_gate_node,
    _build_approval_context,
)
from orchestrator.langgraph.state import (
    WorkflowState,
    PhaseStatus,
    create_initial_state,
)


class TestApprovalGateSkipping:
    """Tests for approval gate skip conditions."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create project directory with config."""
        workflow_dir = tmp_path / ".workflow"
        workflow_dir.mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def mock_config_disabled(self):
        """Config with approval gates disabled."""
        config = MagicMock()
        config.workflow.features.approval_gates = False
        config.workflow.approval_phases = [2, 4]
        return config

    @pytest.fixture
    def mock_config_enabled(self):
        """Config with approval gates enabled."""
        config = MagicMock()
        config.workflow.features.approval_gates = True
        config.workflow.approval_phases = [2, 4]
        return config

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self, project_dir, mock_config_disabled):
        """Test that approval gate is skipped when disabled in config."""
        state = create_initial_state(
            project_dir=str(project_dir),
            project_name="test-project",
        )
        state["current_phase"] = 2

        with patch("orchestrator.langgraph.nodes.approval_gate.load_project_config") as mock_load:
            mock_load.return_value = mock_config_disabled

            result = await approval_gate_node(state)

        assert result["next_decision"] == "continue"
        assert "updated_at" in result

    @pytest.mark.asyncio
    async def test_skips_when_phase_not_in_list(self, project_dir, mock_config_enabled):
        """Test that approval gate is skipped when phase not in approval_phases."""
        state = create_initial_state(
            project_dir=str(project_dir),
            project_name="test-project",
        )
        state["current_phase"] = 3  # Not in approval_phases [2, 4]

        with patch("orchestrator.langgraph.nodes.approval_gate.load_project_config") as mock_load:
            mock_load.return_value = mock_config_enabled

            result = await approval_gate_node(state)

        assert result["next_decision"] == "continue"

    @pytest.mark.asyncio
    async def test_does_not_skip_when_enabled_and_phase_in_list(
        self, project_dir, mock_config_enabled
    ):
        """Test that approval gate triggers when enabled and phase is in list."""
        state = create_initial_state(
            project_dir=str(project_dir),
            project_name="test-project",
        )
        state["current_phase"] = 2  # In approval_phases [2, 4]

        with patch("orchestrator.langgraph.nodes.approval_gate.load_project_config") as mock_load:
            mock_load.return_value = mock_config_enabled

            with patch("orchestrator.langgraph.nodes.approval_gate.interrupt") as mock_interrupt:
                mock_interrupt.return_value = {"action": "approve", "feedback": ""}

                result = await approval_gate_node(state)

        # Interrupt should have been called
        mock_interrupt.assert_called_once()


class TestApprovalContextBuilding:
    """Tests for building approval context per phase."""

    @pytest.fixture
    def base_state(self, tmp_path):
        """Create base state for context building."""
        return {
            "project_dir": str(tmp_path),
            "project_name": "test-project",
            "current_phase": 2,
            "iteration_count": 1,
            "errors": [],
        }

    def test_context_includes_base_fields(self, base_state):
        """Test that context includes basic fields."""
        context = _build_approval_context(base_state, 2)

        assert context["phase"] == 2
        assert context["project_name"] == "test-project"
        assert context["iteration_count"] == 1

    def test_phase_2_includes_plan_summary(self, base_state):
        """Test that phase 2 context includes plan summary."""
        base_state["plan"] = {
            "tasks": [{"id": "T1"}, {"id": "T2"}],
            "estimated_complexity": "medium",
            "key_files": ["src/main.py", "src/utils.py"],
        }

        context = _build_approval_context(base_state, 2)

        assert "plan_summary" in context
        assert context["plan_summary"]["tasks"] == 2
        assert context["plan_summary"]["estimated_complexity"] == "medium"
        assert "src/main.py" in context["plan_summary"]["key_files"]

    def test_phase_3_includes_validation_summary(self, base_state):
        """Test that phase 3 context includes validation summary."""
        base_state["current_phase"] = 3

        # Create mock feedback objects
        mock_cursor_feedback = MagicMock()
        mock_cursor_feedback.to_dict.return_value = {}
        mock_cursor_feedback.approved = True
        mock_cursor_feedback.score = 8.0
        mock_cursor_feedback.concerns = ["Minor concern"]

        base_state["validation_feedback"] = {
            "cursor": mock_cursor_feedback,
        }

        context = _build_approval_context(base_state, 3)

        assert "validation_summary" in context
        assert context["validation_summary"]["cursor"]["approved"] is True
        assert context["validation_summary"]["cursor"]["score"] == 8.0
        assert context["validation_summary"]["cursor"]["concerns_count"] == 1

    def test_phase_4_includes_implementation_summary(self, base_state):
        """Test that phase 4 context includes implementation summary."""
        base_state["current_phase"] = 4
        base_state["implementation_result"] = {
            "status": "completed",
            "files_changed": ["src/main.py", "src/utils.py"],
            "tests_added": ["test_main.py"],
        }

        context = _build_approval_context(base_state, 4)

        assert "implementation_summary" in context
        assert context["implementation_summary"]["status"] == "completed"
        assert "src/main.py" in context["implementation_summary"]["files_changed"]

    def test_phase_5_includes_verification_summary(self, base_state):
        """Test that phase 5 context includes verification summary."""
        base_state["current_phase"] = 5

        mock_gemini_feedback = MagicMock()
        mock_gemini_feedback.to_dict.return_value = {}
        mock_gemini_feedback.approved = True
        mock_gemini_feedback.score = 9.0
        mock_gemini_feedback.concerns = []

        base_state["verification_feedback"] = {
            "gemini": mock_gemini_feedback,
        }

        context = _build_approval_context(base_state, 5)

        assert "verification_summary" in context
        assert context["verification_summary"]["gemini"]["approved"] is True

    def test_recent_errors_included(self, base_state):
        """Test that recent errors are included in context."""
        base_state["errors"] = [
            {"message": "Error 1", "timestamp": "2026-01-01"},
            {"message": "Error 2", "timestamp": "2026-01-02"},
            {"message": "Error 3", "timestamp": "2026-01-03"},
            {"message": "Error 4", "timestamp": "2026-01-04"},
            {"message": "Error 5", "timestamp": "2026-01-05"},
            {"message": "Error 6", "timestamp": "2026-01-06"},
        ]

        context = _build_approval_context(base_state, 2)

        assert "recent_errors" in context
        assert len(context["recent_errors"]) == 5  # Last 5 errors


class TestApprovalGateInterrupt:
    """Tests for LangGraph interrupt integration."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create project directory."""
        workflow_dir = tmp_path / ".workflow"
        workflow_dir.mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def mock_config(self):
        """Config with approval gates enabled."""
        config = MagicMock()
        config.workflow.features.approval_gates = True
        config.workflow.approval_phases = [2]
        return config

    @pytest.mark.asyncio
    async def test_interrupt_called_with_correct_payload(self, project_dir, mock_config):
        """Test that interrupt is called with correct payload structure."""
        state = create_initial_state(
            project_dir=str(project_dir),
            project_name="test-project",
        )
        state["current_phase"] = 2

        captured_payload = None

        def capture_interrupt(payload):
            nonlocal captured_payload
            captured_payload = payload
            return {"action": "approve", "feedback": ""}

        with patch("orchestrator.langgraph.nodes.approval_gate.load_project_config") as mock_load:
            mock_load.return_value = mock_config

            with patch("orchestrator.langgraph.nodes.approval_gate.interrupt", capture_interrupt):
                await approval_gate_node(state)

        assert captured_payload is not None
        assert captured_payload["type"] == "approval_required"
        assert captured_payload["phase"] == 2
        assert captured_payload["project"] == "test-project"
        assert "context" in captured_payload
        assert "approve" in captured_payload["options"]
        assert "reject" in captured_payload["options"]
        assert "request_changes" in captured_payload["options"]


class TestApprovalResponseHandling:
    """Tests for handling different approval responses."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create project directory."""
        workflow_dir = tmp_path / ".workflow"
        workflow_dir.mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def mock_config(self):
        """Config with approval gates enabled."""
        config = MagicMock()
        config.workflow.features.approval_gates = True
        config.workflow.approval_phases = [2]
        return config

    @pytest.mark.asyncio
    async def test_approve_response(self, project_dir, mock_config):
        """Test handling of approve response."""
        state = create_initial_state(
            project_dir=str(project_dir),
            project_name="test-project",
        )
        state["current_phase"] = 2

        with patch("orchestrator.langgraph.nodes.approval_gate.load_project_config") as mock_load:
            mock_load.return_value = mock_config

            with patch("orchestrator.langgraph.nodes.approval_gate.interrupt") as mock_interrupt:
                mock_interrupt.return_value = {"action": "approve", "feedback": "Looks good!"}

                result = await approval_gate_node(state)

        assert result["next_decision"] == "continue"
        assert "updated_at" in result
        assert "errors" not in result or not result.get("errors")

    @pytest.mark.asyncio
    async def test_reject_response(self, project_dir, mock_config):
        """Test handling of reject response."""
        state = create_initial_state(
            project_dir=str(project_dir),
            project_name="test-project",
        )
        state["current_phase"] = 2

        with patch("orchestrator.langgraph.nodes.approval_gate.load_project_config") as mock_load:
            mock_load.return_value = mock_config

            with patch("orchestrator.langgraph.nodes.approval_gate.interrupt") as mock_interrupt:
                mock_interrupt.return_value = {"action": "reject", "feedback": "Not ready"}

                result = await approval_gate_node(state)

        assert result["next_decision"] == "abort"
        assert "errors" in result
        assert result["errors"][0]["type"] == "approval_rejected"
        assert "Not ready" in result["errors"][0].get("feedback", "")

    @pytest.mark.asyncio
    async def test_request_changes_response(self, project_dir, mock_config):
        """Test handling of request_changes response."""
        state = create_initial_state(
            project_dir=str(project_dir),
            project_name="test-project",
        )
        state["current_phase"] = 2

        with patch("orchestrator.langgraph.nodes.approval_gate.load_project_config") as mock_load:
            mock_load.return_value = mock_config

            with patch("orchestrator.langgraph.nodes.approval_gate.interrupt") as mock_interrupt:
                mock_interrupt.return_value = {
                    "action": "request_changes",
                    "feedback": "Please fix X",
                }

                result = await approval_gate_node(state)

        assert result["next_decision"] == "retry"
        assert "errors" in result
        assert result["errors"][0]["type"] == "changes_requested"
        assert "Please fix X" in result["errors"][0].get("feedback", "")

    @pytest.mark.asyncio
    async def test_unknown_action_treated_as_rejection(self, project_dir, mock_config):
        """Test that unknown actions are treated as rejection."""
        state = create_initial_state(
            project_dir=str(project_dir),
            project_name="test-project",
        )
        state["current_phase"] = 2

        with patch("orchestrator.langgraph.nodes.approval_gate.load_project_config") as mock_load:
            mock_load.return_value = mock_config

            with patch("orchestrator.langgraph.nodes.approval_gate.interrupt") as mock_interrupt:
                mock_interrupt.return_value = {"action": "invalid_action", "feedback": ""}

                result = await approval_gate_node(state)

        assert result["next_decision"] == "abort"
        assert "errors" in result
        assert "unknown" in result["errors"][0]["type"].lower()


@pytest.mark.skip(reason="File persistence removed in DB migration - approvals saved to DB now")
class TestApprovalFilePersistence:
    """Tests for file persistence of context and response.

    NOTE: Skipped because approval context/response are now saved to
    the logs table in SurrealDB, not to local files.
    """

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create project directory."""
        workflow_dir = tmp_path / ".workflow"
        workflow_dir.mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def mock_config(self):
        """Config with approval gates enabled."""
        config = MagicMock()
        config.workflow.features.approval_gates = True
        config.workflow.approval_phases = [2]
        return config

    @pytest.mark.asyncio
    async def test_context_file_written(self, project_dir, mock_config):
        """Test that context file is written before interrupt."""
        state = create_initial_state(
            project_dir=str(project_dir),
            project_name="test-project",
        )
        state["current_phase"] = 2

        with patch("orchestrator.langgraph.nodes.approval_gate.load_project_config") as mock_load:
            mock_load.return_value = mock_config

            with patch("orchestrator.langgraph.nodes.approval_gate.interrupt") as mock_interrupt:
                mock_interrupt.return_value = {"action": "approve", "feedback": ""}

                await approval_gate_node(state)

        context_file = project_dir / ".workflow" / "phases" / "approvals" / "phase_2_context.json"
        assert context_file.exists()

        content = json.loads(context_file.read_text())
        assert content["phase"] == 2
        assert content["project_name"] == "test-project"

    @pytest.mark.asyncio
    async def test_response_file_written(self, project_dir, mock_config):
        """Test that response file is written after interrupt."""
        state = create_initial_state(
            project_dir=str(project_dir),
            project_name="test-project",
        )
        state["current_phase"] = 2

        with patch("orchestrator.langgraph.nodes.approval_gate.load_project_config") as mock_load:
            mock_load.return_value = mock_config

            with patch("orchestrator.langgraph.nodes.approval_gate.interrupt") as mock_interrupt:
                mock_interrupt.return_value = {"action": "approve", "feedback": "LGTM"}

                await approval_gate_node(state)

        response_file = project_dir / ".workflow" / "phases" / "approvals" / "phase_2_response.json"
        assert response_file.exists()

        content = json.loads(response_file.read_text())
        assert content["action"] == "approve"
        assert content["feedback"] == "LGTM"
        assert "timestamp" in content
