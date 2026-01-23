"""Pytest fixtures for orchestrator tests."""

import sys
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# Mock websockets/surrealdb at import time for test collection
# These modules may not be installed in all test environments
for mod in [
    "websockets",
    "surrealdb",
    "surrealdb.connections",
    "surrealdb.connections.async_ws",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from orchestrator.models import WorkflowState, PhaseState, PhaseStatus
from orchestrator.storage.workflow_adapter import get_workflow_storage
from orchestrator.utils.logging import OrchestrationLogger, LogLevel


# -------------------------------------------------------------------
# DB Mock Fixtures for Unit Tests
# -------------------------------------------------------------------


@pytest.fixture
def mock_phase_output_repo():
    """Create a mock PhaseOutputRepository."""
    mock_repo = MagicMock()
    # Async methods
    mock_repo.save_output = AsyncMock(return_value=MagicMock(id="test-id", content={}))
    mock_repo.save_plan = AsyncMock(return_value=MagicMock(id="test-id", content={}))
    mock_repo.save_cursor_feedback = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_gemini_feedback = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_task_result = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_cursor_review = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_gemini_review = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_summary = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.get_output = AsyncMock(return_value=None)
    mock_repo.get_plan = AsyncMock(return_value=None)
    mock_repo.get_task_result = AsyncMock(return_value=None)
    mock_repo.get_phase_outputs = AsyncMock(return_value=[])
    mock_repo.get_task_outputs = AsyncMock(return_value=[])
    mock_repo.clear_phase = AsyncMock(return_value=0)
    return mock_repo


@pytest.fixture
def mock_logs_repo():
    """Create a mock LogsRepository."""
    mock_repo = MagicMock()
    # Async methods
    mock_repo.create_log = AsyncMock(return_value=MagicMock(id="test-id", content={}))
    mock_repo.save_uat_document = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_handoff_brief = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_discussion = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_research = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.log_error = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.log_debug = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.get_by_type = AsyncMock(return_value=[])
    mock_repo.get_by_task = AsyncMock(return_value=[])
    mock_repo.get_latest = AsyncMock(return_value=None)
    mock_repo.get_uat_document = AsyncMock(return_value=None)
    mock_repo.get_latest_handoff_brief = AsyncMock(return_value=None)
    mock_repo.clear_by_type = AsyncMock(return_value=0)
    mock_repo.clear_by_task = AsyncMock(return_value=0)
    return mock_repo


@pytest.fixture
def mock_workflow_repo():
    """Create a mock WorkflowRepository."""
    mock_repo = MagicMock()
    mock_state = MagicMock()
    mock_state.project_dir = "/tmp/test"
    mock_state.current_phase = 1
    mock_state.phase_status = {}
    mock_state.iteration_count = 0
    mock_state.plan = None
    mock_state.validation_feedback = {}
    mock_state.verification_feedback = {}
    mock_state.implementation_result = None
    mock_state.next_decision = None
    mock_state.execution_mode = "afk"
    mock_state.discussion_complete = False
    mock_state.research_complete = False
    mock_state.research_findings = {}
    mock_state.token_usage = {}
    mock_state.created_at = None
    mock_state.updated_at = None

    # Async methods
    mock_repo.get_state = AsyncMock(return_value=mock_state)
    mock_repo.initialize_state = AsyncMock(return_value=mock_state)
    mock_repo.update_state = AsyncMock(return_value=mock_state)
    mock_repo.set_phase = AsyncMock(return_value=mock_state)
    mock_repo.reset_state = AsyncMock(return_value=mock_state)
    mock_repo.get_summary = AsyncMock(return_value={"current_phase": 1, "project": "test"})
    mock_repo.increment_iteration = AsyncMock(return_value=mock_state)
    mock_repo.set_plan = AsyncMock(return_value=mock_state)
    mock_repo.set_validation_feedback = AsyncMock(return_value=mock_state)
    mock_repo.set_verification_feedback = AsyncMock(return_value=mock_state)
    mock_repo.set_implementation_result = AsyncMock(return_value=mock_state)
    mock_repo.record_git_commit = AsyncMock(return_value={})
    mock_repo.get_git_commits = AsyncMock(return_value=[])
    mock_repo.reset_to_phase = AsyncMock(return_value=mock_state)
    return mock_repo


@pytest.fixture
def mock_session_repo():
    """Create a mock SessionRepository."""
    mock_repo = MagicMock()
    mock_session = MagicMock()
    mock_session.task_id = "T1"
    mock_session.session_id = "test-session-id"
    mock_session.agent = "claude"
    mock_session.status = "active"
    mock_session.created_at = None
    mock_session.updated_at = None
    mock_session.invocation_count = 0
    mock_session.total_cost_usd = 0.0

    # Async methods
    mock_repo.create_session = AsyncMock(return_value=mock_session)
    mock_repo.get_active_session = AsyncMock(return_value=None)
    mock_repo.close_session = AsyncMock(return_value=True)
    mock_repo.touch_session = AsyncMock(return_value=mock_session)
    mock_repo.record_invocation = AsyncMock(return_value=mock_session)
    mock_repo.get_task_sessions = AsyncMock(return_value=[])
    return mock_repo


@pytest.fixture
def mock_budget_repo():
    """Create a mock BudgetRepository."""
    mock_repo = MagicMock()
    # Async methods
    mock_repo.record_spend = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.get_task_cost = AsyncMock(return_value=0.0)
    mock_repo.get_total_cost = AsyncMock(return_value=0.0)
    mock_repo.get_cost_by_agent = AsyncMock(return_value={})
    mock_repo.get_summary = AsyncMock(
        return_value=MagicMock(
            total_cost_usd=0.0,
            by_agent={},
            by_task={},
            record_count=0,
        )
    )
    return mock_repo


@pytest.fixture
def mock_audit_repo():
    """Create a mock AuditRepository."""
    mock_repo = MagicMock()
    mock_entry = MagicMock()
    mock_entry.id = "test-entry-id"

    # Async methods
    mock_repo.create_entry = AsyncMock(return_value=mock_entry)
    mock_repo.update_result = AsyncMock(return_value=mock_entry)
    mock_repo.find_by_task = AsyncMock(return_value=[])
    mock_repo.find_by_agent = AsyncMock(return_value=[])
    mock_repo.find_by_status = AsyncMock(return_value=[])
    mock_repo.find_since = AsyncMock(return_value=[])
    mock_repo.find_all = AsyncMock(return_value=[])
    mock_repo.get_statistics = AsyncMock(
        return_value=MagicMock(
            total=0,
            success_count=0,
            failed_count=0,
            timeout_count=0,
            success_rate=0.0,
            total_cost_usd=0.0,
            total_duration_seconds=0.0,
            avg_duration_seconds=0.0,
            by_agent={},
            by_status={},
        )
    )
    return mock_repo


@pytest.fixture
def mock_checkpoint_repo():
    """Create a mock CheckpointRepository."""
    mock_repo = MagicMock()
    mock_checkpoint = MagicMock()
    mock_checkpoint.id = "test-checkpoint-id"
    mock_checkpoint.name = "test-checkpoint"
    mock_checkpoint.notes = None

    # Async methods
    mock_repo.create = AsyncMock(return_value=mock_checkpoint)
    mock_repo.list_all = AsyncMock(return_value=[])
    mock_repo.get_by_id = AsyncMock(return_value=None)
    mock_repo.get_latest = AsyncMock(return_value=None)
    mock_repo.delete = AsyncMock(return_value=True)
    mock_repo.prune = AsyncMock(return_value=0)
    return mock_repo


@pytest.fixture
def mock_task_repo():
    """Create a mock TaskRepository."""
    mock_repo = MagicMock()
    # Async methods
    mock_repo.create_task = AsyncMock(return_value=MagicMock(id="T1"))
    mock_repo.get_task = AsyncMock(return_value=None)
    mock_repo.update_task = AsyncMock(return_value=MagicMock(id="T1"))
    mock_repo.get_all_tasks = AsyncMock(return_value=[])
    mock_repo.get_pending_tasks = AsyncMock(return_value=[])
    mock_repo.get_next_task = AsyncMock(return_value=None)
    mock_repo.get_progress = AsyncMock(
        return_value=MagicMock(total=0, completed=0, in_progress=0, pending=0)
    )
    return mock_repo


@pytest.fixture
def patch_db_repos(
    mock_phase_output_repo,
    mock_logs_repo,
    mock_workflow_repo,
    mock_session_repo,
    mock_budget_repo,
    mock_audit_repo,
    mock_checkpoint_repo,
    mock_task_repo,
):
    """Patch all DB repository getters.

    Use this fixture to mock all database interactions in tests.
    """
    with (
        patch(
            "orchestrator.db.repositories.phase_outputs.get_phase_output_repository",
            return_value=mock_phase_output_repo,
        ),
        patch(
            "orchestrator.db.repositories.logs.get_logs_repository",
            return_value=mock_logs_repo,
        ),
        patch(
            "orchestrator.db.repositories.workflow.get_workflow_repository",
            return_value=mock_workflow_repo,
        ),
        patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=mock_session_repo,
        ),
        patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=mock_budget_repo,
        ),
        patch(
            "orchestrator.db.repositories.audit.get_audit_repository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
            return_value=mock_checkpoint_repo,
        ),
        patch(
            "orchestrator.db.repositories.tasks.get_task_repository",
            return_value=mock_task_repo,
        ),
    ):
        yield {
            "phase_outputs": mock_phase_output_repo,
            "logs": mock_logs_repo,
            "workflow": mock_workflow_repo,
            "sessions": mock_session_repo,
            "budget": mock_budget_repo,
            "audit": mock_audit_repo,
            "checkpoints": mock_checkpoint_repo,
            "tasks": mock_task_repo,
        }


# -------------------------------------------------------------------
# Auto-patch DB for all tests
# -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def auto_patch_db_repos():
    """Automatically patch all DB repository getters for all tests.

    This prevents any test from accidentally connecting to SurrealDB.
    Tests that need real DB connections should mark themselves with
    pytest.mark.db_integration.
    """
    # Create mock repositories
    mock_phase_output = MagicMock()
    mock_phase_output.save_output = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_phase_output.save_plan = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_phase_output.save_cursor_feedback = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_phase_output.save_gemini_feedback = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_phase_output.save_task_result = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_phase_output.get_output = AsyncMock(return_value=None)
    mock_phase_output.get_plan = AsyncMock(return_value=None)
    mock_phase_output.get_phase_outputs = AsyncMock(return_value=[])

    mock_logs = MagicMock()
    mock_logs.create_log = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_logs.save_uat_document = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_logs.get_by_type = AsyncMock(return_value=[])
    mock_logs.get_by_task = AsyncMock(return_value=[])

    mock_workflow = MagicMock()
    mock_state = MagicMock()
    mock_state.project_dir = "/tmp/test"
    mock_state.current_phase = 1
    mock_state.phase_status = {}
    mock_state.iteration_count = 0
    mock_state.plan = None
    mock_state.validation_feedback = {}
    mock_state.verification_feedback = {}
    mock_state.implementation_result = None
    mock_state.next_decision = None
    mock_state.execution_mode = "afk"
    mock_state.discussion_complete = False
    mock_state.research_complete = False
    mock_state.research_findings = {}
    mock_state.token_usage = {}
    mock_workflow.get_state = AsyncMock(return_value=mock_state)
    mock_workflow.initialize_state = AsyncMock(return_value=mock_state)
    mock_workflow.update_state = AsyncMock(return_value=mock_state)
    mock_workflow.set_phase = AsyncMock(return_value=mock_state)
    mock_workflow.reset_state = AsyncMock(return_value=mock_state)
    mock_workflow.reset_to_phase = AsyncMock(return_value=mock_state)
    mock_workflow.get_summary = AsyncMock(return_value={"current_phase": 1, "project": "test"})
    mock_workflow.increment_iteration = AsyncMock(return_value=mock_state)
    mock_workflow.set_plan = AsyncMock(return_value=mock_state)
    mock_workflow.set_validation_feedback = AsyncMock(return_value=mock_state)
    mock_workflow.set_verification_feedback = AsyncMock(return_value=mock_state)
    mock_workflow.set_implementation_result = AsyncMock(return_value=mock_state)
    mock_workflow.record_git_commit = AsyncMock(return_value={})

    mock_session = MagicMock()
    mock_session.create_session = AsyncMock(return_value=MagicMock(id="test-session"))
    mock_session.get_active_session = AsyncMock(return_value=None)
    mock_session.get_session = AsyncMock(return_value=None)
    mock_session.close_session = AsyncMock(return_value=True)
    mock_session.touch_session = AsyncMock(return_value=MagicMock())
    mock_session.record_invocation = AsyncMock(return_value=MagicMock())
    mock_session.close_task_sessions = AsyncMock(return_value=0)
    mock_session.get_task_sessions = AsyncMock(return_value=[])

    mock_budget = MagicMock()
    mock_budget.record_spend = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_budget.get_task_cost = AsyncMock(return_value=0.0)
    mock_budget.get_total_cost = AsyncMock(return_value=0.0)
    mock_budget.get_summary = AsyncMock(return_value=MagicMock(
        total_cost_usd=0.0, by_agent={}, by_task={}, record_count=0,
        total_tokens_input=0, total_tokens_output=0, by_model={},
    ))

    mock_audit = MagicMock()
    mock_audit.create_entry = AsyncMock(return_value=MagicMock(id="test-entry"))
    mock_audit.update_result = AsyncMock(return_value=MagicMock())
    mock_audit.find_by_task = AsyncMock(return_value=[])
    mock_audit.find_all = AsyncMock(return_value=[])
    mock_audit.get_statistics = AsyncMock(return_value=MagicMock(
        total=0, success_count=0, failed_count=0, timeout_count=0,
        success_rate=0.0, total_cost_usd=0.0, total_duration_seconds=0.0,
        avg_duration_seconds=0.0, by_agent={}, by_status={},
    ))

    mock_checkpoint = MagicMock()
    mock_checkpoint.create_checkpoint = AsyncMock(return_value=MagicMock(id="test-cp"))
    mock_checkpoint.list_checkpoints = AsyncMock(return_value=[])
    mock_checkpoint.get_checkpoint = AsyncMock(return_value=None)
    mock_checkpoint.get_latest = AsyncMock(return_value=None)
    mock_checkpoint.delete_checkpoint = AsyncMock(return_value=True)
    mock_checkpoint.prune_old_checkpoints = AsyncMock(return_value=0)

    mock_task = MagicMock()
    mock_task.create_task = AsyncMock(return_value=MagicMock(id="T1"))
    mock_task.get_task = AsyncMock(return_value=None)
    mock_task.update_task = AsyncMock(return_value=MagicMock(id="T1"))
    mock_task.get_all_tasks = AsyncMock(return_value=[])
    mock_task.get_pending_tasks = AsyncMock(return_value=[])
    mock_task.get_next_task = AsyncMock(return_value=None)
    mock_task.get_progress = AsyncMock(return_value={"total": 0, "completed": 0, "in_progress": 0, "pending": 0, "completion_rate": 0.0})

    with (
        patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository", return_value=mock_phase_output),
        patch("orchestrator.db.repositories.logs.get_logs_repository", return_value=mock_logs),
        patch("orchestrator.db.repositories.workflow.get_workflow_repository", return_value=mock_workflow),
        patch("orchestrator.db.repositories.sessions.get_session_repository", return_value=mock_session),
        patch("orchestrator.db.repositories.budget.get_budget_repository", return_value=mock_budget),
        patch("orchestrator.db.repositories.audit.get_audit_repository", return_value=mock_audit),
        patch("orchestrator.db.repositories.checkpoints.get_checkpoint_repository", return_value=mock_checkpoint),
        patch("orchestrator.db.repositories.tasks.get_task_repository", return_value=mock_task),
    ):
        yield


# -------------------------------------------------------------------
# Original Fixtures
# -------------------------------------------------------------------


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Create PRODUCT.md with all required sections
        product_md = project_dir / "PRODUCT.md"
        product_md.write_text("""# Test Feature

## Feature
A test feature for testing the orchestrator. This feature allows users to
test the multi-agent orchestration system with various configurations.

## Goals
- Test goal 1: Ensure system works correctly
- Test goal 2: Validate all phases complete successfully
- Test goal 3: Verify error handling is robust

## Summary
A comprehensive test feature for testing the orchestrator.
""")

        yield project_dir


@pytest.fixture
def workflow_storage(temp_project_dir):
    """Create a workflow storage adapter for testing."""
    # Ensure workflow dir exists
    workflow_dir = temp_project_dir / ".workflow"
    workflow_dir.mkdir(exist_ok=True)

    # Get storage adapter
    storage = get_workflow_storage(temp_project_dir)
    storage.initialize_state(str(temp_project_dir))
    return storage


# Backwards compatibility alias
@pytest.fixture
def state_manager(workflow_storage):
    """Backwards compatibility alias for workflow_storage."""
    return workflow_storage


@pytest.fixture
def logger(temp_project_dir):
    """Create a logger for testing."""
    workflow_dir = temp_project_dir / ".workflow"
    workflow_dir.mkdir(exist_ok=True)
    return OrchestrationLogger(
        workflow_dir=workflow_dir,
        console_output=False,  # Disable console output in tests
        min_level=LogLevel.DEBUG,
    )


@pytest.fixture
def mock_claude_agent():
    """Create a mock Claude agent."""
    from orchestrator.agents.base import AgentResult

    mock = MagicMock()
    mock.name = "claude"
    mock.check_available.return_value = True
    mock.run_planning.return_value = AgentResult(
        success=True,
        parsed_output={
            "plan_name": "Test Plan",
            "summary": "Test summary",
            "phases": [
                {
                    "phase": 1,
                    "name": "Setup",
                    "tasks": [
                        {
                            "id": "T1",
                            "description": "Create files",
                            "files": ["test.py"],
                            "dependencies": [],
                        }
                    ],
                }
            ],
            "test_strategy": {
                "unit_tests": ["test_main.py"],
                "test_commands": ["pytest"],
            },
            "estimated_complexity": "low",
        },
    )
    mock.run_implementation.return_value = AgentResult(
        success=True,
        parsed_output={
            "implementation_complete": True,
            "files_created": ["src/main.py"],
            "files_modified": [],
            "test_results": {"passed": 5, "failed": 0},
        },
    )
    return mock


@pytest.fixture
def mock_cursor_agent():
    """Create a mock Cursor agent."""
    from orchestrator.agents.base import AgentResult

    mock = MagicMock()
    mock.name = "cursor"
    mock.check_available.return_value = True
    mock.run_validation.return_value = AgentResult(
        success=True,
        parsed_output={
            "reviewer": "cursor",
            "overall_assessment": "approve",
            "score": 8,
            "strengths": ["Good structure"],
            "concerns": [],
            "summary": "Plan looks good",
        },
    )
    mock.run_code_review.return_value = AgentResult(
        success=True,
        parsed_output={
            "reviewer": "cursor",
            "approved": True,
            "review_type": "code_review",
            "overall_code_quality": 8,
            "files_reviewed": [],
            "blocking_issues": [],
            "summary": "Code looks good",
        },
    )
    return mock


@pytest.fixture
def mock_gemini_agent():
    """Create a mock Gemini agent."""
    from orchestrator.agents.base import AgentResult

    mock = MagicMock()
    mock.name = "gemini"
    mock.check_available.return_value = True
    mock.run_validation.return_value = AgentResult(
        success=True,
        parsed_output={
            "reviewer": "gemini",
            "overall_assessment": "approve",
            "score": 9,
            "architecture_review": {
                "patterns_identified": ["Repository pattern"],
                "scalability_assessment": "good",
                "maintainability_assessment": "good",
                "concerns": [],
            },
            "summary": "Architecture is solid",
        },
    )
    mock.run_architecture_review.return_value = AgentResult(
        success=True,
        parsed_output={
            "reviewer": "gemini",
            "approved": True,
            "review_type": "architecture_review",
            "architecture_assessment": {
                "modularity_score": 8,
                "coupling_assessment": "loose",
                "cohesion_assessment": "high",
            },
            "blocking_issues": [],
            "summary": "Architecture review passed",
        },
    )
    return mock


@pytest.fixture
def sample_plan():
    """Sample implementation plan."""
    return {
        "plan_name": "Test Feature",
        "summary": "A test feature implementation",
        "phases": [
            {
                "phase": 1,
                "name": "Setup",
                "tasks": [
                    {
                        "id": "T1",
                        "description": "Create project structure",
                        "files": ["src/__init__.py", "src/main.py"],
                        "dependencies": [],
                    },
                    {
                        "id": "T2",
                        "description": "Implement core logic",
                        "files": ["src/core.py"],
                        "dependencies": ["T1"],
                    },
                ],
            },
            {
                "phase": 2,
                "name": "Testing",
                "tasks": [
                    {
                        "id": "T3",
                        "description": "Write unit tests",
                        "files": ["tests/test_core.py"],
                        "dependencies": ["T2"],
                    },
                ],
            },
        ],
        "test_strategy": {
            "unit_tests": ["tests/test_core.py"],
            "integration_tests": [],
            "test_commands": ["pytest tests/"],
        },
        "risks": ["Complexity may increase"],
        "estimated_complexity": "medium",
    }
