"""Tests for MCP workflow server.

Tests cover:
1. get_state - Get workflow state
2. update_phase - Update phase status
3. get_plan / save_plan - Plan management
4. create_checkpoint - Checkpoint creation
5. get_phase_feedback / save_phase_feedback - Feedback management
6. add_blocker / resolve_blocker - Blocker management

Run with: pytest tests/test_mcp_workflow.py -v
"""

import json
import pytest
from pathlib import Path
from datetime import datetime

# Import server functions
from mcp_servers.workflow.server import (
    get_state,
    update_phase,
    get_plan,
    save_plan,
    create_checkpoint,
    get_phase_feedback,
    save_phase_feedback,
    add_blocker,
    resolve_blocker,
    create_server,
    _get_workflow_dir,
    _load_state,
    _save_state,
    _create_default_state,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_projects_dir(tmp_path):
    """Create a temporary projects directory with sample project."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Create a sample project
    project_dir = projects_dir / "test-project"
    project_dir.mkdir()

    # Create workflow directory
    workflow_dir = project_dir / ".workflow"
    workflow_dir.mkdir()

    # Create default state
    state = {
        "project_name": "test-project",
        "current_phase": 1,
        "iteration_count": 0,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "phases": {
            "1": {"status": "pending", "attempts": 0, "blockers": []},
            "2": {"status": "pending", "attempts": 0, "blockers": []},
            "3": {"status": "pending", "attempts": 0, "blockers": []},
            "4": {"status": "pending", "attempts": 0, "blockers": []},
            "5": {"status": "pending", "attempts": 0, "blockers": []},
        },
        "git_commits": [],
        "checkpoints": [],
    }
    (workflow_dir / "state.json").write_text(json.dumps(state, indent=2))

    return projects_dir


@pytest.fixture
def mock_projects_root(temp_projects_dir, monkeypatch):
    """Mock PROJECTS_ROOT to use temp directory."""
    import mcp_servers.workflow.server as server_module
    monkeypatch.setattr(server_module, 'PROJECTS_ROOT', temp_projects_dir)
    return temp_projects_dir


# =============================================================================
# Test Helper Functions
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_workflow_dir(self, mock_projects_root):
        """Test _get_workflow_dir returns correct path."""
        result = _get_workflow_dir("test-project")
        assert result == mock_projects_root / "test-project" / ".workflow"

    def test_create_default_state(self):
        """Test _create_default_state creates valid state."""
        state = _create_default_state("my-project")

        assert state["project_name"] == "my-project"
        assert state["current_phase"] == 1
        assert state["iteration_count"] == 0
        assert "phases" in state
        assert len(state["phases"]) == 5
        assert state["phases"]["1"]["status"] == "pending"
        assert state["checkpoints"] == []
        assert state["git_commits"] == []

    def test_load_state_existing(self, mock_projects_root):
        """Test _load_state loads existing state."""
        state = _load_state("test-project")

        assert state["project_name"] == "test-project"
        assert "phases" in state

    def test_load_state_creates_default(self, mock_projects_root):
        """Test _load_state creates default when no state exists."""
        # Create project without state
        new_project = mock_projects_root / "new-project"
        new_project.mkdir()

        state = _load_state("new-project")

        assert state["project_name"] == "new-project"
        assert state["phases"]["1"]["status"] == "pending"

    def test_save_state(self, mock_projects_root):
        """Test _save_state saves state correctly."""
        state = _load_state("test-project")
        state["current_phase"] = 2
        state["phases"]["1"]["status"] = "completed"

        _save_state("test-project", state)

        # Reload and verify
        reloaded = _load_state("test-project")
        assert reloaded["current_phase"] == 2
        assert reloaded["phases"]["1"]["status"] == "completed"
        assert "updated_at" in reloaded


# =============================================================================
# Test get_state
# =============================================================================

class TestGetState:
    """Tests for get_state function."""

    @pytest.mark.asyncio
    async def test_get_state_success(self, mock_projects_root):
        """Test getting state for existing project."""
        result = await get_state("test-project")

        assert "error" not in result
        assert result["project_name"] == "test-project"
        assert "phases" in result
        assert result["current_phase"] == 1

    @pytest.mark.asyncio
    async def test_get_state_project_not_found(self, mock_projects_root):
        """Test getting state for non-existent project."""
        result = await get_state("nonexistent")

        assert "error" in result
        assert "not found" in result["error"]


# =============================================================================
# Test update_phase
# =============================================================================

class TestUpdatePhase:
    """Tests for update_phase function."""

    @pytest.mark.asyncio
    async def test_update_phase_to_in_progress(self, mock_projects_root):
        """Test updating phase to in_progress."""
        result = await update_phase(
            project="test-project",
            phase=1,
            status="in_progress",
        )

        assert result["success"] is True
        assert result["phase"] == 1
        assert result["status"] == "in_progress"

        # Verify state was updated
        state = _load_state("test-project")
        assert state["phases"]["1"]["status"] == "in_progress"
        assert "started_at" in state["phases"]["1"]
        assert state["current_phase"] == 1

    @pytest.mark.asyncio
    async def test_update_phase_to_completed(self, mock_projects_root):
        """Test updating phase to completed."""
        result = await update_phase(
            project="test-project",
            phase=1,
            status="completed",
        )

        assert result["success"] is True

        state = _load_state("test-project")
        assert state["phases"]["1"]["status"] == "completed"
        assert "completed_at" in state["phases"]["1"]

    @pytest.mark.asyncio
    async def test_update_phase_to_failed_with_error(self, mock_projects_root):
        """Test updating phase to failed with error message."""
        result = await update_phase(
            project="test-project",
            phase=1,
            status="failed",
            error="Validation failed",
        )

        assert result["success"] is True

        state = _load_state("test-project")
        assert state["phases"]["1"]["status"] == "failed"
        assert state["phases"]["1"]["error"] == "Validation failed"

    @pytest.mark.asyncio
    async def test_update_phase_increments_attempts(self, mock_projects_root):
        """Test that attempts are incremented on each update."""
        # First update
        await update_phase(project="test-project", phase=1, status="in_progress")
        state = _load_state("test-project")
        assert state["phases"]["1"]["attempts"] == 1

        # Second update
        await update_phase(project="test-project", phase=1, status="failed")
        state = _load_state("test-project")
        assert state["phases"]["1"]["attempts"] == 2

    @pytest.mark.asyncio
    async def test_update_phase_invalid_phase(self, mock_projects_root):
        """Test updating invalid phase number."""
        result = await update_phase(
            project="test-project",
            phase=6,
            status="in_progress",
        )

        assert "error" in result
        assert "Invalid phase" in result["error"]


# =============================================================================
# Test Plan Management
# =============================================================================

class TestPlanManagement:
    """Tests for plan-related functions."""

    @pytest.mark.asyncio
    async def test_save_plan(self, mock_projects_root):
        """Test saving a plan."""
        plan = {
            "feature": "Calculator",
            "steps": [
                {"id": 1, "description": "Create Calculator class"},
                {"id": 2, "description": "Add methods"},
            ],
        }

        result = await save_plan(project="test-project", plan=plan)

        assert result["success"] is True
        assert "plan_file" in result

        # Verify file was created
        plan_file = Path(result["plan_file"])
        assert plan_file.exists()

    @pytest.mark.asyncio
    async def test_get_plan_success(self, mock_projects_root):
        """Test getting a saved plan."""
        # First save a plan
        plan = {"feature": "Test", "steps": []}
        await save_plan(project="test-project", plan=plan)

        # Then get it
        result = await get_plan("test-project")

        assert "error" not in result
        assert result["project"] == "test-project"
        assert result["plan"]["feature"] == "Test"

    @pytest.mark.asyncio
    async def test_get_plan_not_found(self, mock_projects_root):
        """Test getting non-existent plan."""
        result = await get_plan("test-project")

        assert "error" in result
        assert "not found" in result["error"].lower()


# =============================================================================
# Test Checkpoint Management
# =============================================================================

class TestCheckpointManagement:
    """Tests for checkpoint functions."""

    @pytest.mark.asyncio
    async def test_create_checkpoint(self, mock_projects_root):
        """Test creating a checkpoint."""
        result = await create_checkpoint(
            project="test-project",
            label="Before implementation",
        )

        assert result["success"] is True
        assert result["checkpoint_id"] == 1
        assert result["label"] == "Before implementation"

        # Verify checkpoint was saved
        state = _load_state("test-project")
        assert len(state["checkpoints"]) == 1
        assert state["checkpoints"][0]["label"] == "Before implementation"

    @pytest.mark.asyncio
    async def test_create_checkpoint_auto_label(self, mock_projects_root):
        """Test creating checkpoint with auto-generated label."""
        result = await create_checkpoint(project="test-project")

        assert result["success"] is True
        assert "Checkpoint" in result["label"]

    @pytest.mark.asyncio
    async def test_create_multiple_checkpoints(self, mock_projects_root):
        """Test creating multiple checkpoints."""
        await create_checkpoint(project="test-project", label="First")
        await create_checkpoint(project="test-project", label="Second")
        result = await create_checkpoint(project="test-project", label="Third")

        assert result["checkpoint_id"] == 3

        state = _load_state("test-project")
        assert len(state["checkpoints"]) == 3

    @pytest.mark.asyncio
    async def test_checkpoint_captures_state(self, mock_projects_root):
        """Test that checkpoint captures current state."""
        # Update phase first
        await update_phase(project="test-project", phase=1, status="completed")
        await update_phase(project="test-project", phase=2, status="in_progress")

        # Create checkpoint
        await create_checkpoint(project="test-project", label="Mid-workflow")

        state = _load_state("test-project")
        checkpoint = state["checkpoints"][0]

        assert checkpoint["phase"] == 2
        assert "state_snapshot" in checkpoint
        assert checkpoint["state_snapshot"]["phases"]["1"]["status"] == "completed"


# =============================================================================
# Test Feedback Management
# =============================================================================

class TestFeedbackManagement:
    """Tests for feedback functions."""

    @pytest.mark.asyncio
    async def test_save_phase_feedback_validation(self, mock_projects_root):
        """Test saving validation feedback (phase 2)."""
        feedback = {
            "agent": "cursor",
            "approved": True,
            "score": 8.5,
            "concerns": [],
        }

        result = await save_phase_feedback(
            project="test-project",
            phase=2,
            agent="cursor",
            feedback=feedback,
        )

        assert result["success"] is True
        assert result["phase"] == 2
        assert result["agent"] == "cursor"

    @pytest.mark.asyncio
    async def test_save_phase_feedback_verification(self, mock_projects_root):
        """Test saving verification feedback (phase 4)."""
        feedback = {
            "agent": "gemini",
            "approved": False,
            "score": 5.0,
            "blocking_issues": ["Security vulnerability"],
        }

        result = await save_phase_feedback(
            project="test-project",
            phase=4,
            agent="gemini",
            feedback=feedback,
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_save_phase_feedback_invalid_phase(self, mock_projects_root):
        """Test saving feedback for invalid phase."""
        result = await save_phase_feedback(
            project="test-project",
            phase=3,  # Phase 3 is implementation, no feedback
            agent="cursor",
            feedback={},
        )

        assert "error" in result
        assert "phases 2 and 4" in result["error"]

    @pytest.mark.asyncio
    async def test_get_phase_feedback_success(self, mock_projects_root):
        """Test getting feedback."""
        # Save feedback first
        await save_phase_feedback(
            project="test-project",
            phase=2,
            agent="cursor",
            feedback={"approved": True, "score": 8.0},
        )
        await save_phase_feedback(
            project="test-project",
            phase=2,
            agent="gemini",
            feedback={"approved": True, "score": 7.5},
        )

        # Get feedback
        result = await get_phase_feedback(project="test-project", phase=2)

        assert "error" not in result
        assert result["phase"] == 2
        assert "cursor" in result["feedback"]
        assert "gemini" in result["feedback"]

    @pytest.mark.asyncio
    async def test_get_phase_feedback_not_found(self, mock_projects_root):
        """Test getting non-existent feedback."""
        result = await get_phase_feedback(project="test-project", phase=2)

        assert "error" in result
        assert "No feedback" in result["error"]

    @pytest.mark.asyncio
    async def test_get_phase_feedback_invalid_phase(self, mock_projects_root):
        """Test getting feedback for invalid phase."""
        result = await get_phase_feedback(project="test-project", phase=1)

        assert "error" in result


# =============================================================================
# Test Blocker Management
# =============================================================================

class TestBlockerManagement:
    """Tests for blocker functions."""

    @pytest.mark.asyncio
    async def test_add_blocker(self, mock_projects_root):
        """Test adding a blocker."""
        result = await add_blocker(
            project="test-project",
            phase=2,
            blocker="Missing security review",
            severity="high",
        )

        assert result["success"] is True
        assert result["blocker_id"] == 0

        state = _load_state("test-project")
        blockers = state["phases"]["2"]["blockers"]
        assert len(blockers) == 1
        assert blockers[0]["description"] == "Missing security review"
        assert blockers[0]["severity"] == "high"
        assert blockers[0]["resolved"] is False

    @pytest.mark.asyncio
    async def test_add_blocker_default_severity(self, mock_projects_root):
        """Test adding blocker with default severity."""
        result = await add_blocker(
            project="test-project",
            phase=1,
            blocker="Test blocker",
        )

        assert result["success"] is True

        state = _load_state("test-project")
        assert state["phases"]["1"]["blockers"][0]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_add_multiple_blockers(self, mock_projects_root):
        """Test adding multiple blockers."""
        await add_blocker(project="test-project", phase=2, blocker="First")
        await add_blocker(project="test-project", phase=2, blocker="Second")
        result = await add_blocker(project="test-project", phase=2, blocker="Third")

        assert result["blocker_id"] == 2

        state = _load_state("test-project")
        assert len(state["phases"]["2"]["blockers"]) == 3

    @pytest.mark.asyncio
    async def test_add_blocker_invalid_phase(self, mock_projects_root):
        """Test adding blocker to invalid phase."""
        result = await add_blocker(
            project="test-project",
            phase=10,
            blocker="Test",
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_resolve_blocker(self, mock_projects_root):
        """Test resolving a blocker."""
        # Add blocker first
        await add_blocker(project="test-project", phase=2, blocker="Test blocker")

        # Resolve it
        result = await resolve_blocker(
            project="test-project",
            phase=2,
            blocker_id=0,
        )

        assert result["success"] is True

        state = _load_state("test-project")
        blocker = state["phases"]["2"]["blockers"][0]
        assert blocker["resolved"] is True
        assert "resolved_at" in blocker

    @pytest.mark.asyncio
    async def test_resolve_blocker_invalid_id(self, mock_projects_root):
        """Test resolving non-existent blocker."""
        result = await resolve_blocker(
            project="test-project",
            phase=2,
            blocker_id=99,
        )

        assert "error" in result
        assert "Invalid blocker_id" in result["error"]


# =============================================================================
# Test Server Creation
# =============================================================================

class TestCreateServer:
    """Tests for server creation."""

    def test_create_server(self):
        """Test server is created successfully."""
        server = create_server()

        assert server is not None
        assert server.name == "mcp-workflow"


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_workflow_without_state_file(self, mock_projects_root):
        """Test handling project without state file."""
        # Create project without state
        new_project = mock_projects_root / "no-state-project"
        new_project.mkdir()
        (new_project / ".workflow").mkdir()

        result = await get_state("no-state-project")

        # Should create default state
        assert "error" not in result
        assert result["project_name"] == "no-state-project"

    @pytest.mark.asyncio
    async def test_concurrent_state_updates(self, mock_projects_root):
        """Test handling concurrent-like state updates."""
        import asyncio

        async def update_attempt(n):
            return await update_phase(
                project="test-project",
                phase=1,
                status="in_progress",
            )

        # Run multiple updates
        results = await asyncio.gather(*[update_attempt(i) for i in range(3)])

        # All should succeed
        for result in results:
            assert result["success"] is True

        # State should reflect updates
        state = _load_state("test-project")
        assert state["phases"]["1"]["attempts"] == 3

    @pytest.mark.asyncio
    async def test_phase_workflow_sequence(self, mock_projects_root):
        """Test typical workflow phase sequence."""
        # Phase 1: Planning
        await update_phase(project="test-project", phase=1, status="in_progress")
        await save_plan(project="test-project", plan={"feature": "Test"})
        await update_phase(project="test-project", phase=1, status="completed")

        # Phase 2: Validation
        await update_phase(project="test-project", phase=2, status="in_progress")
        await save_phase_feedback(
            project="test-project",
            phase=2,
            agent="cursor",
            feedback={"approved": True},
        )
        await update_phase(project="test-project", phase=2, status="completed")

        # Check final state
        state = _load_state("test-project")
        assert state["phases"]["1"]["status"] == "completed"
        assert state["phases"]["2"]["status"] == "completed"
        assert state["current_phase"] == 2


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
