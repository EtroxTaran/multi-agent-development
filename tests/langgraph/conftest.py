"""LangGraph-specific pytest fixtures.

Provides fixtures for testing workflow state, nodes, and routers.
"""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.langgraph.state import (
    AgentFeedback,
    PhaseState,
    PhaseStatus,
    WorkflowState,
    create_initial_state,
    create_task,
)


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory with required structure."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()

    # Create workflow directory
    workflow_dir = project_dir / ".workflow"
    workflow_dir.mkdir()

    # Create docs directory
    docs_dir = project_dir / "docs"
    docs_dir.mkdir()

    # Create a minimal PRODUCT.md
    product_md = docs_dir / "PRODUCT.md"
    product_md.write_text(
        """# Test Feature

## Summary
A test feature for testing.

## Problem Statement
We need this for testing purposes.

## Acceptance Criteria
- [ ] Tests pass
- [ ] Coverage is good
- [ ] No errors

## Example Inputs/Outputs
Input: test
Output: success

## Technical Constraints
None

## Testing Strategy
Unit tests

## Definition of Done
- [ ] Code complete
- [ ] Tests pass
- [ ] Reviewed
"""
    )

    return project_dir


@pytest.fixture
def minimal_workflow_state(temp_project_dir) -> WorkflowState:
    """Create a minimal workflow state for testing."""
    return create_initial_state(
        project_name="test-project",
        project_dir=str(temp_project_dir),
    )


@pytest.fixture
def workflow_state_phase_1(temp_project_dir) -> WorkflowState:
    """Create workflow state at phase 1 (planning)."""
    state = create_initial_state(
        project_name="test-project",
        project_dir=str(temp_project_dir),
    )
    state["current_phase"] = 1
    state["product_spec"] = {
        "feature_name": "Test Feature",
        "summary": "A test feature",
        "acceptance_criteria": ["Tests pass", "Coverage good"],
    }
    return state


@pytest.fixture
def workflow_state_phase_2(temp_project_dir) -> WorkflowState:
    """Create workflow state at phase 2 (validation)."""
    state = create_initial_state(
        project_name="test-project",
        project_dir=str(temp_project_dir),
    )
    state["current_phase"] = 2
    state["plan"] = {
        "plan_name": "Test Plan",
        "tasks": [
            {
                "id": "T1",
                "title": "Implement feature",
                "acceptance_criteria": ["Tests pass"],
                "files_to_create": ["src/feature.py"],
                "files_to_modify": [],
                "test_files": ["tests/test_feature.py"],
            }
        ],
    }
    return state


@pytest.fixture
def workflow_state_phase_3(temp_project_dir) -> WorkflowState:
    """Create workflow state at phase 3 (implementation)."""
    state = create_initial_state(
        project_name="test-project",
        project_dir=str(temp_project_dir),
    )
    state["current_phase"] = 3
    state["plan"] = {
        "plan_name": "Test Plan",
        "tasks": [
            {
                "id": "T1",
                "title": "Implement feature",
                "status": "pending",
                "acceptance_criteria": ["Tests pass"],
                "files_to_create": ["src/feature.py"],
                "files_to_modify": [],
                "test_files": ["tests/test_feature.py"],
            }
        ],
    }
    state["validation_feedback"] = {
        "cursor": AgentFeedback(
            agent="cursor",
            approved=True,
            score=8.0,
            assessment="approved",
            summary="Plan looks good",
        ),
        "gemini": AgentFeedback(
            agent="gemini",
            approved=True,
            score=8.5,
            assessment="approved",
            summary="Architecture is sound",
        ),
    }
    return state


@pytest.fixture
def workflow_state_phase_4(temp_project_dir) -> WorkflowState:
    """Create workflow state at phase 4 (verification)."""
    state = create_initial_state(
        project_name="test-project",
        project_dir=str(temp_project_dir),
    )
    state["current_phase"] = 4
    state["plan"] = {
        "plan_name": "Test Plan",
        "tasks": [{"id": "T1", "title": "Implement feature", "status": "completed"}],
    }
    state["implementation_result"] = {
        "files_created": ["src/feature.py"],
        "files_modified": [],
        "test_results": {"passed": 5, "failed": 0},
    }
    return state


@pytest.fixture
def sample_plan() -> dict[str, Any]:
    """Create a sample valid plan."""
    return {
        "plan_name": "Test Feature Implementation",
        "tasks": [
            {
                "id": "T1",
                "title": "Set up project structure",
                "acceptance_criteria": ["Directory structure created", "Config files present"],
                "files_to_create": ["src/__init__.py", "src/config.py"],
                "files_to_modify": [],
                "test_files": ["tests/test_config.py"],
                "dependencies": [],
            },
            {
                "id": "T2",
                "title": "Implement core logic",
                "acceptance_criteria": ["Core function implemented", "Tests pass"],
                "files_to_create": ["src/core.py"],
                "files_to_modify": ["src/config.py"],
                "test_files": ["tests/test_core.py"],
                "dependencies": ["T1"],
            },
        ],
        "milestones": [
            {"id": "M1", "title": "Initial Setup", "tasks": ["T1"]},
            {"id": "M2", "title": "Core Implementation", "tasks": ["T2"]},
        ],
    }


@pytest.fixture
def cursor_feedback_approved() -> AgentFeedback:
    """Create approved cursor feedback."""
    return AgentFeedback(
        agent="cursor",
        approved=True,
        score=8.5,
        assessment="approved",
        concerns=[],
        blocking_issues=[],
        summary="Code quality looks good",
        raw_output={"score": 8.5, "approved": True, "findings": []},
    )


@pytest.fixture
def cursor_feedback_rejected() -> AgentFeedback:
    """Create rejected cursor feedback."""
    return AgentFeedback(
        agent="cursor",
        approved=False,
        score=4.0,
        assessment="needs_changes",
        concerns=["Missing error handling", "No input validation"],
        blocking_issues=["SQL injection vulnerability in query builder"],
        summary="Security issues found",
        raw_output={
            "score": 4.0,
            "approved": False,
            "findings": [
                {
                    "file": "src/db.py",
                    "line": 42,
                    "severity": "CRITICAL",
                    "description": "SQL injection vulnerability",
                }
            ],
        },
    )


@pytest.fixture
def gemini_feedback_approved() -> AgentFeedback:
    """Create approved gemini feedback."""
    return AgentFeedback(
        agent="gemini",
        approved=True,
        score=8.0,
        assessment="approved",
        concerns=[],
        blocking_issues=[],
        summary="Architecture follows best practices",
        raw_output={"score": 8.0, "approved": True, "comments": []},
    )


@pytest.fixture
def gemini_feedback_rejected() -> AgentFeedback:
    """Create rejected gemini feedback."""
    return AgentFeedback(
        agent="gemini",
        approved=False,
        score=5.0,
        assessment="needs_changes",
        concerns=["Tight coupling between modules", "Missing dependency injection"],
        blocking_issues=["Circular dependency between core and utils"],
        summary="Architecture issues found",
        raw_output={
            "score": 5.0,
            "approved": False,
            "comments": [
                {"description": "Circular dependency", "remediation": "Use interface segregation"}
            ],
        },
    )


@pytest.fixture
def mock_specialist_runner():
    """Mock SpecialistRunner for agent invocations."""
    runner = MagicMock()
    agent = MagicMock()
    agent.run = MagicMock(
        return_value=MagicMock(
            success=True,
            output='{"score": 8.0, "approved": true}',
            parsed_output={"score": 8.0, "approved": True},
            error=None,
        )
    )
    runner.create_agent = MagicMock(return_value=agent)
    return runner


@pytest.fixture
def mock_phase_output_repository():
    """Mock phase output repository."""
    repo = MagicMock()
    repo.save_plan = AsyncMock()
    repo.save_cursor_feedback = AsyncMock()
    repo.save_gemini_feedback = AsyncMock()
    repo.save_cursor_review = AsyncMock()
    repo.save_gemini_review = AsyncMock()
    repo.save_output = AsyncMock()
    repo.get_by_type = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_db_repositories(mock_phase_output_repository):
    """Patch database repositories."""
    with patch(
        "orchestrator.langgraph.nodes.planning.get_phase_output_repository",
        return_value=mock_phase_output_repository,
    ), patch(
        "orchestrator.langgraph.nodes.validation.get_phase_output_repository",
        return_value=mock_phase_output_repository,
    ), patch(
        "orchestrator.langgraph.nodes.verification.get_phase_output_repository",
        return_value=mock_phase_output_repository,
    ):
        yield mock_phase_output_repository


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return create_task(
        task_id="T1",
        title="Implement authentication",
        acceptance_criteria=["Users can log in", "Sessions are managed", "Passwords hashed"],
        files_to_create=["src/auth.py"],
        files_to_modify=["src/app.py"],
    )


@pytest.fixture
def sample_error_context():
    """Create a sample error context for testing."""
    return {
        "error_type": "AssertionError",
        "error_message": "Test failed: expected 5, got 3",
        "source_node": "implementation",
        "recoverable": True,
        "retry_count": 0,
        "stack_trace": "Traceback (most recent call last):\n  File 'test.py', line 10\n    assert result == 5",
        "suggested_actions": ["review_test_logic", "check_implementation"],
        "timestamp": datetime.now().isoformat(),
    }


@pytest.fixture
def phase_status_fresh() -> dict[str, PhaseState]:
    """Create fresh phase status with no progress."""
    return {
        "1": PhaseState(),
        "2": PhaseState(),
        "3": PhaseState(),
        "4": PhaseState(),
        "5": PhaseState(),
    }


@pytest.fixture
def phase_status_phase_2_complete() -> dict[str, PhaseState]:
    """Create phase status with phases 1-2 complete."""
    return {
        "1": PhaseState(
            status=PhaseStatus.COMPLETED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
        ),
        "2": PhaseState(
            status=PhaseStatus.COMPLETED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
        ),
        "3": PhaseState(),
        "4": PhaseState(),
        "5": PhaseState(),
    }
