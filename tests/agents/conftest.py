"""Agent-specific pytest fixtures.

Provides fixtures for testing agent adapters, session management,
budget control, and error context handling.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.agents.adapter import ClaudeAdapter, CursorAdapter, GeminiAdapter, IterationResult
from orchestrator.agents.budget import (
    DEFAULT_INVOCATION_BUDGET_USD,
    DEFAULT_PROJECT_BUDGET_USD,
    DEFAULT_TASK_BUDGET_USD,
    BudgetConfig,
    BudgetManager,
    SpendRecord,
)
from orchestrator.agents.error_context import ErrorContext, ErrorContextManager
from orchestrator.agents.session_manager import SessionInfo, SessionManager


def create_mock_budget_storage():
    """Create a mock BudgetStorageAdapter with in-memory tracking.

    This mock fully implements the BudgetStorageAdapter interface to allow
    unit testing without a real database connection.
    """
    mock_storage = MagicMock()

    # In-memory state tracking
    mock_storage._records = []
    mock_storage._total_spent = 0.0
    mock_storage._task_spent = {}

    # Budget configuration properties
    mock_storage.project_budget_usd = DEFAULT_PROJECT_BUDGET_USD
    mock_storage.task_budget_usd = DEFAULT_TASK_BUDGET_USD
    mock_storage.invocation_budget_usd = DEFAULT_INVOCATION_BUDGET_USD

    def record_spend(task_id, agent, cost_usd, tokens_input=None, tokens_output=None, model=None):
        """Record a spend event."""
        record = MagicMock()
        record.id = f"spend-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(mock_storage._records)}"
        record.task_id = task_id
        record.agent = agent
        record.cost_usd = cost_usd
        record.model = model
        record.tokens_input = tokens_input
        record.tokens_output = tokens_output
        record.timestamp = datetime.now().isoformat()
        mock_storage._records.append(record)

        # Update totals
        mock_storage._total_spent += cost_usd
        if task_id not in mock_storage._task_spent:
            mock_storage._task_spent[task_id] = 0.0
        mock_storage._task_spent[task_id] += cost_usd

        return record

    def get_task_spent(task_id):
        """Get total spent for a task."""
        return mock_storage._task_spent.get(task_id, 0.0)

    def get_total_spent():
        """Get total spent across all tasks."""
        return mock_storage._total_spent

    def get_project_remaining():
        """Get remaining project budget."""
        return mock_storage.project_budget_usd - mock_storage._total_spent

    def get_invocation_budget(task_id):
        """Get per-invocation budget for a task."""
        return mock_storage.invocation_budget_usd

    def get_summary():
        """Get budget summary."""
        summary = MagicMock()
        summary.total_cost_usd = mock_storage._total_spent
        summary.by_task = dict(mock_storage._task_spent)
        summary.by_agent = {}
        summary.record_count = len(mock_storage._records)

        for r in mock_storage._records:
            if r.agent not in summary.by_agent:
                summary.by_agent[r.agent] = 0.0
            summary.by_agent[r.agent] += r.cost_usd

        return summary

    # Mock database backend for reset operations
    mock_db = MagicMock()

    async def reset_task_spending(task_id):
        if task_id in mock_storage._task_spent:
            amount = mock_storage._task_spent.pop(task_id)
            mock_storage._total_spent -= amount
            return 1
        return 0

    async def delete_task_records(task_id):
        return await reset_task_spending(task_id)

    async def reset_all_spending():
        count = len(mock_storage._task_spent)
        mock_storage._total_spent = 0.0
        mock_storage._task_spent = {}
        mock_storage._records = []
        return count

    mock_db.reset_task_spending = reset_task_spending
    mock_db.delete_task_records = delete_task_records
    mock_db.reset_all_spending = reset_all_spending

    def _get_db_backend():
        return mock_db

    # Set up all methods
    mock_storage.record_spend = MagicMock(side_effect=record_spend)
    mock_storage.get_task_spent = MagicMock(side_effect=get_task_spent)
    mock_storage.get_total_spent = MagicMock(side_effect=get_total_spent)
    mock_storage.get_project_remaining = MagicMock(side_effect=get_project_remaining)
    mock_storage.get_invocation_budget = MagicMock(side_effect=get_invocation_budget)
    mock_storage.get_summary = MagicMock(side_effect=get_summary)
    mock_storage._get_db_backend = MagicMock(return_value=mock_db)

    return mock_storage


class MockSessionData:
    """Simple class to mock session storage data without MagicMock attribute issues."""

    def __init__(self, session_id, task_id, agent):
        self.id = session_id
        self.task_id = task_id
        self.agent = agent
        self.status = "active"
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.invocation_count = 1


def create_mock_session_storage():
    """Create a mock SessionStorageAdapter with in-memory tracking."""
    mock_storage = MagicMock()

    # In-memory session store
    mock_storage._sessions = {}
    mock_storage._session_counter = 0

    def create_session(task_id, agent, session_id=None):
        mock_storage._session_counter += 1
        sid = session_id or f"{task_id}-mock-session-{mock_storage._session_counter}"
        session_data = MockSessionData(sid, task_id, agent)
        mock_storage._sessions[task_id] = session_data
        return session_data

    def get_active_session(task_id):
        session = mock_storage._sessions.get(task_id)
        if session and session.status == "active":
            return session
        return None

    def close_session(task_id):
        if task_id in mock_storage._sessions:
            mock_storage._sessions[task_id].status = "closed"
            return True
        return False

    def touch_session(task_id):
        if task_id in mock_storage._sessions:
            session = mock_storage._sessions[task_id]
            session.updated_at = datetime.now()
            session.invocation_count += 1
            return session
        return None

    def delete_session(task_id):
        if task_id in mock_storage._sessions:
            del mock_storage._sessions[task_id]
            return True
        return False

    def get_resume_args(task_id):
        session = mock_storage._sessions.get(task_id)
        if session and session.status == "active":
            return ["--resume", session.id]
        return []

    mock_storage.create_session = MagicMock(side_effect=create_session)
    mock_storage.get_active_session = MagicMock(side_effect=get_active_session)
    mock_storage.close_session = MagicMock(side_effect=close_session)
    mock_storage.touch_session = MagicMock(side_effect=touch_session)
    mock_storage.delete_session = MagicMock(side_effect=delete_session)
    mock_storage.get_resume_args = MagicMock(side_effect=get_resume_args)

    return mock_storage


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
    """Create a SessionManager for testing with mocked storage."""
    manager = SessionManager(temp_project_dir, session_ttl_hours=24)
    # Replace storage with mock
    mock_storage = create_mock_session_storage()
    manager._storage = mock_storage
    return manager


@pytest.fixture
def budget_manager(temp_project_dir):
    """Create a BudgetManager for testing with mocked storage."""
    manager = BudgetManager(temp_project_dir)
    # Replace storage with mock that tracks state
    mock_storage = create_mock_budget_storage()
    manager._storage = mock_storage
    return manager


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
