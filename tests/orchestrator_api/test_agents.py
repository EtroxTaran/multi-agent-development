"""Tests for agent and audit endpoints."""

from unittest.mock import patch


class TestGetAgents:
    """Tests for GET /projects/{project_name}/agents endpoint."""

    def test_get_agents_returns_list(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get agents should return agent list."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/agents")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_agents_includes_all_agents(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get agents should include claude, cursor, and gemini."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/agents")

        assert response.status_code == 200
        data = response.json()
        agent_names = [a["agent"] for a in data]
        assert "claude" in agent_names
        assert "cursor" in agent_names
        assert "gemini" in agent_names

    def test_get_agents_includes_status(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get agents should include availability status."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/agents")

        assert response.status_code == 200
        data = response.json()
        for agent in data:
            assert "available" in agent
            assert "total_invocations" in agent

    def test_get_agents_project_not_found(self, test_client, mock_project_manager):
        """Get agents should return 404 when project not found."""
        mock_project_manager.get_project.return_value = None

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_project_dir") as mock_get_dir:
                from fastapi import HTTPException

                mock_get_dir.side_effect = HTTPException(
                    status_code=404, detail="Project not found"
                )
                response = test_client.get("/projects/nonexistent/agents")

        assert response.status_code == 404


class TestGetAudit:
    """Tests for GET /projects/{project_name}/audit endpoint."""

    def test_get_audit_returns_entries(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get audit should return audit entries."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/audit")

        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data

    def test_get_audit_with_agent_filter(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get audit should filter by agent."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/audit?agent=claude")

        assert response.status_code == 200
        mock_audit_storage.query.assert_called_once()
        call_kwargs = mock_audit_storage.query.call_args[1]
        assert call_kwargs["agent"] == "claude"

    def test_get_audit_with_task_filter(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get audit should filter by task_id."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/audit?task_id=T1")

        assert response.status_code == 200
        mock_audit_storage.query.assert_called_once()
        call_kwargs = mock_audit_storage.query.call_args[1]
        assert call_kwargs["task_id"] == "T1"

    def test_get_audit_with_status_filter(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get audit should filter by status."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/audit?status=success")

        assert response.status_code == 200
        mock_audit_storage.query.assert_called_once()
        call_kwargs = mock_audit_storage.query.call_args[1]
        assert call_kwargs["status"] == "success"

    def test_get_audit_with_since_hours(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get audit should filter by time range."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/audit?since_hours=24")

        assert response.status_code == 200
        mock_audit_storage.query.assert_called_once()
        call_kwargs = mock_audit_storage.query.call_args[1]
        assert call_kwargs["since"] is not None

    def test_get_audit_entry_structure(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get audit entries should have expected structure."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/audit")

        assert response.status_code == 200
        data = response.json()
        if data["entries"]:
            entry = data["entries"][0]
            expected_fields = [
                "id",
                "agent",
                "task_id",
                "status",
                "duration_seconds",
                "cost_usd",
            ]
            for field in expected_fields:
                assert field in entry


class TestGetAuditStatistics:
    """Tests for GET /projects/{project_name}/audit/statistics endpoint."""

    def test_get_audit_statistics_returns_stats(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get audit statistics should return statistics."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/audit/statistics")

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "success_count" in data
        assert "failed_count" in data

    def test_get_audit_statistics_includes_rates(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get audit statistics should include success rate."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/audit/statistics")

        assert response.status_code == 200
        data = response.json()
        assert "success_rate" in data
        assert "avg_duration_seconds" in data

    def test_get_audit_statistics_includes_cost(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get audit statistics should include cost totals."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/audit/statistics")

        assert response.status_code == 200
        data = response.json()
        assert "total_cost_usd" in data
        assert "total_duration_seconds" in data

    def test_get_audit_statistics_includes_breakdowns(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get audit statistics should include breakdowns by agent and status."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/audit/statistics")

        assert response.status_code == 200
        data = response.json()
        assert "by_agent" in data
        assert "by_status" in data

    def test_get_audit_statistics_with_since_hours(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get audit statistics should filter by time range."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/audit/statistics?since_hours=24")

        assert response.status_code == 200
        mock_audit_storage.get_statistics.assert_called_once()
        call_kwargs = mock_audit_storage.get_statistics.call_args[1]
        assert call_kwargs["since"] is not None
