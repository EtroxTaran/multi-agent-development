"""Tests for the main orchestrator."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from orchestrator.orchestrator import Orchestrator
from orchestrator.utils.state import PhaseStatus


class TestOrchestrator:
    """Tests for the Orchestrator class."""

    def test_initialization(self, temp_project_dir):
        """Test orchestrator initialization."""
        orch = Orchestrator(
            project_dir=temp_project_dir,
            max_retries=5,
            auto_commit=False,
        )

        assert orch.project_dir == temp_project_dir
        assert orch.max_retries == 5
        assert orch.auto_commit is False
        assert orch.state is not None
        assert orch.logger is not None

    def test_check_prerequisites_missing_product(self, temp_project_dir):
        """Test prerequisites check fails without PRODUCT.md."""
        (temp_project_dir / "PRODUCT.md").unlink()

        orch = Orchestrator(temp_project_dir)
        ok, errors = orch.check_prerequisites()

        assert ok is False
        assert any("PRODUCT.md" in e for e in errors)

    @patch("orchestrator.agents.claude_agent.ClaudeAgent.check_available")
    @patch("orchestrator.agents.cursor_agent.CursorAgent.check_available")
    @patch("orchestrator.agents.gemini_agent.GeminiAgent.check_available")
    def test_check_prerequisites_all_available(
        self, mock_gemini, mock_cursor, mock_claude, temp_project_dir
    ):
        """Test prerequisites check passes with all CLIs."""
        mock_claude.return_value = True
        mock_cursor.return_value = True
        mock_gemini.return_value = True

        orch = Orchestrator(temp_project_dir)
        ok, errors = orch.check_prerequisites()

        assert ok is True
        assert len(errors) == 0

    def test_status(self, temp_project_dir):
        """Test getting workflow status."""
        orch = Orchestrator(temp_project_dir)
        status = orch.status()

        assert "project" in status
        assert "current_phase" in status
        assert "phase_statuses" in status

    def test_reset_all(self, temp_project_dir):
        """Test resetting all phases."""
        orch = Orchestrator(temp_project_dir)

        # Simulate some progress
        orch.state.start_phase(1)
        orch.state.complete_phase(1)
        orch.state.start_phase(2)

        # Reset
        orch.reset()

        # Verify reset
        for phase_name, phase in orch.state.state.phases.items():
            assert phase.status == PhaseStatus.PENDING
            assert phase.attempts == 0

    def test_reset_single_phase(self, temp_project_dir):
        """Test resetting a single phase."""
        orch = Orchestrator(temp_project_dir)

        # Simulate progress
        orch.state.start_phase(1)
        orch.state.fail_phase(1, "test error")

        # Reset phase 1
        orch.reset(phase=1)

        # Verify
        phase = orch.state.get_phase(1)
        assert phase.status == PhaseStatus.PENDING
        assert phase.error is None

    @patch.object(Orchestrator, "check_prerequisites")
    @patch.object(Orchestrator, "_run_phase_with_retry")
    def test_run_executes_phases(
        self, mock_run_phase, mock_prereq, temp_project_dir
    ):
        """Test that run executes phases in order."""
        mock_prereq.return_value = (True, [])
        mock_run_phase.return_value = {"success": True}

        orch = Orchestrator(temp_project_dir, auto_commit=False)
        result = orch.run()

        assert result["success"] is True
        # Should have called for all 5 phases
        assert mock_run_phase.call_count == 5

    @patch.object(Orchestrator, "check_prerequisites")
    @patch.object(Orchestrator, "_run_phase_with_retry")
    def test_run_stops_on_failure(
        self, mock_run_phase, mock_prereq, temp_project_dir
    ):
        """Test that run stops when a phase fails."""
        mock_prereq.return_value = (True, [])
        # First phase succeeds, second fails
        mock_run_phase.side_effect = [
            {"success": True},
            {"success": False, "error": "Phase 2 failed"},
        ]

        orch = Orchestrator(temp_project_dir, auto_commit=False)
        result = orch.run()

        assert result["success"] is False
        assert result["stopped_at_phase"] == 2

    @patch.object(Orchestrator, "check_prerequisites")
    @patch.object(Orchestrator, "_run_phase_with_retry")
    def test_run_with_start_phase(
        self, mock_run_phase, mock_prereq, temp_project_dir
    ):
        """Test starting from a specific phase."""
        mock_prereq.return_value = (True, [])
        mock_run_phase.return_value = {"success": True}

        orch = Orchestrator(temp_project_dir, auto_commit=False)
        result = orch.run(start_phase=3)

        # Should only run phases 3, 4, 5
        assert mock_run_phase.call_count == 3

    @patch.object(Orchestrator, "check_prerequisites")
    @patch.object(Orchestrator, "_run_phase_with_retry")
    def test_run_skip_validation(
        self, mock_run_phase, mock_prereq, temp_project_dir
    ):
        """Test skipping validation phase."""
        mock_prereq.return_value = (True, [])
        mock_run_phase.return_value = {"success": True}

        orch = Orchestrator(temp_project_dir, auto_commit=False)
        result = orch.run(skip_validation=True)

        # Should run phases 1, 3, 4, 5 (skip 2)
        assert mock_run_phase.call_count == 4

    @patch("subprocess.run")
    def test_auto_commit(self, mock_run, temp_project_dir):
        """Test auto-commit functionality."""
        # Mock git commands - optimized to use batched operations:
        # 1. is_git_repo() -> git rev-parse --is-inside-work-tree
        # 2. auto_commit() -> batched bash script (status + add + commit + hash)
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git rev-parse (is_git_repo check)
            MagicMock(returncode=0, stdout="abc123def456\n"),  # batched auto_commit script
        ]

        orch = Orchestrator(temp_project_dir, auto_commit=True)
        orch._auto_commit(1, "planning")

        # Verify batched git operations were called (2 subprocess calls total)
        assert mock_run.call_count == 2

    def test_resume(self, temp_project_dir):
        """Test resume finds correct starting phase."""
        orch = Orchestrator(temp_project_dir, auto_commit=False)

        # Complete first two phases
        orch.state.load()
        orch.state.state.phases["planning"].status = PhaseStatus.COMPLETED
        orch.state.state.phases["validation"].status = PhaseStatus.COMPLETED
        orch.state.save()

        with patch.object(orch, "run") as mock_run:
            mock_run.return_value = {"success": True}
            orch.resume()

            # Should start from phase 3
            mock_run.assert_called_once_with(start_phase=3)
