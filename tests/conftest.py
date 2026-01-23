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

# Import mock factories
from tests.helpers.mock_factories import (
    create_mock_phase_output_repo,
    create_mock_logs_repo,
    create_mock_workflow_repo,
    create_mock_session_repo,
    create_mock_budget_repo,
    create_mock_audit_repo,
    create_mock_checkpoint_repo,
    create_mock_task_repo,
    create_mock_workflow_state,
)


# -------------------------------------------------------------------
# DB Mock Fixtures for Unit Tests
# -------------------------------------------------------------------


@pytest.fixture
def mock_phase_output_repo():
    """Create a mock PhaseOutputRepository."""
    return create_mock_phase_output_repo()


@pytest.fixture
def mock_logs_repo():
    """Create a mock LogsRepository."""
    return create_mock_logs_repo()


@pytest.fixture
def mock_workflow_repo():
    """Create a mock WorkflowRepository."""
    return create_mock_workflow_repo()


@pytest.fixture
def mock_session_repo():
    """Create a mock SessionRepository."""
    return create_mock_session_repo()


@pytest.fixture
def mock_budget_repo():
    """Create a mock BudgetRepository."""
    return create_mock_budget_repo()


@pytest.fixture
def mock_audit_repo():
    """Create a mock AuditRepository."""
    return create_mock_audit_repo()


@pytest.fixture
def mock_checkpoint_repo():
    """Create a mock CheckpointRepository."""
    return create_mock_checkpoint_repo()


@pytest.fixture
def mock_task_repo():
    """Create a mock TaskRepository."""
    return create_mock_task_repo()


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
    with (
        patch(
            "orchestrator.db.repositories.phase_outputs.get_phase_output_repository",
            return_value=create_mock_phase_output_repo(),
        ),
        patch(
            "orchestrator.db.repositories.logs.get_logs_repository",
            return_value=create_mock_logs_repo(),
        ),
        patch(
            "orchestrator.db.repositories.workflow.get_workflow_repository",
            return_value=create_mock_workflow_repo(),
        ),
        patch(
            "orchestrator.db.repositories.sessions.get_session_repository",
            return_value=create_mock_session_repo(),
        ),
        patch(
            "orchestrator.db.repositories.budget.get_budget_repository",
            return_value=create_mock_budget_repo(),
        ),
        patch(
            "orchestrator.db.repositories.audit.get_audit_repository",
            return_value=create_mock_audit_repo(),
        ),
        patch(
            "orchestrator.db.repositories.checkpoints.get_checkpoint_repository",
            return_value=create_mock_checkpoint_repo(),
        ),
        patch(
            "orchestrator.db.repositories.tasks.get_task_repository",
            return_value=create_mock_task_repo(),
        ),
        patch(
            "orchestrator.storage.surreal_store.get_workflow_repository",
            return_value=create_mock_workflow_repo(),
        ),
        patch(
            "orchestrator.storage.surreal_store.SurrealWorkflowRepository._get_db_backend",
            return_value=create_mock_workflow_repo(),
        ),
    ):
        yield


# -------------------------------------------------------------------
# Global State Cleanup
# -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def cleanup_global_state():
    """Reset global state after each test.

    This ensures test isolation by cleaning up any global singletons
    or cached state that may persist between tests.
    """
    yield
    # Add cleanup for any known global singletons here
    # Example: ModuleName._instance = None


# -------------------------------------------------------------------
# Project Directory Fixtures
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


# -------------------------------------------------------------------
# Agent Mock Fixtures
# -------------------------------------------------------------------


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


# -------------------------------------------------------------------
# Sample Data Fixtures
# -------------------------------------------------------------------


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
