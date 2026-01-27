"""Tests for verification nodes.

Tests cursor_review_node, gemini_review_node, review_gate_node,
and verification_fan_in_node.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.langgraph.nodes.verification import (
    _build_verification_correction_prompt,
    _get_changed_files,
    _is_docs_only_changes,
    cursor_review_node,
    gemini_review_node,
    review_gate_node,
    verification_fan_in_node,
)
from orchestrator.langgraph.state import PhaseState


class TestCursorReviewNode:
    """Tests for cursor_review_node."""

    @pytest.mark.asyncio
    async def test_successful_review(self, workflow_state_phase_4, mock_specialist_runner):
        """Test successful cursor code review."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=True,
                output='{"score": 8.0, "approved": true, "findings": []}',
                parsed_output={"score": 8.0, "approved": True, "findings": []},
                error=None,
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        with patch(
            "orchestrator.langgraph.nodes.verification.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await cursor_review_node(workflow_state_phase_4)

        assert "verification_feedback" in result
        feedback = result["verification_feedback"]["cursor"]
        assert feedback.agent == "cursor"
        assert feedback.approved is True
        assert feedback.score == 8.0

    @pytest.mark.asyncio
    async def test_review_with_security_findings(
        self, workflow_state_phase_4, mock_specialist_runner
    ):
        """Test cursor review with security findings."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=True,
                output=json.dumps(
                    {
                        "score": 4.0,
                        "approved": False,
                        "findings": [
                            {
                                "file": "src/db.py",
                                "line": 42,
                                "severity": "CRITICAL",
                                "description": "SQL injection vulnerability",
                            },
                            {
                                "file": "src/auth.py",
                                "line": 15,
                                "severity": "HIGH",
                                "description": "Weak password hashing",
                            },
                        ],
                    }
                ),
                error=None,
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        with patch(
            "orchestrator.langgraph.nodes.verification.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await cursor_review_node(workflow_state_phase_4)

        feedback = result["verification_feedback"]["cursor"]
        assert feedback.approved is False
        assert len(feedback.blocking_issues) >= 2

    @pytest.mark.asyncio
    async def test_review_skipped_for_docs_only(self, workflow_state_phase_4):
        """Test review skipped when review_skipped flag is set."""
        workflow_state_phase_4["review_skipped"] = True

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await cursor_review_node(workflow_state_phase_4)

        feedback = result["verification_feedback"]["cursor"]
        assert feedback.approved is True
        assert feedback.score == 10.0
        assert feedback.assessment == "skipped"

    @pytest.mark.asyncio
    async def test_review_failure_returns_error(
        self, workflow_state_phase_4, mock_specialist_runner
    ):
        """Test cursor review failure creates error context."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=False,
                error="Agent timeout",
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        with patch(
            "orchestrator.langgraph.nodes.verification.SpecialistRunner",
            return_value=mock_specialist_runner,
        ):
            result = await cursor_review_node(workflow_state_phase_4)

        assert "errors" in result
        assert result["errors"][0]["type"] == "verification_error"
        assert "error_context" in result

    @pytest.mark.asyncio
    async def test_tracks_agent_execution(self, workflow_state_phase_4, mock_specialist_runner):
        """Test cursor review tracks agent execution."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=True,
                output='{"score": 8.0, "approved": true}',
                parsed_output={"score": 8.0, "approved": True},
                error=None,
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        with patch(
            "orchestrator.langgraph.nodes.verification.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await cursor_review_node(workflow_state_phase_4)

        assert "last_agent_execution" in result
        execution = result["last_agent_execution"]
        assert execution["agent"] == "cursor"
        assert execution["template_name"] == "code_review"


class TestGeminiReviewNode:
    """Tests for gemini_review_node."""

    @pytest.mark.asyncio
    async def test_successful_review(self, workflow_state_phase_4, mock_specialist_runner):
        """Test successful gemini architecture review."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=True,
                output='{"score": 8.5, "approved": true, "comments": []}',
                error=None,
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        with patch(
            "orchestrator.langgraph.nodes.verification.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await gemini_review_node(workflow_state_phase_4)

        assert "verification_feedback" in result
        feedback = result["verification_feedback"]["gemini"]
        assert feedback.agent == "gemini"
        assert feedback.approved is True

    @pytest.mark.asyncio
    async def test_review_with_architecture_issues(
        self, workflow_state_phase_4, mock_specialist_runner
    ):
        """Test gemini review with architecture issues."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=True,
                output=json.dumps(
                    {
                        "score": 5.0,
                        "approved": False,
                        "comments": [
                            {
                                "description": "Circular dependency between modules",
                                "remediation": "Introduce interface abstraction",
                            }
                        ],
                        "blocking_issues": ["Violates single responsibility principle"],
                    }
                ),
                error=None,
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        with patch(
            "orchestrator.langgraph.nodes.verification.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await gemini_review_node(workflow_state_phase_4)

        feedback = result["verification_feedback"]["gemini"]
        assert feedback.approved is False
        assert len(feedback.blocking_issues) > 0

    @pytest.mark.asyncio
    async def test_review_skipped_for_docs_only(self, workflow_state_phase_4):
        """Test review skipped when review_skipped flag is set."""
        workflow_state_phase_4["review_skipped"] = True

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await gemini_review_node(workflow_state_phase_4)

        feedback = result["verification_feedback"]["gemini"]
        assert feedback.approved is True
        assert feedback.assessment == "skipped"

    @pytest.mark.asyncio
    async def test_tracks_agent_execution(self, workflow_state_phase_4, mock_specialist_runner):
        """Test gemini review tracks agent execution."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=True,
                output='{"score": 8.0, "approved": true}',
                error=None,
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        with patch(
            "orchestrator.langgraph.nodes.verification.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await gemini_review_node(workflow_state_phase_4)

        assert "last_agent_execution" in result
        assert result["last_agent_execution"]["template_name"] == "architecture_review"


class TestReviewGateNode:
    """Tests for review_gate_node."""

    @pytest.mark.asyncio
    async def test_docs_only_changes_skip_review(self, workflow_state_phase_4):
        """Test docs-only changes skip review."""
        workflow_state_phase_4["implementation_result"] = {
            "files_created": ["docs/README.md", "docs/API.md"],
            "files_modified": [],
        }

        with patch("orchestrator.langgraph.nodes.verification.load_project_config") as mock_config:
            mock_config.return_value = MagicMock(workflow=MagicMock(review_gating="conservative"))
            with patch(
                "orchestrator.langgraph.nodes.verification._get_changed_files",
                new_callable=AsyncMock,
                return_value=["docs/README.md"],
            ):
                result = await review_gate_node(workflow_state_phase_4)

        assert result["review_skipped"] is True
        assert result["review_skipped_reason"] == "docs_only"

    @pytest.mark.asyncio
    async def test_code_changes_require_review(self, workflow_state_phase_4):
        """Test code changes require review."""
        workflow_state_phase_4["implementation_result"] = {
            "files_created": ["src/feature.py"],
            "files_modified": ["src/app.py"],
        }

        with patch("orchestrator.langgraph.nodes.verification.load_project_config") as mock_config:
            mock_config.return_value = MagicMock(workflow=MagicMock(review_gating="conservative"))
            with patch(
                "orchestrator.langgraph.nodes.verification._get_changed_files",
                new_callable=AsyncMock,
                return_value=["src/feature.py", "src/app.py"],
            ):
                result = await review_gate_node(workflow_state_phase_4)

        assert result["review_skipped"] is False

    @pytest.mark.asyncio
    async def test_mixed_changes_require_review(self, workflow_state_phase_4):
        """Test mixed docs and code changes require review."""
        workflow_state_phase_4["implementation_result"] = {
            "files_created": ["src/feature.py", "docs/feature.md"],
            "files_modified": [],
        }

        with patch("orchestrator.langgraph.nodes.verification.load_project_config") as mock_config:
            mock_config.return_value = MagicMock(workflow=MagicMock(review_gating="conservative"))
            with patch(
                "orchestrator.langgraph.nodes.verification._get_changed_files",
                new_callable=AsyncMock,
                return_value=["src/feature.py", "docs/feature.md"],
            ):
                result = await review_gate_node(workflow_state_phase_4)

        assert result["review_skipped"] is False


class TestVerificationFanIn:
    """Tests for verification_fan_in_node."""

    @pytest.mark.asyncio
    async def test_both_approved(
        self, workflow_state_phase_4, cursor_feedback_approved, gemini_feedback_approved
    ):
        """Test fan-in when both agents approve."""
        workflow_state_phase_4["verification_feedback"] = {
            "cursor": cursor_feedback_approved,
            "gemini": gemini_feedback_approved,
        }

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await verification_fan_in_node(workflow_state_phase_4)

        assert result["next_decision"] == "continue"
        assert result["current_phase"] == 5

    @pytest.mark.asyncio
    async def test_cursor_rejects_creates_correction_prompt(
        self, workflow_state_phase_4, cursor_feedback_rejected, gemini_feedback_approved
    ):
        """Test cursor rejection creates correction prompt."""
        workflow_state_phase_4["verification_feedback"] = {
            "cursor": cursor_feedback_rejected,
            "gemini": gemini_feedback_approved,
        }
        workflow_state_phase_4["phase_status"] = {"4": PhaseState(attempts=0)}

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await verification_fan_in_node(workflow_state_phase_4)

        if result["next_decision"] == "retry":
            assert "correction_prompt" in result

    @pytest.mark.asyncio
    async def test_max_attempts_escalates(
        self, workflow_state_phase_4, cursor_feedback_rejected, gemini_feedback_rejected
    ):
        """Test max attempts triggers escalation."""
        workflow_state_phase_4["verification_feedback"] = {
            "cursor": cursor_feedback_rejected,
            "gemini": gemini_feedback_rejected,
        }
        # Set max attempts reached
        workflow_state_phase_4["phase_status"] = {"4": PhaseState(attempts=3, max_attempts=3)}

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await verification_fan_in_node(workflow_state_phase_4)

        assert result["next_decision"] == "escalate"

    @pytest.mark.asyncio
    async def test_missing_feedback_returns_error(
        self, workflow_state_phase_4, cursor_feedback_approved
    ):
        """Test missing feedback returns error when single-agent fallback is disabled."""
        workflow_state_phase_4["verification_feedback"] = {
            "cursor": cursor_feedback_approved,
            # gemini missing
        }

        # Mock review config to disable single-agent fallback
        mock_config = type(
            "MockReviewConfig",
            (),
            {
                "allow_single_agent_approval": False,
                "single_agent_score_penalty": 1.0,
                "single_agent_minimum_score": 7.0,
            },
        )()

        with patch(
            "orchestrator.langgraph.nodes.verification.get_review_config", return_value=mock_config
        ):
            result = await verification_fan_in_node(workflow_state_phase_4)

        assert "errors" in result
        assert result["next_decision"] == "retry"

    @pytest.mark.asyncio
    async def test_uses_dynamic_weights(
        self, workflow_state_phase_4, cursor_feedback_approved, gemini_feedback_rejected
    ):
        """Test verification uses dynamic role weights."""
        # Set up architecture-focused task
        workflow_state_phase_4["current_task"] = {
            "id": "T1",
            "title": "Refactor database layer",
            "type": "ARCHITECTURE",
        }
        workflow_state_phase_4["verification_feedback"] = {
            "cursor": cursor_feedback_approved,
            "gemini": gemini_feedback_rejected,
        }
        workflow_state_phase_4["phase_status"] = {"4": PhaseState()}

        with patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"), patch(
            "orchestrator.storage.async_utils.run_async"
        ):
            result = await verification_fan_in_node(workflow_state_phase_4)

        # For architecture tasks, gemini rejection should matter more
        assert result["next_decision"] in ["retry", "escalate"]


class TestBuildVerificationCorrectionPrompt:
    """Tests for _build_verification_correction_prompt helper."""

    def test_includes_blocking_issues(self, cursor_feedback_rejected, gemini_feedback_approved):
        """Test prompt includes blocking issues."""
        blocking = ["SQL injection in user input", "Missing CSRF protection"]

        prompt = _build_verification_correction_prompt(
            cursor_feedback_rejected, gemini_feedback_approved, blocking
        )

        assert "SQL injection" in prompt
        assert "CSRF protection" in prompt
        assert "MUST FIX" in prompt

    def test_includes_security_findings(self, cursor_feedback_rejected, gemini_feedback_approved):
        """Test prompt includes security findings from cursor."""
        prompt = _build_verification_correction_prompt(
            cursor_feedback_rejected, gemini_feedback_approved, []
        )

        # Should reference security/code findings section
        assert "Security" in prompt or "Findings" in prompt

    def test_includes_architecture_comments(
        self, cursor_feedback_approved, gemini_feedback_rejected
    ):
        """Test prompt includes architecture comments from gemini."""
        prompt = _build_verification_correction_prompt(
            cursor_feedback_approved, gemini_feedback_rejected, []
        )

        assert "Architecture" in prompt

    def test_includes_fix_instructions(self, cursor_feedback_approved, gemini_feedback_approved):
        """Test prompt includes fix instructions."""
        prompt = _build_verification_correction_prompt(
            cursor_feedback_approved, gemini_feedback_approved, []
        )

        assert "Instructions" in prompt
        assert "Fix" in prompt or "fix" in prompt


class TestIsDocsOnlyChanges:
    """Tests for _is_docs_only_changes helper."""

    def test_markdown_only_returns_true(self):
        """Test markdown-only changes return True."""
        files = ["README.md", "docs/guide.md", "CHANGELOG.md"]
        assert _is_docs_only_changes(files) is True

    def test_text_files_return_true(self):
        """Test text documentation files return True."""
        files = ["docs/notes.txt", "README.rst", "guide.adoc"]
        assert _is_docs_only_changes(files) is True

    def test_code_files_return_false(self):
        """Test code files return False."""
        files = ["src/main.py", "tests/test_main.py"]
        assert _is_docs_only_changes(files) is False

    def test_mixed_files_return_false(self):
        """Test mixed docs and code return False."""
        files = ["README.md", "src/feature.py"]
        assert _is_docs_only_changes(files) is False

    def test_empty_list_returns_false(self):
        """Test empty file list returns False."""
        assert _is_docs_only_changes([]) is False


class TestGetChangedFiles:
    """Tests for _get_changed_files helper."""

    @pytest.mark.asyncio
    async def test_returns_git_diff_files(self, temp_project_dir):
        """Test returns files from git diff."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="src/file1.py\nsrc/file2.py\n",
            )

            files = await _get_changed_files(temp_project_dir)

        assert "src/file1.py" in files
        assert "src/file2.py" in files

    @pytest.mark.asyncio
    async def test_handles_no_changes(self, temp_project_dir):
        """Test handles no changes gracefully."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
            )

            files = await _get_changed_files(temp_project_dir)

        assert files == []

    @pytest.mark.asyncio
    async def test_handles_git_error(self, temp_project_dir):
        """Test handles git error gracefully."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Git not found")

            files = await _get_changed_files(temp_project_dir)

        # Should return empty list, not raise
        assert files == []
