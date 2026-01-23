"""Tests for task endpoints."""

from unittest.mock import patch


class TestGetTasks:
    """Tests for GET /projects/{project_name}/tasks endpoint."""

    def test_get_tasks_returns_list(
        self, test_client, mock_project_manager, temp_project_with_state
    ):
        """Get tasks should return task list."""
        mock_project_manager.get_project.return_value = temp_project_with_state

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects/test-project/tasks")

        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert "total" in data
        assert isinstance(data["tasks"], list)

    def test_get_tasks_includes_counts(
        self, test_client, mock_project_manager, temp_project_with_state
    ):
        """Get tasks should include status counts."""
        mock_project_manager.get_project.return_value = temp_project_with_state

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects/test-project/tasks")

        assert response.status_code == 200
        data = response.json()
        assert "completed" in data
        assert "in_progress" in data
        assert "pending" in data
        assert "failed" in data

    def test_get_tasks_empty_when_no_state(
        self, test_client, mock_project_manager, temp_project_dir
    ):
        """Get tasks should return empty list when no workflow state."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects/test-project/tasks")

        assert response.status_code == 200
        data = response.json()
        assert data["tasks"] == []
        assert data["total"] == 0

    def test_get_tasks_project_not_found(self, test_client, mock_project_manager):
        """Get tasks should return 404 when project not found."""
        mock_project_manager.get_project.return_value = None

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_project_dir") as mock_get_dir:
                from fastapi import HTTPException

                mock_get_dir.side_effect = HTTPException(
                    status_code=404, detail="Project not found"
                )
                response = test_client.get("/projects/nonexistent/tasks")

        assert response.status_code == 404

    def test_get_tasks_includes_task_details(
        self, test_client, mock_project_manager, temp_project_with_state
    ):
        """Get tasks should include task details."""
        mock_project_manager.get_project.return_value = temp_project_with_state

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects/test-project/tasks")

        assert response.status_code == 200
        data = response.json()
        tasks = data["tasks"]
        assert len(tasks) > 0

        # Check first task has expected fields
        task = tasks[0]
        assert "id" in task
        assert "title" in task
        assert "status" in task
        assert "priority" in task


class TestGetTask:
    """Tests for GET /projects/{project_name}/tasks/{task_id} endpoint."""

    def test_get_task_success(self, test_client, mock_project_manager, temp_project_with_state):
        """Get task should return task details."""
        mock_project_manager.get_project.return_value = temp_project_with_state

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects/test-project/tasks/T1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "T1"
        assert data["title"] == "Test Task 1"

    def test_get_task_not_found(self, test_client, mock_project_manager, temp_project_with_state):
        """Get task should return 404 when task not found."""
        mock_project_manager.get_project.return_value = temp_project_with_state

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects/test-project/tasks/NONEXISTENT")

        assert response.status_code == 404

    def test_get_task_includes_all_fields(
        self, test_client, mock_project_manager, temp_project_with_state
    ):
        """Get task should include all task fields."""
        mock_project_manager.get_project.return_value = temp_project_with_state

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects/test-project/tasks/T1")

        assert response.status_code == 200
        data = response.json()

        expected_fields = [
            "id",
            "title",
            "description",
            "status",
            "priority",
            "dependencies",
            "files_to_create",
            "files_to_modify",
            "acceptance_criteria",
        ]
        for field in expected_fields:
            assert field in data


class TestGetTaskHistory:
    """Tests for GET /projects/{project_name}/tasks/{task_id}/history endpoint."""

    def test_get_task_history_success(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get task history should return audit entries."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/tasks/T1/history")

        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data

    def test_get_task_history_with_limit(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get task history should respect limit parameter."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/tasks/T1/history?limit=50")

        assert response.status_code == 200
        mock_audit_storage.get_task_history.assert_called_with("T1", limit=50)

    def test_get_task_history_entry_structure(
        self, test_client, mock_project_manager, mock_audit_storage, temp_project_dir
    ):
        """Get task history entries should have expected structure."""
        mock_project_manager.get_project.return_value = temp_project_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_audit_storage", return_value=mock_audit_storage):
                response = test_client.get("/projects/test-project/tasks/T1/history")

        assert response.status_code == 200
        data = response.json()
        if data["entries"]:
            entry = data["entries"][0]
            assert "id" in entry
            assert "agent" in entry
            assert "task_id" in entry
            assert "status" in entry
