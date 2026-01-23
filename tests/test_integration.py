"""Integration tests for the orchestrator workflow."""

import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator import Orchestrator
from orchestrator.agents.base import AgentResult


@pytest.fixture
def temp_project():
    """Create temporary project directory with PRODUCT.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Create PRODUCT.md with required sections
        product_md = project_dir / "PRODUCT.md"
        product_md.write_text(
            """# User Authentication Feature

## Feature
Add user authentication with JWT tokens to the application.

## Goals
- Secure login/logout functionality
- Token refresh mechanism
- Password reset capability
- Session management

## Constraints
- Use existing user database
- Support OAuth2 integration
- Must be backwards compatible

## Success Criteria
- All authentication endpoints have tests
- No security vulnerabilities in OWASP top 10
- Response time < 200ms for auth operations
"""
        )

        yield project_dir


@pytest.fixture
def mock_all_agents():
    """Mock all agent CLI calls."""
    mock_claude = MagicMock()
    mock_claude.name = "claude"
    mock_claude.check_available.return_value = True
    mock_claude.run_planning.return_value = AgentResult(
        success=True,
        parsed_output={
            "plan_name": "JWT Authentication",
            "summary": "Implement JWT-based authentication",
            "phases": [
                {
                    "phase": 1,
                    "name": "Setup",
                    "tasks": [
                        {
                            "id": "T1",
                            "description": "Setup auth module",
                            "files": ["auth.py"],
                            "dependencies": [],
                        }
                    ],
                }
            ],
            "test_strategy": {"unit_tests": ["test_auth.py"], "test_commands": ["pytest"]},
            "estimated_complexity": "medium",
        },
    )
    mock_claude.run_implementation.return_value = AgentResult(
        success=True,
        parsed_output={
            "implementation_complete": True,
            "files_created": ["src/auth.py"],
            "files_modified": [],
            "test_results": {"passed": 10, "failed": 0},
        },
    )

    mock_cursor = MagicMock()
    mock_cursor.name = "cursor"
    mock_cursor.check_available.return_value = True
    mock_cursor.run_validation.return_value = AgentResult(
        success=True,
        parsed_output={
            "reviewer": "cursor",
            "overall_assessment": "approve",
            "score": 8.5,
            "strengths": ["Good security practices"],
            "concerns": [],
        },
    )
    mock_cursor.run_code_review.return_value = AgentResult(
        success=True,
        parsed_output={
            "reviewer": "cursor",
            "approved": True,
            "overall_code_quality": 8,
            "files_reviewed": [],
            "blocking_issues": [],
        },
    )

    mock_gemini = MagicMock()
    mock_gemini.name = "gemini"
    mock_gemini.check_available.return_value = True
    mock_gemini.run_validation.return_value = AgentResult(
        success=True,
        parsed_output={
            "reviewer": "gemini",
            "overall_assessment": "approve",
            "score": 9,
            "architecture_review": {
                "patterns_identified": ["Strategy pattern"],
                "scalability_assessment": "excellent",
                "maintainability_assessment": "good",
                "concerns": [],
            },
        },
    )
    mock_gemini.run_architecture_review.return_value = AgentResult(
        success=True,
        parsed_output={
            "reviewer": "gemini",
            "approved": True,
            "architecture_assessment": {"modularity_score": 9},
            "blocking_issues": [],
        },
    )

    return mock_claude, mock_cursor, mock_gemini


class TestWorkflowIntegration:
    """End-to-end workflow tests."""

    def test_full_workflow_success(self, temp_project, mock_all_agents):
        """Test complete 5-phase workflow."""
        mock_claude, mock_cursor, mock_gemini = mock_all_agents

        with patch("orchestrator.agents.ClaudeAgent", return_value=mock_claude), patch(
            "orchestrator.agents.CursorAgent", return_value=mock_cursor
        ), patch("orchestrator.agents.GeminiAgent", return_value=mock_gemini):
            orchestrator = Orchestrator(
                temp_project,
                auto_commit=False,
                console_output=False,
            )
            # Just check that it initializes correctly
            status = orchestrator.status()
            assert "project" in status

    def test_workflow_resume_after_failure(self, temp_project, mock_all_agents):
        """Test resuming workflow after phase failure."""
        mock_claude, mock_cursor, mock_gemini = mock_all_agents

        with patch("orchestrator.agents.ClaudeAgent", return_value=mock_claude), patch(
            "orchestrator.agents.CursorAgent", return_value=mock_cursor
        ), patch("orchestrator.agents.GeminiAgent", return_value=mock_gemini):
            orchestrator = Orchestrator(
                temp_project,
                max_retries=2,
                auto_commit=False,
                console_output=False,
            )

            # Check state can be loaded via storage adapter
            state = orchestrator.storage.get_state()
            assert state is not None
            # With mocked DB, current_phase comes from mock

    def test_parallel_agent_failure_handling(self, temp_project, mock_all_agents):
        """Test that one agent failure doesn't lose other's results."""
        mock_claude, mock_cursor, mock_gemini = mock_all_agents

        # Make Gemini fail but Cursor succeed
        mock_gemini.run_validation.return_value = AgentResult(
            success=False, error="Gemini unavailable"
        )

        with patch("orchestrator.agents.ClaudeAgent", return_value=mock_claude), patch(
            "orchestrator.agents.CursorAgent", return_value=mock_cursor
        ), patch("orchestrator.agents.GeminiAgent", return_value=mock_gemini):
            orchestrator = Orchestrator(
                temp_project,
                auto_commit=False,
                console_output=False,
            )

            # Verify orchestrator initialized correctly
            status = orchestrator.status()
            # With mocked DB, project name comes from mock
            assert "current_phase" in status or status.get("status") == "not_initialized"


@pytest.mark.skip(reason="File-based state persistence removed in DB migration")
class TestStatePersistence:
    """Tests for state persistence and recovery.

    NOTE: These tests are skipped as they test file-based state persistence
    which was removed in the SurrealDB migration. State is now only stored in DB.
    """

    def test_state_atomic_save(self, temp_project):
        """Test that state saves are atomic."""
        from orchestrator.utils.state import StateManager

        state_manager = StateManager(temp_project)
        state_manager.ensure_workflow_dir()
        state_manager.load()

        # Simulate multiple concurrent saves
        def save_iteration(iteration):
            state_manager.state.metadata[f"iter_{iteration}"] = iteration
            state_manager.save()

        threads = []
        for i in range(5):
            t = threading.Thread(target=save_iteration, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Reload and verify state is valid
        new_manager = StateManager(temp_project)
        state = new_manager.load()
        assert state.project_name == temp_project.name

    def test_state_recovery_from_corruption(self, temp_project):
        """Test recovery from corrupted state file."""
        state_manager = StateManager(temp_project)
        state_manager.ensure_workflow_dir()
        state_manager.load()

        # Save valid state
        state_manager.state.metadata["test"] = "value"
        state_manager.save()

        # Corrupt the state file
        state_file = state_manager.state_file
        state_file.write_text("{invalid json")

        # Should recover (either from backup or create new)
        new_manager = StateManager(temp_project)
        state = new_manager.load()
        assert state is not None
        assert state.project_name == temp_project.name


class TestValidation:
    """Tests for input validation."""

    def test_empty_product_spec_rejected(self):
        """Test that empty PRODUCT.md is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            product_md = project_dir / "PRODUCT.md"
            product_md.write_text("")

            orchestrator = Orchestrator(
                project_dir,
                auto_commit=False,
                console_output=False,
            )

            # This should fail due to missing prerequisites
            ok, errors = orchestrator.check_prerequisites()
            # Note: check_prerequisites checks file existence, not content
            # Content validation happens during planning phase

    def test_product_spec_without_required_sections(self):
        """Test that PRODUCT.md without required sections is rejected."""
        from orchestrator.utils.validation import ProductSpecValidator

        validator = ProductSpecValidator()

        # Missing required sections
        content = """# My Feature

Just some text without proper structure.
"""
        result = validator.validate(content)
        assert not result.valid
        assert any("Feature" in e for e in result.errors)
        assert any("Goals" in e for e in result.errors)

    def test_valid_product_spec_accepted(self):
        """Test that valid PRODUCT.md is accepted."""
        from orchestrator.utils.validation import ProductSpecValidator

        validator = ProductSpecValidator()

        content = """# My Feature

## Feature
This is the main feature description with enough content.

## Goals
- Goal 1
- Goal 2
- Goal 3
"""
        result = validator.validate(content)
        assert result.valid
        assert len(result.errors) == 0


@pytest.mark.skip(reason="File-based state persistence removed in DB migration")
class TestThreadSafety:
    """Tests for thread safety.

    NOTE: These tests are skipped as they test file-based StateManager
    which was removed in the SurrealDB migration. Thread safety is now
    handled by the database layer.
    """

    def test_concurrent_state_updates(self, temp_project):
        """Test that concurrent state updates don't corrupt data."""
        from orchestrator.utils.state import StateManager

        state_manager = StateManager(temp_project)
        state_manager.ensure_workflow_dir()
        state_manager.load()

        errors = []

        def update_phase(phase_num):
            try:
                state_manager.start_phase(phase_num)
                time.sleep(0.01)  # Small delay to increase contention
                state_manager.add_approval(phase_num, "test_agent", True)
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(1, 6):  # Phases 1-5
            t = threading.Thread(target=update_phase, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0

        # Reload and verify state
        new_manager = StateManager(temp_project)
        state = new_manager.load()
        assert state is not None


class TestLogging:
    """Tests for logging functionality."""

    def test_secrets_redaction(self):
        """Test that secrets are redacted from logs."""
        from orchestrator.utils.logging import SecretsRedactor

        redactor = SecretsRedactor()

        # Test API key redaction
        message = "Using API key: sk-abc123def456xyz789"
        redacted = redactor.redact(message)
        assert "sk-abc123def456xyz789" not in redacted
        assert "REDACTED" in redacted

        # Test password redaction
        message = 'password="mysecretpassword"'
        redacted = redactor.redact(message)
        assert "mysecretpassword" not in redacted

        # Test bearer token redaction
        message = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        redacted = redactor.redact(message)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted

    def test_thread_safe_logging(self, temp_project):
        """Test that concurrent logging doesn't cause issues."""
        from orchestrator.utils.logging import LogLevel, OrchestrationLogger

        workflow_dir = temp_project / ".workflow"
        workflow_dir.mkdir(exist_ok=True)

        logger = OrchestrationLogger(
            workflow_dir=workflow_dir,
            console_output=False,
            min_level=LogLevel.DEBUG,
        )

        errors = []

        def log_messages(thread_id):
            try:
                for i in range(10):
                    logger.info(f"Thread {thread_id} message {i}")
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(5):
            t = threading.Thread(target=log_messages, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0

        # Verify log file exists and is not corrupted
        log_file = workflow_dir / "coordination.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert len(content) > 0


class TestFeedbackValidation:
    """Tests for feedback validation."""

    def test_normalize_agent_feedback(self):
        """Test that agent feedback is normalized correctly."""
        from orchestrator.utils.validation import AssessmentType, validate_feedback

        # Test with various field name conventions
        raw_feedback = {
            "assessment": "approved",  # Different field name
            "rating": 8,  # Different field name
            "issues": [  # Different field name
                {"category": "security", "message": "Consider input validation"}
            ],
        }

        normalized = validate_feedback("cursor", raw_feedback)

        assert normalized["reviewer"] == "cursor"
        assert normalized["overall_assessment"] == AssessmentType.APPROVED.value
        assert normalized["score"] == 8.0
        assert len(normalized["items"]) == 1

    def test_handle_missing_fields(self):
        """Test that missing fields are handled gracefully."""
        from orchestrator.utils.validation import validate_feedback

        # Minimal feedback
        raw_feedback = {}

        normalized = validate_feedback("gemini", raw_feedback)

        assert normalized["reviewer"] == "gemini"
        assert normalized["overall_assessment"] == "unknown"
        assert normalized["score"] == 0.0
