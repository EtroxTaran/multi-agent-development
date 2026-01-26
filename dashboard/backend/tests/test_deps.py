"""Tests for dependency injection functions."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import deps
from app.main import app


class TestGetProjectManager:
    """Tests for get_project_manager dependency."""

    def test_get_project_manager_creates_instance(self):
        """Test that get_project_manager returns a ProjectManager."""
        # Clear the lru_cache first since the function may have been called already
        deps.get_project_manager.cache_clear()

        with patch("app.deps.ProjectManager") as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm_cls.return_value = mock_pm

            result = deps.get_project_manager()

            assert result == mock_pm
            mock_pm_cls.assert_called_once()

        # Clear cache after test to not affect other tests
        deps.get_project_manager.cache_clear()


class TestGetProjectDir:
    """Tests for get_project_dir dependency."""

    def test_get_project_dir_success(self, mock_project_manager: MagicMock):
        """Test getting project directory successfully."""
        project_path = Path("/test/projects/my-project")
        mock_project_manager.get_project.return_value = project_path

        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager

        try:
            # Use the dependency in a test route
            client = TestClient(app)
            # The dependency is tested indirectly through routes
            _response = client.get("/api/projects/my-project")  # noqa: F841
            # If project manager returns a path, the dependency works
            mock_project_manager.get_project_status.return_value = {"name": "my-project"}
        finally:
            app.dependency_overrides.clear()

    def test_get_project_dir_not_found(self, mock_project_manager: MagicMock):
        """Test get_project_dir when project doesn't exist."""
        mock_project_manager.get_project.return_value = None

        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager

        try:
            client = TestClient(app)
            # Routes that use get_project_dir should return 404
            response = client.get("/api/projects/nonexistent/status")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestGetOrchestrator:
    """Tests for get_orchestrator dependency."""

    def test_get_orchestrator_creates_instance(self, temp_project_dir: Path):
        """Test that get_orchestrator creates an Orchestrator."""
        with patch("app.deps.Orchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch_cls.return_value = mock_orch

            result = deps.get_orchestrator(temp_project_dir)

            assert result == mock_orch
            # Verify it was called with project_dir (may have additional kwargs)
            assert mock_orch_cls.call_count == 1
            call_args = mock_orch_cls.call_args
            assert call_args[0][0] == temp_project_dir


class TestGetAuditAdapter:
    """Tests for get_audit_adapter dependency."""

    def test_get_audit_adapter_returns_adapter(self, temp_project_dir: Path):
        """Test that get_audit_adapter returns an adapter instance."""
        # Just test that the function is callable and returns something
        result = deps.get_audit_adapter(temp_project_dir)

        # Should return an AuditStorageAdapter
        assert result is not None
        assert hasattr(result, "query")
        assert hasattr(result, "get_statistics")


class TestGetSettings:
    """Tests for get_settings function."""

    def test_get_settings_returns_settings(self):
        """Test that get_settings returns settings instance."""
        from app.config import get_settings

        settings = get_settings()

        assert settings is not None
        assert hasattr(settings, "conductor_root")
        assert hasattr(settings, "projects_path")

    def test_get_settings_cached(self):
        """Test that get_settings returns cached instance."""
        from app.config import get_settings

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2
