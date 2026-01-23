"""Tests for workflow endpoints."""

from unittest.mock import AsyncMock, patch


class TestGetWorkflowStatus:
    """Tests for GET /projects/{project_name}/workflow/status endpoint."""

    def test_get_status_not_started(self, test_client, mock_project_manager, mock_orchestrator):
        """Get status should return not_started for new project."""
        mock_orchestrator.status_langgraph = AsyncMock(
            return_value={
                "mode": "langgraph",
                "status": "not_started",
                "project": "test-project",
                "phase_status": {},
            }
        )

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.get("/projects/test-project/workflow/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_started"

    def test_get_status_in_progress(self, test_client, mock_project_manager, mock_orchestrator):
        """Get status should return in_progress with phase info."""
        mock_orchestrator.status_langgraph = AsyncMock(
            return_value={
                "mode": "langgraph",
                "status": "in_progress",
                "project": "test-project",
                "current_phase": 2,
                "phase_status": {"1": "completed", "2": "in_progress"},
            }
        )

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.get("/projects/test-project/workflow/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
        assert data["current_phase"] == 2

    def test_get_status_paused(self, test_client, mock_project_manager, mock_orchestrator):
        """Get status should return paused with interrupt info."""
        mock_orchestrator.status_langgraph = AsyncMock(
            return_value={
                "mode": "langgraph",
                "status": "paused",
                "project": "test-project",
                "current_phase": 3,
                "pending_interrupt": {
                    "type": "escalation",
                    "message": "Human input required",
                },
            }
        )

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.get("/projects/test-project/workflow/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"
        assert data["pending_interrupt"] is not None

    def test_get_status_project_not_found(self, test_client, mock_project_manager):
        """Get status should return 404 for missing project."""
        mock_project_manager.get_project.return_value = None

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_project_dir") as mock_get_dir:
                from fastapi import HTTPException

                mock_get_dir.side_effect = HTTPException(
                    status_code=404, detail="Project not found"
                )
                response = test_client.get("/projects/nonexistent/workflow/status")

        assert response.status_code == 404


class TestGetWorkflowHealth:
    """Tests for GET /projects/{project_name}/workflow/health endpoint."""

    def test_get_health_healthy(self, test_client, mock_project_manager, mock_orchestrator):
        """Get health should return healthy status."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.get("/projects/test-project/workflow/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["agents"]["claude"] is True

    def test_get_health_includes_metrics(
        self, test_client, mock_project_manager, mock_orchestrator
    ):
        """Get health should include iteration count and commits."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.get("/projects/test-project/workflow/health")

        assert response.status_code == 200
        data = response.json()
        assert "iteration_count" in data
        assert "total_commits" in data

    def test_get_health_degraded(self, test_client, mock_project_manager, mock_orchestrator):
        """Get health should return degraded when agent unavailable."""
        mock_orchestrator.health_check.return_value = {
            "status": "degraded",
            "agents": {"claude": True, "cursor": False, "gemini": True},
        }

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.get("/projects/test-project/workflow/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"


class TestGetWorkflowGraph:
    """Tests for GET /projects/{project_name}/workflow/graph endpoint."""

    def test_get_graph_returns_nodes_and_edges(
        self, test_client, mock_project_manager, mock_orchestrator
    ):
        """Get graph should return nodes and edges."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.get("/projects/test-project/workflow/graph")

        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) >= 1


class TestStartWorkflow:
    """Tests for POST /projects/{project_name}/workflow/start endpoint."""

    def test_start_workflow_success(self, test_client, mock_project_manager, mock_orchestrator):
        """Start workflow should return success."""
        mock_orchestrator.run_langgraph = AsyncMock()

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.post(
                    "/projects/test-project/workflow/start",
                    json={"start_phase": 1, "end_phase": 5},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["mode"] == "langgraph"

    def test_start_workflow_prerequisites_failed(
        self, test_client, mock_project_manager, mock_orchestrator
    ):
        """Start workflow should return 400 when prerequisites fail."""
        mock_orchestrator.check_prerequisites.return_value = (
            False,
            ["PRODUCT.md is required"],
        )

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.post(
                    "/projects/test-project/workflow/start",
                    json={"start_phase": 1, "end_phase": 5},
                )

        assert response.status_code == 400

    def test_start_workflow_with_autonomous(
        self, test_client, mock_project_manager, mock_orchestrator
    ):
        """Start workflow should accept autonomous flag."""
        mock_orchestrator.run_langgraph = AsyncMock()

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.post(
                    "/projects/test-project/workflow/start",
                    json={
                        "start_phase": 1,
                        "end_phase": 5,
                        "autonomous": True,
                    },
                )

        assert response.status_code == 200

    def test_start_workflow_custom_phase_range(
        self, test_client, mock_project_manager, mock_orchestrator
    ):
        """Start workflow should accept custom phase range."""
        mock_orchestrator.run_langgraph = AsyncMock()

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.post(
                    "/projects/test-project/workflow/start",
                    json={"start_phase": 2, "end_phase": 4},
                )

        assert response.status_code == 200


class TestResumeWorkflow:
    """Tests for POST /projects/{project_name}/workflow/resume endpoint."""

    def test_resume_workflow_success(self, test_client, mock_project_manager, mock_orchestrator):
        """Resume workflow should return success."""
        mock_orchestrator.resume_langgraph = AsyncMock()

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.post("/projects/test-project/workflow/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_resume_workflow_autonomous(self, test_client, mock_project_manager, mock_orchestrator):
        """Resume workflow should accept autonomous flag."""
        mock_orchestrator.resume_langgraph = AsyncMock()

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.post(
                    "/projects/test-project/workflow/resume?autonomous=true"
                )

        assert response.status_code == 200


class TestRollbackWorkflow:
    """Tests for POST /projects/{project_name}/workflow/rollback/{phase} endpoint."""

    def test_rollback_success(self, test_client, mock_project_manager, mock_orchestrator):
        """Rollback should return success."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.post("/projects/test-project/workflow/rollback/2")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_rollback_invalid_phase_low(self, test_client, mock_project_manager):
        """Rollback should return 400 for phase < 1."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.post("/projects/test-project/workflow/rollback/0")

        assert response.status_code == 400

    def test_rollback_invalid_phase_high(self, test_client, mock_project_manager):
        """Rollback should return 400 for phase > 5."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.post("/projects/test-project/workflow/rollback/6")

        assert response.status_code == 400


class TestResetWorkflow:
    """Tests for POST /projects/{project_name}/workflow/reset endpoint."""

    def test_reset_success(self, test_client, mock_project_manager, mock_orchestrator):
        """Reset should return success message."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.Orchestrator", return_value=mock_orchestrator):
                response = test_client.post("/projects/test-project/workflow/reset")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "reset" in data["message"].lower()
