"""Tests for gap analysis engine."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.collection.gap_analysis import (
    FEATURE_KEYWORDS,
    TECHNOLOGY_KEYWORDS,
    GapAnalysisEngine,
)
from orchestrator.collection.models import (
    CollectionItem,
    CollectionTags,
    GapAnalysisResult,
    ItemType,
    ProjectRequirements,
)


class TestGapAnalysisEngine:
    """Tests for GapAnalysisEngine."""

    @pytest.fixture
    def mock_service(self):
        """Create a mock collection service."""
        service = MagicMock()
        service.list_items = AsyncMock(return_value=[])
        return service

    @pytest.fixture
    def engine(self, mock_service):
        """Create engine with mock service."""
        return GapAnalysisEngine(collection_service=mock_service)

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory with docs."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Create docs folder
        docs_dir = project_dir / "docs"
        docs_dir.mkdir()

        # Create a product vision document
        (docs_dir / "product-vision.md").write_text(
            """
# Test Project

This is a Python FastAPI backend for user authentication.

## Features
- REST API endpoints
- JWT authentication
- PostgreSQL database
- Docker deployment
        """
        )

        # Create package files
        (project_dir / "pyproject.toml").write_text('[project]\nname = "test"')
        (project_dir / "Dockerfile").write_text("FROM python:3.11")

        return project_dir

    def test_technology_keywords_coverage(self):
        """Test that common technologies are covered."""
        expected_techs = ["python", "typescript", "react", "fastapi", "docker"]
        for tech in expected_techs:
            assert tech in TECHNOLOGY_KEYWORDS, f"Missing technology: {tech}"

    def test_feature_keywords_coverage(self):
        """Test that common features are covered."""
        expected_features = ["auth", "api", "database", "testing", "security"]
        for feature in expected_features:
            assert feature in FEATURE_KEYWORDS, f"Missing feature: {feature}"

    @pytest.mark.asyncio
    async def test_extract_project_requirements(self, engine, temp_project):
        """Test extracting requirements from project docs."""
        reqs = await engine.extract_project_requirements(temp_project, "test-project")

        assert reqs.project_name == "test-project"
        assert "python" in reqs.technologies
        assert "docker" in reqs.technologies
        assert "api" in reqs.features
        assert "auth" in reqs.features

    @pytest.mark.asyncio
    async def test_extract_from_package_files(self, engine, tmp_path):
        """Test technology detection from package files."""
        project = tmp_path / "js-project"
        project.mkdir()
        (project / "package.json").write_text('{"name": "test"}')

        reqs = await engine.extract_project_requirements(project, "js-project")

        assert "javascript" in reqs.technologies or "nodejs" in reqs.technologies

    @pytest.mark.asyncio
    async def test_find_matching_items(self, engine, mock_service):
        """Test finding matching items from collection."""
        # Setup mock items
        mock_items = [
            CollectionItem(
                id="python-standards",
                name="Python Standards",
                item_type=ItemType.RULE,
                category="coding-standards",
                file_path="rules/coding-standards/python.md",
                summary="Python coding standards",
                tags=CollectionTags(technology=["python"], feature=["backend"]),
            ),
            CollectionItem(
                id="security-guardrails",
                name="Security Guardrails",
                item_type=ItemType.RULE,
                category="guardrails",
                file_path="rules/guardrails/security.md",
                summary="Security guardrails",
                tags=CollectionTags(feature=["security"], priority="critical"),
            ),
        ]

        mock_service.list_items = AsyncMock(
            side_effect=[
                [mock_items[0]],  # tech items
                [],  # feature items
                [mock_items[1]],  # critical items
            ]
        )

        reqs = ProjectRequirements(
            project_name="test",
            project_path=Path("/tmp/test"),
            technologies=["python"],
            features=["auth"],
        )

        items = await engine.find_matching_items(reqs)

        assert len(items) >= 1
        assert mock_service.list_items.call_count >= 1

    @pytest.mark.asyncio
    async def test_identify_gaps(self, engine, mock_service):
        """Test identifying gaps in coverage."""
        reqs = ProjectRequirements(
            project_name="test",
            project_path=Path("/tmp/test"),
            technologies=["python", "graphql"],  # graphql is unlikely to be covered
            features=["auth", "realtime"],  # realtime is unlikely to be covered
        )

        # Items only cover python and auth
        available_items = [
            CollectionItem(
                id="python-standards",
                name="Python Standards",
                item_type=ItemType.RULE,
                category="standards",
                file_path="rules/python.md",
                summary="Python standards",
                tags=CollectionTags(technology=["python"], feature=["auth"]),
            ),
        ]

        gaps = await engine.identify_gaps(reqs, available_items)

        # Should find gaps for graphql and realtime
        gap_values = [g.value for g in gaps]
        assert "graphql" in gap_values
        assert "realtime" in gap_values

    @pytest.mark.asyncio
    async def test_suggest_research_queries(self, engine):
        """Test generating research queries for gaps."""
        from orchestrator.collection.models import GapItem

        gaps = [
            GapItem(
                gap_type="technology",
                value="graphql",
                recommended_research="graphql best practices",
            ),
            GapItem(
                gap_type="feature",
                value="caching",
                recommended_research="caching patterns",
            ),
        ]

        queries = await engine.suggest_research_queries(gaps)

        assert len(queries) >= 2
        assert any("graphql" in q.lower() for q in queries)
        assert any("caching" in q.lower() for q in queries)

    @pytest.mark.asyncio
    async def test_full_analysis_flow(self, engine, temp_project, mock_service):
        """Test complete analysis workflow."""
        mock_service.list_items = AsyncMock(return_value=[])

        result = await engine.analyze_project(temp_project, "test-project")

        assert isinstance(result, GapAnalysisResult)
        assert result.project_name == "test-project"
        assert result.requirements is not None
        assert result.analyzed_at is not None
