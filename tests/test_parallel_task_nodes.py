"""Tests for parallel task implementation and verification nodes."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.langgraph.state import TaskStatus


class DummyWorktreeManager:
    """Minimal WorktreeManager stub for tests."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def create_worktree(self, suffix: str):
        path = self.project_dir / f"wt-{suffix}"
        path.mkdir(exist_ok=True)
        return path

    def merge_worktree(self, worktree_path: Path, commit_message: str):
        return "deadbeef"


@pytest.mark.asyncio
async def test_implement_tasks_parallel_node_success(temp_project_dir):
    """Parallel implementation completes and clears batch state."""
    from orchestrator.langgraph.nodes import implement_task as implement_module
    from orchestrator.langgraph.nodes.task import nodes as task_nodes

    state = {
        "project_dir": str(temp_project_dir),
        "project_name": "test",
        "current_task_id": "T1",
        "current_task_ids": ["T1", "T2"],
        "in_flight_task_ids": ["T1", "T2"],
        "tasks": [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING, "attempts": 0},
            {"id": "T2", "title": "Task 2", "status": TaskStatus.PENDING, "attempts": 0},
        ],
        "completed_task_ids": [],
        "failed_task_ids": [],
    }

    outputs = [
        {"success": True, "output": '{"task_id":"T1","status":"completed"}', "error": None},
        {"success": True, "output": '{"task_id":"T2","status":"completed"}', "error": None},
    ]

    with patch.object(task_nodes, "WorktreeManager", DummyWorktreeManager), patch.object(
        task_nodes, "_run_task_in_worktree", side_effect=outputs
    ), patch.object(task_nodes, "_check_budget_before_task", return_value=None):
        result = await implement_module.implement_tasks_parallel_node(state)

    assert result["next_decision"] == "continue"
    assert result["current_task_ids"] == []
    assert result["in_flight_task_ids"] == []
    assert result["current_task_id"] is None
    assert len(result["tasks"]) == 2


@pytest.mark.asyncio
async def test_verify_tasks_parallel_node_success(temp_project_dir):
    """Parallel verification completes tasks and clears batch state."""
    from orchestrator.langgraph.nodes import verify_task as verify_module

    # Create files required by tasks
    (temp_project_dir / "src").mkdir()
    (temp_project_dir / "src" / "a.py").write_text("# a")
    (temp_project_dir / "src" / "b.py").write_text("# b")

    state = {
        "project_dir": str(temp_project_dir),
        "project_name": "test",
        "current_task_id": "T1",
        "current_task_ids": ["T1", "T2"],
        "in_flight_task_ids": ["T1", "T2"],
        "tasks": [
            {
                "id": "T1",
                "title": "Task 1",
                "status": TaskStatus.IN_PROGRESS,
                "attempts": 1,
                "files_to_create": ["src/a.py"],
            },
            {
                "id": "T2",
                "title": "Task 2",
                "status": TaskStatus.IN_PROGRESS,
                "attempts": 1,
                "files_to_create": ["src/b.py"],
            },
        ],
        "completed_task_ids": [],
        "failed_task_ids": [],
    }

    with patch.object(
        verify_module,
        "_run_task_tests",
        new_callable=AsyncMock,
        return_value={"success": True},
    ):
        result = await verify_module.verify_tasks_parallel_node(state)

    assert set(result["completed_task_ids"]) == {"T1", "T2"}
    assert result["next_decision"] == "continue"
    assert result["current_task_ids"] == []
    assert result["in_flight_task_ids"] == []
    assert result["current_task_id"] is None
