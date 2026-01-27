"""
Fixtures for orchestrator-api tests.

Note: These tests require the orchestrator-api FastAPI app to be present.
Skip if not available.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add orchestrator-api to path if it exists
CONDUCTOR_ROOT = Path(__file__).parent.parent.parent
orchestrator_api_path = CONDUCTOR_ROOT / "orchestrator-api"

HAS_API = False
app = None
TestClient = None

if orchestrator_api_path.exists():
    sys.path.insert(0, str(orchestrator_api_path))
    sys.path.insert(0, str(CONDUCTOR_ROOT))
    try:
        from fastapi.testclient import TestClient
        from main import app

        HAS_API = True
    except ImportError:
        pass

# Skip all tests in this module if API not available
pytestmark = pytest.mark.skipif(not HAS_API, reason="orchestrator-api not available")


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    if not HAS_API or TestClient is None:
        pytest.skip("orchestrator-api not available")
    return TestClient(app)


@pytest.fixture
def temp_project_dir() -> Generator[Path, None, None]:
    """Create a temporary project directory."""
    temp_dir = tempfile.mkdtemp()
    project_dir = Path(temp_dir) / "test-project"
    project_dir.mkdir(parents=True)

    # Create required directories and files
    (project_dir / "Docs").mkdir()
    (project_dir / "Docs" / "PRODUCT.md").write_text(
        "# Test Feature\n\n## Summary\nA test feature."
    )
    (project_dir / ".workflow").mkdir()

    yield project_dir

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_project_with_state(temp_project_dir: Path) -> Path:
    """Create a project with workflow state."""
    state = {
        "project": "test-project",
        "current_phase": 2,
        "status": "in_progress",
        "task_breakdown": {
            "tasks": [
                {
                    "id": "T1",
                    "title": "Test Task 1",
                    "description": "First test task",
                    "status": "completed",
                    "priority": 1,
                    "dependencies": [],
                    "files_to_create": ["src/test.ts"],
                    "files_to_modify": [],
                    "acceptance_criteria": ["Must pass"],
                    "complexity_score": 3.0,
                    "created_at": "2024-01-01T00:00:00Z",
                    "completed_at": "2024-01-01T01:00:00Z",
                },
                {
                    "id": "T2",
                    "title": "Test Task 2",
                    "description": "Second test task",
                    "status": "in_progress",
                    "priority": 2,
                    "dependencies": ["T1"],
                    "files_to_create": [],
                    "files_to_modify": ["src/test.ts"],
                    "acceptance_criteria": ["Must work"],
                    "complexity_score": 2.5,
                    "created_at": "2024-01-01T00:00:00Z",
                    "started_at": "2024-01-01T01:30:00Z",
                },
                {
                    "id": "T3",
                    "title": "Test Task 3",
                    "status": "pending",
                    "priority": 3,
                    "dependencies": ["T2"],
                },
            ]
        },
    }

    state_file = temp_project_dir / ".workflow" / "state.json"
    state_file.write_text(json.dumps(state))

    return temp_project_dir


@pytest.fixture
def mock_project_manager(temp_project_dir: Path):
    """Mock ProjectManager for testing."""
    mock_pm = MagicMock()

    # Mock list_projects
    mock_pm.list_projects.return_value = [
        {
            "name": "test-project",
            "path": str(temp_project_dir),
            "created_at": "2024-01-01T00:00:00Z",
            "current_phase": 1,
            "has_documents": True,
            "has_product_spec": True,
            "has_claude_md": False,
            "has_gemini_md": False,
            "has_cursor_rules": False,
        }
    ]

    # Mock get_project
    mock_pm.get_project.return_value = temp_project_dir

    # Mock get_project_status
    mock_pm.get_project_status.return_value = {
        "name": "test-project",
        "path": str(temp_project_dir),
        "config": {"name": "test-project"},
        "state": {"phase": 1},
        "files": {"Docs/PRODUCT.md": True},
        "phases": {},
    }

    # Mock init_project
    mock_pm.init_project.return_value = {
        "success": True,
        "project_dir": str(temp_project_dir),
        "message": "Project initialized",
    }

    return mock_pm


@pytest.fixture
def mock_orchestrator():
    """Mock Orchestrator for testing."""
    mock_orch = MagicMock()

    # Mock status
    mock_orch.status.return_value = {
        "project": "test-project",
        "current_phase": 2,
        "phase_statuses": {"1": "completed", "2": "in_progress"},
    }

    # Mock health_check
    mock_orch.health_check.return_value = {
        "status": "healthy",
        "project": "test-project",
        "current_phase": 2,
        "phase_status": "in_progress",
        "iteration_count": 3,
        "last_updated": "2024-01-01T12:00:00Z",
        "agents": {"claude": True, "cursor": True, "gemini": True},
        "langgraph_enabled": True,
        "has_context": True,
        "total_commits": 5,
    }

    # Mock get_workflow_definition
    mock_orch.get_workflow_definition.return_value = {
        "nodes": [
            {"id": "planning", "label": "Planning"},
            {"id": "validation", "label": "Validation"},
        ],
        "edges": [{"source": "planning", "target": "validation"}],
    }

    # Mock check_prerequisites
    mock_orch.check_prerequisites.return_value = (True, [])

    # Mock rollback_to_phase
    mock_orch.rollback_to_phase.return_value = {
        "success": True,
        "rolled_back_to": "checkpoint_phase_2",
        "current_phase": 2,
        "message": "Rolled back to phase 2",
    }

    return mock_orch


@pytest.fixture
def mock_budget_manager():
    """Mock BudgetManager for testing."""
    mock_bm = MagicMock()

    mock_bm.get_budget_status.return_value = {
        "total_spent_usd": 1.25,
        "project_budget_usd": 10.0,
        "project_remaining_usd": 8.75,
        "project_used_percent": 12.5,
        "task_count": 3,
        "record_count": 15,
        "task_spent": {"T1": 0.75, "T2": 0.50},
        "updated_at": "2024-01-01T12:00:00Z",
        "enabled": True,
    }

    mock_bm.get_task_spending_report.return_value = [
        {"task_id": "T1", "spent_usd": 0.75, "budget_usd": 2.0},
        {"task_id": "T2", "spent_usd": 0.50, "budget_usd": 2.0},
    ]

    return mock_bm


@pytest.fixture
def mock_audit_storage():
    """Mock audit storage for testing."""
    mock_audit = MagicMock()

    # Mock query
    mock_entry = MagicMock()
    mock_entry.id = "audit-1"
    mock_entry.agent = "claude"
    mock_entry.task_id = "T1"
    mock_entry.session_id = "session-1"
    mock_entry.prompt_hash = "abc123"
    mock_entry.prompt_length = 1500
    mock_entry.command_args = ["-p", "test"]
    mock_entry.exit_code = 0
    mock_entry.status = "success"
    mock_entry.duration_seconds = 120.5
    mock_entry.output_length = 5000
    mock_entry.error_length = 0
    mock_entry.parsed_output_type = "json"
    mock_entry.cost_usd = 0.05
    mock_entry.model = "claude-3-sonnet"
    mock_entry.metadata = {}
    mock_entry.timestamp = "2024-01-01T12:00:00Z"

    mock_audit.query.return_value = [mock_entry]
    mock_audit.get_task_history.return_value = [mock_entry]

    # Mock statistics
    mock_stats = MagicMock()
    mock_stats.total = 50
    mock_stats.success_count = 45
    mock_stats.failed_count = 3
    mock_stats.timeout_count = 2
    mock_stats.success_rate = 0.90
    mock_stats.total_cost_usd = 2.50
    mock_stats.total_duration_seconds = 3600.0
    mock_stats.avg_duration_seconds = 72.0
    mock_stats.by_agent = {"claude": 25, "cursor": 15, "gemini": 10}
    mock_stats.by_status = {"success": 45, "failed": 3, "timeout": 2}

    mock_audit.get_statistics.return_value = mock_stats

    return mock_audit
