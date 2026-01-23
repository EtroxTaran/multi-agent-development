"""Tests for budget endpoints."""

from unittest.mock import patch


class TestGetBudget:
    """Tests for GET /projects/{project_name}/budget endpoint."""

    def test_get_budget_returns_status(
        self, test_client, mock_project_manager, mock_budget_manager, temp_project_dir
    ):
        """Get budget should return budget status."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.BudgetManager", return_value=mock_budget_manager):
                response = test_client.get("/projects/test-project/budget")

        assert response.status_code == 200
        data = response.json()
        assert "total_spent_usd" in data
        assert "enabled" in data

    def test_get_budget_includes_spending(
        self, test_client, mock_project_manager, mock_budget_manager, temp_project_dir
    ):
        """Get budget should include spending details."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.BudgetManager", return_value=mock_budget_manager):
                response = test_client.get("/projects/test-project/budget")

        assert response.status_code == 200
        data = response.json()
        assert "project_budget_usd" in data
        assert "project_remaining_usd" in data
        assert "project_used_percent" in data

    def test_get_budget_includes_task_spending(
        self, test_client, mock_project_manager, mock_budget_manager, temp_project_dir
    ):
        """Get budget should include task-level spending."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.BudgetManager", return_value=mock_budget_manager):
                response = test_client.get("/projects/test-project/budget")

        assert response.status_code == 200
        data = response.json()
        assert "task_spent" in data
        assert "task_count" in data

    def test_get_budget_project_not_found(self, test_client, mock_project_manager):
        """Get budget should return 404 when project not found."""
        mock_project_manager.get_project.return_value = None

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_project_dir") as mock_get_dir:
                from fastapi import HTTPException

                mock_get_dir.side_effect = HTTPException(
                    status_code=404, detail="Project not found"
                )
                response = test_client.get("/projects/nonexistent/budget")

        assert response.status_code == 404


class TestGetBudgetReport:
    """Tests for GET /projects/{project_name}/budget/report endpoint."""

    def test_get_budget_report_returns_full_report(
        self, test_client, mock_project_manager, mock_budget_manager, temp_project_dir
    ):
        """Get budget report should return full report."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.BudgetManager", return_value=mock_budget_manager):
                response = test_client.get("/projects/test-project/budget/report")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "task_spending" in data

    def test_get_budget_report_includes_task_breakdown(
        self, test_client, mock_project_manager, mock_budget_manager, temp_project_dir
    ):
        """Get budget report should include task spending breakdown."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.BudgetManager", return_value=mock_budget_manager):
                response = test_client.get("/projects/test-project/budget/report")

        assert response.status_code == 200
        data = response.json()
        task_spending = data["task_spending"]
        assert isinstance(task_spending, list)
        if task_spending:
            assert "task_id" in task_spending[0]
            assert "spent_usd" in task_spending[0]
