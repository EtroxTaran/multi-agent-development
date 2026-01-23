"""Tests for project endpoints."""

from pathlib import Path
from unittest.mock import patch


class TestListProjects:
    """Tests for GET /projects endpoint."""

    def test_list_projects_returns_array(self, test_client, mock_project_manager):
        """List projects should return an array."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_projects_returns_project_data(self, test_client, mock_project_manager):
        """List projects should return project data."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-project"
        assert data[0]["has_documents"] is True
        assert data[0]["has_product_spec"] is True

    def test_list_projects_empty(self, test_client, mock_project_manager):
        """List projects should return empty array when no projects."""
        mock_project_manager.list_projects.return_value = []

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects")

        assert response.status_code == 200
        data = response.json()
        assert data == []


class TestGetProject:
    """Tests for GET /projects/{project_name} endpoint."""

    def test_get_project_returns_status(self, test_client, mock_project_manager):
        """Get project should return project status."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects/test-project")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-project"

    def test_get_project_includes_files(self, test_client, mock_project_manager):
        """Get project should include file status."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects/test-project")

        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert "Docs/PRODUCT.md" in data["files"]

    def test_get_project_not_found(self, test_client, mock_project_manager):
        """Get project should return 404 when not found."""
        mock_project_manager.get_project_status.return_value = {"error": "Project not found"}

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/projects/nonexistent")

        assert response.status_code == 404


class TestInitProject:
    """Tests for POST /projects/{project_name}/init endpoint."""

    def test_init_project_success(self, test_client, mock_project_manager):
        """Init project should return success."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.post("/projects/new-project/init")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_init_project_returns_path(self, test_client, mock_project_manager):
        """Init project should return project directory."""
        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.post("/projects/new-project/init")

        assert response.status_code == 200
        data = response.json()
        assert "project_dir" in data

    def test_init_project_failure(self, test_client, mock_project_manager):
        """Init project should return 400 on failure."""
        mock_project_manager.init_project.return_value = {
            "success": False,
            "error": "Project already exists",
        }

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.post("/projects/existing/init")

        assert response.status_code == 400


class TestDeleteProject:
    """Tests for DELETE /projects/{project_name} endpoint."""

    def test_delete_project_workflow_only(
        self, test_client, mock_project_manager, temp_project_dir
    ):
        """Delete project should remove workflow state only by default."""
        mock_project_manager.get_project.return_value = temp_project_dir

        # Create workflow state
        workflow_dir = temp_project_dir / ".workflow"
        workflow_dir.mkdir(exist_ok=True)
        (workflow_dir / "state.json").write_text("{}")

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.delete("/projects/test-project")

        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"].lower()

    def test_delete_project_with_source(self, test_client, mock_project_manager, temp_project_dir):
        """Delete project with remove_source should delete everything."""
        import tempfile

        # Create a fresh temp dir to delete
        fresh_dir = Path(tempfile.mkdtemp()) / "to-delete"
        fresh_dir.mkdir(parents=True)
        (fresh_dir / "test.txt").write_text("test")
        (fresh_dir / ".workflow").mkdir()

        mock_project_manager.get_project.return_value = fresh_dir

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.delete("/projects/test-project?remove_source=true")

        assert response.status_code == 200
        assert not fresh_dir.exists()

    def test_delete_project_not_found(self, test_client, mock_project_manager):
        """Delete project should return 404 when not found."""
        mock_project_manager.get_project.return_value = None

        with patch("main.get_project_manager", return_value=mock_project_manager):
            with patch("main.get_project_dir") as mock_get_dir:
                from fastapi import HTTPException

                mock_get_dir.side_effect = HTTPException(
                    status_code=404, detail="Project not found"
                )
                response = test_client.delete("/projects/nonexistent")

        assert response.status_code == 404
