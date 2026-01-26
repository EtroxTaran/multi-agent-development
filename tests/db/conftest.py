"""DB-specific pytest fixtures.

Provides fixtures for testing database connection, repositories,
and related functionality with proper mocking.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.db.connection import Connection, ConnectionStats
from orchestrator.db.repositories.workflow import WorkflowState


@pytest.fixture
def mock_surreal_client():
    """Create a mock SurrealDB client."""
    client = MagicMock()
    client.connect = AsyncMock()
    client.signin = AsyncMock()
    client.authenticate = AsyncMock()
    client.use = AsyncMock()
    client.close = AsyncMock()
    client.query = AsyncMock(return_value=[{"result": []}])
    client.create = AsyncMock(return_value={"id": "test:123"})
    client.select = AsyncMock(return_value=[])
    client.update = AsyncMock(return_value={"id": "test:123"})
    client.delete = AsyncMock(return_value=True)
    client.live = AsyncMock(return_value="live-query-uuid")
    client.kill = AsyncMock()
    return client


@pytest.fixture
def mock_surreal_config():
    """Create a mock SurrealDB configuration."""
    from orchestrator.db.config import SurrealConfig

    return SurrealConfig(
        url="ws://localhost:8000/rpc",
        namespace="test",
        default_database="test_db",
        user="root",
        password="root",
        pool_size=3,
        connect_timeout=5.0,
        query_timeout=30.0,
        skip_ssl_verify=False,
    )


@pytest.fixture
def mock_connection(mock_surreal_client, mock_surreal_config):
    """Create a mock Connection instance."""
    conn = Connection(mock_surreal_config, "test_db")
    conn._client = mock_surreal_client
    conn._connected = True
    return conn


@pytest.fixture
def sample_workflow_state():
    """Create a sample workflow state for testing."""
    return WorkflowState(
        project_dir="/tmp/test-project",
        current_phase=1,
        phase_status={
            "1": {"status": "pending", "attempts": 0},
            "2": {"status": "pending", "attempts": 0},
            "3": {"status": "pending", "attempts": 0},
            "4": {"status": "pending", "attempts": 0},
            "5": {"status": "pending", "attempts": 0},
        },
        iteration_count=0,
        execution_mode="afk",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def sample_phase_output():
    """Create a sample phase output for testing."""
    return {
        "phase": 1,
        "output_type": "plan",
        "content": {
            "plan_name": "Test Plan",
            "summary": "Test summary",
            "tasks": [{"id": "T1", "title": "Test task"}],
        },
        "metadata": {"version": "1.0"},
    }


@pytest.fixture
def sample_log_entry():
    """Create a sample log entry for testing."""
    return {
        "log_type": "escalation",
        "content": {
            "reason": "Test escalation",
            "phase": 2,
            "severity": "warning",
        },
        "metadata": {"source": "test"},
    }


@pytest.fixture
def connection_stats():
    """Create a ConnectionStats instance for testing."""
    return ConnectionStats(
        total_connections=5,
        active_connections=2,
        failed_connections=0,
        total_queries=100,
        failed_queries=3,
        last_connected=datetime.now(),
        last_error=None,
    )
