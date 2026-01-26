"""Agent-specific pytest fixtures.

Provides fixtures for testing agent adapters, session management,
budget control, and error context handling.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.agents.adapter import (
    ClaudeAdapter,
    CursorAdapter,
    GeminiAdapter,
    IterationResult,
)
from orchestrator.agents.budget import BudgetConfig, BudgetManager, SpendRecord
from orchestrator.agents.error_context import ErrorContext, ErrorContextManager
from orchestrator.agents.session_manager import SessionInfo, SessionManager


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    workflow_dir = project_dir / ".workflow"
    workflow_dir.mkdir()
    return project_dir


@pytest.fixture
def mock_subprocess():
    """Mock asyncio subprocess for agent execution."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(
        return_value=(b'{"status": "completed", "result": "success"}', b"")
    )
    return mock_process


@pytest.fixture
def claude_adapter(temp_project_dir):
    """Create a Claude adapter for testing."""
    return ClaudeAdapter(temp_project_dir, model="sonnet", timeout=300)


@pytest.fixture
def cursor_adapter(temp_project_dir):
    """Create a Cursor adapter for testing."""
    return CursorAdapter(temp_project_dir, model="codex-5.2", timeout=300)


@pytest.fixture
def gemini_adapter(temp_project_dir):
    """Create a Gemini adapter for testing."""
    return GeminiAdapter(temp_project_dir, model="gemini-2.0-flash", timeout=300)


@pytest.fixture
def session_manager(temp_project_dir):
    """Create a SessionManager for testing."""
    return SessionManager(temp_project_dir, session_ttl_hours=24)


@pytest.fixture
def budget_manager(temp_project_dir):
    """Create a BudgetManager for testing."""
    return BudgetManager(temp_project_dir)


@pytest.fixture
def error_context_manager(temp_project_dir):
    """Create an ErrorContextManager for testing."""
    return ErrorContextManager(temp_project_dir)


@pytest.fixture
def sample_session_info():
    """Create a sample SessionInfo for testing."""
    return SessionInfo(
        session_id="T1-abc123def456",
        task_id="T1",
        project_dir="/tmp/test-project",
        created_at=datetime.now(),
        last_used_at=datetime.now(),
        iteration=1,
        is_active=True,
        metadata={"test": "value"},
    )


@pytest.fixture
def sample_spend_record():
    """Create a sample SpendRecord for testing."""
    return SpendRecord(
        id="spend-20260126120000-0001",
        timestamp=datetime.now().isoformat(),
        task_id="T1",
        agent="claude",
        amount_usd=0.05,
        model="sonnet",
        prompt_tokens=1000,
        completion_tokens=500,
        metadata={"iteration": 1},
    )


@pytest.fixture
def sample_error_context():
    """Create a sample ErrorContext for testing."""
    return ErrorContext(
        id="err-T1-20260126120000-1",
        task_id="T1",
        timestamp=datetime.now().isoformat(),
        attempt=1,
        error_type="test_failure",
        error_message="AssertionError: expected 5, got 3",
        stdout_excerpt="Running tests...",
        stderr_excerpt="FAILED test_calc.py::test_add",
        files_involved=["src/calc.py", "tests/test_calc.py"],
        stack_trace="Traceback...",
        suggestions=["Check the implementation"],
        metadata={"phase": "implementation"},
    )


@pytest.fixture
def sample_budget_config():
    """Create a sample BudgetConfig for testing."""
    return BudgetConfig(
        project_budget_usd=50.00,
        task_budget_usd=5.00,
        invocation_budget_usd=1.00,
        task_budgets={"T1": 2.00},
        warn_at_percent=80.0,
        enabled=True,
    )


@pytest.fixture
def sample_iteration_result():
    """Create a sample IterationResult for testing."""
    return IterationResult(
        success=True,
        output='{"status": "completed"}',
        parsed_output={"status": "completed"},
        completion_detected=True,
        exit_code=0,
        duration_seconds=10.5,
        error=None,
        files_changed=["src/calc.py"],
        session_id="session-123",
        cost_usd=0.05,
        model="sonnet",
    )


@pytest.fixture
def expired_session_info():
    """Create an expired SessionInfo for testing."""
    return SessionInfo(
        session_id="T2-expired123",
        task_id="T2",
        project_dir="/tmp/test-project",
        created_at=datetime.now() - timedelta(hours=48),
        last_used_at=datetime.now() - timedelta(hours=48),
        iteration=1,
        is_active=True,
        metadata={},
    )
