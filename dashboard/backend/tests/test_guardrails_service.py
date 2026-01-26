"""Tests for GuardrailsService."""

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.guardrails_service import (
    GuardrailRecord,
    GuardrailsService,
    ToggleResult,
    get_guardrails_service,
)


def make_mock_connection(mock_conn: AsyncMock):
    """Create an async context manager factory that yields mock_conn.

    This is needed because get_connection is an @asynccontextmanager,
    not a class with __aenter__/__aexit__.
    """

    @asynccontextmanager
    async def mock_get_connection(project_name):
        yield mock_conn

    return mock_get_connection


class TestGuardrailRecord:
    """Tests for GuardrailRecord dataclass."""

    def test_defaults(self):
        """Should have sensible defaults."""
        record = GuardrailRecord(item_id="test", item_type="rule")
        assert record.enabled is True
        assert record.delivery_method == "file"
        assert record.version_applied == 1
        assert record.file_path is None


class TestGuardrailsService:
    """Tests for GuardrailsService."""

    @pytest.fixture
    def service(self, tmp_path: Path):
        """Create service with temp directory."""
        return GuardrailsService(tmp_path)

    @pytest.fixture
    def project_dir(self, tmp_path: Path) -> Path:
        """Create a test project directory."""
        project = tmp_path / "test-project"
        project.mkdir()

        # Create conductor directory with manifest
        conductor = project / ".conductor"
        conductor.mkdir()

        (conductor / "manifest.json").write_text(
            """
            {
                "items": [
                    {
                        "id": "rule-1",
                        "type": "rule",
                        "enabled": true,
                        "delivery_method": "file",
                        "version": 1,
                        "applied_at": "2024-01-01",
                        "file_path": ".conductor/rules/rule-1.md"
                    }
                ]
            }
            """
        )

        # Create the rule file
        rules = conductor / "rules"
        rules.mkdir()
        (rules / "rule-1.md").write_text("# Rule 1\n\nThis is a test rule.")

        return project

    @pytest.mark.asyncio
    async def test_list_project_guardrails_from_manifest(
        self, service: GuardrailsService, project_dir: Path
    ):
        """Should list guardrails from manifest when DB not available."""
        with patch(
            "orchestrator.db.connection.get_connection",
            side_effect=Exception("No DB"),
        ):
            guardrails = await service.list_project_guardrails("test-project", project_dir)

            assert len(guardrails) == 1
            assert guardrails[0].item_id == "rule-1"
            assert guardrails[0].item_type == "rule"
            assert guardrails[0].enabled is True

    @pytest.mark.asyncio
    async def test_list_project_guardrails_empty(self, service: GuardrailsService, tmp_path: Path):
        """Should return empty list for project without guardrails."""
        empty_project = tmp_path / "empty-project"
        empty_project.mkdir()

        with patch(
            "orchestrator.db.connection.get_connection",
            side_effect=Exception("No DB"),
        ):
            guardrails = await service.list_project_guardrails("empty-project", empty_project)
            assert guardrails == []

    @pytest.mark.asyncio
    async def test_toggle_guardrail_success(self, service: GuardrailsService):
        """Should toggle guardrail and return new state."""
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [{"enabled": True}],  # First query: find record
                None,  # Second query: update
            ]
        )

        with patch(
            "orchestrator.db.connection.get_connection",
            make_mock_connection(mock_conn),
        ):
            result = await service.toggle_guardrail("test-project", "rule-1")

            assert isinstance(result, ToggleResult)
            assert result.item_id == "rule-1"
            assert result.enabled is False  # Toggled from True

    @pytest.mark.asyncio
    async def test_toggle_guardrail_not_found(self, service: GuardrailsService):
        """Should raise error for non-existent guardrail."""
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[])  # Empty result

        with patch(
            "orchestrator.db.connection.get_connection",
            make_mock_connection(mock_conn),
        ):
            with pytest.raises(ValueError) as exc_info:
                await service.toggle_guardrail("test-project", "nonexistent")

            assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_promote_to_global_success(self, service: GuardrailsService, project_dir: Path):
        """Should promote guardrail to global collection."""
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [
                    {
                        "file_path": ".conductor/rules/rule-1.md",
                        "item_type": "rule",
                    }
                ],  # Find record
                None,  # Update promoted
            ]
        )

        with patch(
            "orchestrator.db.connection.get_connection",
            make_mock_connection(mock_conn),
        ):
            # Mock the CollectionService
            with patch("orchestrator.collection.service.CollectionService") as mock_cs_cls:
                mock_cs = AsyncMock()
                mock_cs_cls.return_value = mock_cs

                result = await service.promote_to_global("test-project", project_dir, "rule-1")

                assert result.promoted is True
                assert result.item_id == "rule-1"
                assert result.source_project == "test-project"

    @pytest.mark.asyncio
    async def test_promote_to_global_not_found(self, service: GuardrailsService, project_dir: Path):
        """Should fail if guardrail not found."""
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[])  # Empty result

        with patch(
            "orchestrator.db.connection.get_connection",
            make_mock_connection(mock_conn),
        ):
            result = await service.promote_to_global("test-project", project_dir, "nonexistent")

            assert result.promoted is False
            assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_promote_to_global_no_file_path(
        self, service: GuardrailsService, project_dir: Path
    ):
        """Should fail if guardrail has no file path."""
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[{"file_path": None}])  # No file path

        with patch(
            "orchestrator.db.connection.get_connection",
            make_mock_connection(mock_conn),
        ):
            result = await service.promote_to_global("test-project", project_dir, "rule-1")

            assert result.promoted is False
            assert "without file path" in result.message.lower()


class TestGetGuardrailsService:
    """Tests for get_guardrails_service helper."""

    def test_returns_instance(self):
        """Should return a GuardrailsService instance."""
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(conductor_root=Path("/tmp/conductor"))

            # Clear the singleton for testing
            import app.services.guardrails_service as gs_module

            gs_module._guardrails_service = None

            service = get_guardrails_service()
            assert isinstance(service, GuardrailsService)
