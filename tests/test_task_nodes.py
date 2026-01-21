"""Tests for task loop nodes.

Tests cover:
1. Task data model and state reducers
2. Task breakdown node
3. Select task node
4. Implement task node
5. Verify task node
6. Task routers

Run with: pytest tests/test_task_nodes.py -v
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch


# =============================================================================
# Test Task Data Model
# =============================================================================

class TestTaskModel:
    """Test Task and Milestone data models."""

    def test_task_status_enum(self):
        """Test TaskStatus enum values."""
        from orchestrator.langgraph.state import TaskStatus

        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.BLOCKED == "blocked"

    def test_create_task(self):
        """Test task creation helper."""
        from orchestrator.langgraph.state import create_task, TaskStatus

        task = create_task(
            task_id="T1",
            title="Create Calculator class",
            user_story="As a developer, I want a Calculator class",
            acceptance_criteria=["Can be imported", "Can be instantiated"],
            dependencies=[],
            priority="high",
            estimated_complexity="medium",
        )

        assert task["id"] == "T1"
        assert task["title"] == "Create Calculator class"
        assert task["status"] == TaskStatus.PENDING
        assert task["priority"] == "high"
        assert task["attempts"] == 0
        assert task["max_attempts"] == 3
        assert len(task["acceptance_criteria"]) == 2

    def test_milestone_model(self):
        """Test Milestone TypedDict."""
        from orchestrator.langgraph.state import Milestone, TaskStatus

        milestone = Milestone(
            id="M1",
            name="Core Calculator",
            description="Implement core calculator functions",
            task_ids=["T1", "T2", "T3"],
            status=TaskStatus.PENDING,
        )

        assert milestone["id"] == "M1"
        assert milestone["name"] == "Core Calculator"
        assert len(milestone["task_ids"]) == 3


class TestTaskReducers:
    """Test task-related state reducers."""

    def test_append_unique_reducer(self):
        """Test unique list appending reducer."""
        from orchestrator.langgraph.state import _append_unique

        existing = ["T1", "T2"]
        new = ["T2", "T3"]  # T2 is duplicate
        result = _append_unique(existing, new)

        assert len(result) == 3
        assert "T1" in result
        assert "T2" in result
        assert "T3" in result

    def test_append_unique_with_none(self):
        """Test append unique with None existing."""
        from orchestrator.langgraph.state import _append_unique

        result = _append_unique(None, ["T1", "T2"])
        assert result == ["T1", "T2"]

    def test_merge_tasks_reducer(self):
        """Test task merging reducer."""
        from orchestrator.langgraph.state import _merge_tasks, TaskStatus

        existing = [
            {"id": "T1", "status": TaskStatus.PENDING, "attempts": 0},
            {"id": "T2", "status": TaskStatus.PENDING, "attempts": 0},
        ]
        new = [
            {"id": "T1", "status": TaskStatus.COMPLETED, "attempts": 1},  # Updated
            {"id": "T3", "status": TaskStatus.PENDING, "attempts": 0},  # New
        ]

        result = _merge_tasks(existing, new)

        assert len(result) == 3
        t1 = next(t for t in result if t["id"] == "T1")
        assert t1["status"] == TaskStatus.COMPLETED
        assert t1["attempts"] == 1

    def test_merge_tasks_with_none(self):
        """Test merge tasks with None existing."""
        from orchestrator.langgraph.state import _merge_tasks

        result = _merge_tasks(None, [{"id": "T1"}])
        assert len(result) == 1


class TestTaskHelpers:
    """Test task state helper functions."""

    def test_get_task_by_id(self):
        """Test retrieving task by ID."""
        from orchestrator.langgraph.state import get_task_by_id, TaskStatus

        state = {
            "tasks": [
                {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
                {"id": "T2", "title": "Task 2", "status": TaskStatus.PENDING},
            ]
        }

        task = get_task_by_id(state, "T1")
        assert task is not None
        assert task["title"] == "Task 1"

        # Non-existent task
        task = get_task_by_id(state, "T99")
        assert task is None

    def test_get_pending_tasks(self):
        """Test getting pending tasks."""
        from orchestrator.langgraph.state import get_pending_tasks, TaskStatus

        state = {
            "tasks": [
                {"id": "T1", "status": TaskStatus.PENDING},
                {"id": "T2", "status": TaskStatus.COMPLETED},
                {"id": "T3", "status": TaskStatus.PENDING},
            ]
        }

        pending = get_pending_tasks(state)
        assert len(pending) == 2
        assert all(t["status"] == TaskStatus.PENDING for t in pending)

    def test_get_available_tasks(self):
        """Test getting tasks with satisfied dependencies."""
        from orchestrator.langgraph.state import get_available_tasks, TaskStatus

        state = {
            "tasks": [
                {"id": "T1", "status": TaskStatus.PENDING, "dependencies": []},
                {"id": "T2", "status": TaskStatus.PENDING, "dependencies": ["T1"]},
                {"id": "T3", "status": TaskStatus.PENDING, "dependencies": ["T1", "T2"]},
            ],
            "completed_task_ids": [],
        }

        # Initially only T1 is available
        available = get_available_tasks(state)
        assert len(available) == 1
        assert available[0]["id"] == "T1"

        # After T1 is completed, T2 becomes available
        state["completed_task_ids"] = ["T1"]
        available = get_available_tasks(state)
        assert len(available) == 1
        assert available[0]["id"] == "T2"

        # After T1 and T2 are completed, T3 becomes available
        state["completed_task_ids"] = ["T1", "T2"]
        available = get_available_tasks(state)
        assert len(available) == 1
        assert available[0]["id"] == "T3"

    def test_all_tasks_completed(self):
        """Test checking if all tasks are completed."""
        from orchestrator.langgraph.state import all_tasks_completed

        # No tasks = completed
        state = {"tasks": [], "completed_task_ids": []}
        assert all_tasks_completed(state) is True

        # Some tasks incomplete
        state = {
            "tasks": [{"id": "T1"}, {"id": "T2"}],
            "completed_task_ids": ["T1"],
        }
        assert all_tasks_completed(state) is False

        # All tasks completed
        state["completed_task_ids"] = ["T1", "T2"]
        assert all_tasks_completed(state) is True


# =============================================================================
# Test Task Breakdown Node
# =============================================================================

class TestTaskBreakdownNode:
    """Test task breakdown node logic."""

    def test_parse_acceptance_criteria(self):
        """Test parsing acceptance criteria from PRODUCT.md."""
        from orchestrator.langgraph.nodes.task_breakdown import _parse_acceptance_criteria

        product_md = """# Feature

## Acceptance Criteria
- [ ] Can create new calculator instance
- [ ] Can add two numbers
- [ ] Can subtract two numbers
- [x] Has documentation
"""
        criteria = _parse_acceptance_criteria(product_md)

        assert len(criteria) == 4
        assert "Can create new calculator instance" in criteria

    def test_parse_acceptance_criteria_numbered(self):
        """Test parsing numbered acceptance criteria."""
        from orchestrator.langgraph.nodes.task_breakdown import _parse_acceptance_criteria

        product_md = """# Feature

## Acceptance Criteria
1. First criterion
2. Second criterion
3. Third criterion
"""
        criteria = _parse_acceptance_criteria(product_md)

        assert len(criteria) == 3
        assert "First criterion" in criteria

    def test_generate_user_story(self):
        """Test user story generation."""
        from orchestrator.langgraph.nodes.task_breakdown import _generate_user_story

        story = _generate_user_story("Create Calculator class", "")
        assert "as a" in story.lower()
        assert "want" in story.lower()

        story = _generate_user_story("Add validation logic", "")
        assert "as a" in story.lower()

    def test_estimate_priority(self):
        """Test priority estimation."""
        from orchestrator.langgraph.nodes.task_breakdown import _estimate_priority

        assert _estimate_priority("Critical security fix", []) == "critical"
        assert _estimate_priority("Important feature", []) == "high"
        assert _estimate_priority("Nice to have enhancement", []) == "medium"
        assert _estimate_priority("Optional cleanup", []) == "low"
        assert _estimate_priority("Regular task", []) == "medium"  # Default

    def test_estimate_complexity(self):
        """Test complexity estimation."""
        from orchestrator.langgraph.nodes.task_breakdown import _estimate_complexity

        assert _estimate_complexity("Complex integration", ["a.py"] * 10) == "high"
        assert _estimate_complexity("Moderate update", ["a.py", "b.py", "c.py"]) == "medium"
        assert _estimate_complexity("Simple fix", ["a.py"]) == "low"

    def test_assign_dependencies(self):
        """Test dependency assignment based on file relationships."""
        from orchestrator.langgraph.nodes.task_breakdown import _assign_dependencies

        tasks = [
            {"id": "T1", "files_to_create": ["src/core.py"], "files_to_modify": [], "dependencies": []},
            {"id": "T2", "files_to_create": [], "files_to_modify": ["src/core.py"], "dependencies": []},
        ]

        result = _assign_dependencies(tasks)

        # T2 modifies src/core.py which T1 creates, so T2 depends on T1
        t2 = next(t for t in result if t["id"] == "T2")
        assert "T1" in t2["dependencies"]


# =============================================================================
# Test Select Task Node
# =============================================================================

class TestSelectTaskNode:
    """Test select task node logic."""

    def test_sort_tasks_by_priority(self):
        """Test task sorting by priority."""
        from orchestrator.langgraph.nodes.select_task import _sort_tasks_by_priority

        tasks = [
            {"id": "T1", "priority": "low", "milestone_id": "M1"},
            {"id": "T2", "priority": "critical", "milestone_id": "M1"},
            {"id": "T3", "priority": "high", "milestone_id": "M1"},
        ]

        sorted_tasks = _sort_tasks_by_priority(tasks, [{"id": "M1"}])

        assert sorted_tasks[0]["id"] == "T2"  # Critical first
        assert sorted_tasks[1]["id"] == "T3"  # High second
        assert sorted_tasks[2]["id"] == "T1"  # Low last

    def test_get_task_summary(self):
        """Test task summary generation."""
        from orchestrator.langgraph.nodes.select_task import get_task_summary
        from orchestrator.langgraph.state import TaskStatus

        state = {
            "tasks": [
                {"id": "T1", "status": TaskStatus.PENDING},
                {"id": "T2", "status": TaskStatus.IN_PROGRESS},
                {"id": "T3", "status": TaskStatus.COMPLETED},
            ],
            "completed_task_ids": ["T3"],
            "failed_task_ids": [],
            "current_task_id": "T2",
        }

        summary = get_task_summary(state)

        assert summary["total"] == 3
        assert "T1" in summary["pending"]
        assert "T2" in summary["in_progress"]
        assert "T3" in summary["completed"]
        assert summary["current_task_id"] == "T2"


# =============================================================================
# Test Task Routers
# =============================================================================

class TestTaskRouters:
    """Test task loop routing logic."""

    def test_task_breakdown_router_continue(self):
        """Test routing after task breakdown."""
        from orchestrator.langgraph.routers.task import task_breakdown_router

        state = {
            "next_decision": "continue",
            "tasks": [{"id": "T1"}],
        }
        result = task_breakdown_router(state)
        assert result == "select_task"

    def test_task_breakdown_router_no_tasks(self):
        """Test routing when no tasks created."""
        from orchestrator.langgraph.routers.task import task_breakdown_router

        state = {
            "next_decision": "continue",
            "tasks": [],
        }
        result = task_breakdown_router(state)
        assert result == "__end__"

    def test_select_task_router_to_implement(self):
        """Test routing from select to implement."""
        from orchestrator.langgraph.routers.task import select_task_router

        state = {
            "next_decision": "continue",
            "current_task_id": "T1",
            "tasks": [{"id": "T1"}],
            "completed_task_ids": [],
        }
        result = select_task_router(state)
        assert result == "implement_task"

    def test_select_task_router_all_done(self):
        """Test routing when all tasks done."""
        from orchestrator.langgraph.routers.task import select_task_router

        state = {
            "next_decision": "continue",
            "current_task_id": None,
            "tasks": [{"id": "T1"}],
            "completed_task_ids": ["T1"],
        }
        result = select_task_router(state)
        assert result == "build_verification"

    def test_verify_task_router_loop_back(self):
        """Test verify router loops back to select."""
        from orchestrator.langgraph.routers.task import verify_task_router

        state = {
            "next_decision": "continue",
            "current_task_id": None,
        }
        result = verify_task_router(state)
        assert result == "select_task"

    def test_verify_task_router_retry(self):
        """Test verify router routes to retry."""
        from orchestrator.langgraph.routers.task import verify_task_router

        state = {
            "next_decision": "retry",
            "current_task_id": "T1",
            "tasks": [{"id": "T1", "attempts": 1, "max_attempts": 3}],
        }
        result = verify_task_router(state)
        assert result == "implement_task"

    def test_verify_task_router_escalate_max_retries(self):
        """Test verify router escalates on max retries."""
        from orchestrator.langgraph.routers.task import verify_task_router

        state = {
            "next_decision": "retry",
            "current_task_id": "T1",
            "tasks": [{"id": "T1", "attempts": 3, "max_attempts": 3}],
        }
        result = verify_task_router(state)
        assert result == "human_escalation"


# =============================================================================
# Test Verify Task Node
# =============================================================================

class TestVerifyTaskNode:
    """Test verify task node logic."""

    def test_verify_files_created(self, temp_project_dir):
        """Test file creation verification."""
        from orchestrator.langgraph.nodes.verify_task import _verify_files_created

        # Create some files
        src_dir = temp_project_dir / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")

        task = {
            "id": "T1",
            "files_to_create": ["src/main.py"],
        }

        result = _verify_files_created(temp_project_dir, task)
        assert result["success"] is True

        # Missing file
        task["files_to_create"] = ["src/missing.py"]
        result = _verify_files_created(temp_project_dir, task)
        assert result["success"] is False
        assert "src/missing.py" in result["missing"]

    def test_detect_test_command_python(self, temp_project_dir):
        """Test test command detection for Python."""
        from orchestrator.langgraph.nodes.verify_task import _detect_test_command

        # Create pyproject.toml
        (temp_project_dir / "pyproject.toml").write_text("[build-system]")

        cmd = _detect_test_command(temp_project_dir)
        assert cmd == "pytest"

    def test_detect_test_command_node(self, temp_project_dir):
        """Test test command detection for Node.js."""
        from orchestrator.langgraph.nodes.verify_task import _detect_test_command

        (temp_project_dir / "package.json").write_text(json.dumps({
            "scripts": {"test": "jest"}
        }))

        cmd = _detect_test_command(temp_project_dir)
        assert cmd == "npm test"


# =============================================================================
# Test Implement Task Node
# =============================================================================

class TestImplementTaskNode:
    """Test implement task node logic."""

    def test_build_completed_context(self):
        """Test building context from completed tasks."""
        from orchestrator.langgraph.nodes.implement_task import _build_completed_context

        state = {
            "tasks": [
                {"id": "T1", "title": "Create module", "implementation_notes": "Done"},
                {"id": "T2", "title": "Add tests", "implementation_notes": "Added 5 tests"},
            ],
            "completed_task_ids": ["T1"],
        }

        context = _build_completed_context(state)

        assert "PREVIOUSLY COMPLETED" in context
        assert "T1" in context
        assert "T2" not in context  # Not completed yet

    def test_format_criteria(self):
        """Test acceptance criteria formatting."""
        from orchestrator.langgraph.nodes.implement_task import _format_criteria

        criteria = ["First criterion", "Second criterion"]
        formatted = _format_criteria(criteria)

        assert "- [ ] First criterion" in formatted
        assert "- [ ] Second criterion" in formatted

    def test_handle_task_error_retry(self):
        """Test error handling with retries remaining."""
        from orchestrator.langgraph.nodes.implement_task import _handle_task_error
        from orchestrator.langgraph.state import TaskStatus

        task = {"id": "T1", "attempts": 1, "max_attempts": 3}

        result = _handle_task_error(task, "Test error")

        assert result["next_decision"] == "retry"
        assert task["status"] == TaskStatus.PENDING

    def test_handle_task_error_max_retries(self):
        """Test error handling with max retries exceeded."""
        from orchestrator.langgraph.nodes.implement_task import _handle_task_error
        from orchestrator.langgraph.state import TaskStatus

        task = {"id": "T1", "attempts": 3, "max_attempts": 3}

        result = _handle_task_error(task, "Test error")

        assert result["next_decision"] == "escalate"
        assert task["status"] == TaskStatus.FAILED
        assert "T1" in result["failed_task_ids"]


# =============================================================================
# Test Initial State with Tasks
# =============================================================================

class TestInitialStateWithTasks:
    """Test initial state includes task fields."""

    def test_create_initial_state_has_task_fields(self):
        """Test initial state has task-related fields."""
        from orchestrator.langgraph.state import create_initial_state

        state = create_initial_state("/project", "test")

        assert "tasks" in state
        assert "milestones" in state
        assert "current_task_id" in state
        assert "completed_task_ids" in state
        assert "failed_task_ids" in state
        assert state["tasks"] == []
        assert state["milestones"] == []

    def test_workflow_summary_includes_tasks(self):
        """Test workflow summary includes task info."""
        from orchestrator.langgraph.state import (
            create_initial_state,
            get_workflow_summary,
            TaskStatus,
        )

        state = create_initial_state("/project", "test")
        state["tasks"] = [
            {"id": "T1", "status": TaskStatus.COMPLETED},
            {"id": "T2", "status": TaskStatus.PENDING},
        ]
        state["completed_task_ids"] = ["T1"]

        summary = get_workflow_summary(state)

        assert "tasks" in summary
        assert summary["tasks"]["total"] == 2
        assert summary["tasks"]["completed"] == 1
        assert summary["tasks"]["pending"] == 1


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
