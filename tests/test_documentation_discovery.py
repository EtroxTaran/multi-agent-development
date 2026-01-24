"""Tests for documentation discovery system.

Tests for DocumentationScanner and documentation_discovery_node.
"""

import json
import tempfile
from pathlib import Path

import pytest


class TestDocumentationScanner:
    """Test DocumentationScanner class."""

    def test_discover_docs_folder(self):
        """Test discovering documentation from docs/ folder."""
        from orchestrator.validators.documentation_discovery import DocumentationScanner

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create docs structure
            docs_dir = project_dir / "docs" / "product"
            docs_dir.mkdir(parents=True)

            # Create overview file
            overview = docs_dir / "overview.md"
            overview.write_text(
                """# Product Vision

## Overview
This is our product vision for the application.

## Requirements
- [ ] User authentication
- [ ] Data storage
- [ ] API endpoints
"""
            )

            # Create architecture file
            design_dir = project_dir / "docs" / "design"
            design_dir.mkdir(parents=True)
            arch = design_dir / "architecture.md"
            arch.write_text(
                """# System Architecture

## Overview
The system uses a microservices architecture.

## Components
- API Gateway
- Auth Service
- Data Service
"""
            )

            scanner = DocumentationScanner()
            result = scanner.discover(project_dir)

            assert result.is_valid
            assert len(result.documents) >= 2
            assert "docs" in result.source_folders[0]
            assert result.score >= 4.0

    def test_discover_documents_folder(self):
        """Test discovering documentation from Documents/ folder."""
        from orchestrator.validators.documentation_discovery import DocumentationScanner

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create Documents structure
            docs_dir = project_dir / "Documents"
            docs_dir.mkdir(parents=True)

            # Create product file
            product = docs_dir / "product.md"
            product.write_text(
                """# Product Requirements

## Vision
Our product helps developers work faster.

## Acceptance Criteria
- [ ] Must support multiple languages
- [ ] Must integrate with CI/CD
"""
            )

            scanner = DocumentationScanner()
            result = scanner.discover(project_dir)

            # Result may not be valid due to low score, but should have documents
            assert len(result.documents) >= 1
            assert "Documents" in result.source_folders[0]

    def test_fallback_to_product_md(self):
        """Test fallback to PRODUCT.md when no docs folder exists."""
        from orchestrator.validators.documentation_discovery import DocumentationScanner

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Only create PRODUCT.md
            product_md = project_dir / "PRODUCT.md"
            product_md.write_text(
                """# My Product

## Vision
A tool for testing.

## Requirements
- [ ] Feature A
- [ ] Feature B
- [ ] Feature C
"""
            )

            scanner = DocumentationScanner()
            result = scanner.discover(project_dir)

            # May not meet is_valid threshold, but should have content
            assert "PRODUCT.md" in result.source_folders[0]
            assert len(result.documents) == 1

    def test_no_documentation_found(self):
        """Test behavior when no documentation is found."""
        from orchestrator.validators.documentation_discovery import DocumentationScanner

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            # Empty project - no docs

            scanner = DocumentationScanner()
            result = scanner.discover(project_dir)

            assert not result.is_valid
            assert result.score == 0.0
            assert len(result.issues) > 0

    def test_scoring_completeness(self):
        """Test documentation completeness scoring."""
        from orchestrator.validators.documentation_discovery import DocumentationScanner

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create comprehensive docs structure
            for folder in ["docs/product", "docs/design", "docs/guides"]:
                (project_dir / folder).mkdir(parents=True)

            # Product vision
            (project_dir / "docs/product/overview.md").write_text(
                """# Product Vision
Our product enables AI-assisted development workflows.
"""
            )

            # Architecture
            (project_dir / "docs/design/architecture.md").write_text(
                """# System Architecture
## Overview
Clean architecture with domain layer.
"""
            )

            # Guide
            (project_dir / "docs/guides/quick-start.md").write_text(
                """# Quick Start
1. Install dependencies
2. Run the app
"""
            )

            # Requirements with acceptance criteria
            (project_dir / "docs/product/requirements.md").write_text(
                """# Requirements
## Acceptance Criteria
- [ ] Users can log in
- [ ] Users can create projects
- [ ] Users can run workflows
"""
            )

            scanner = DocumentationScanner()
            result = scanner.discover(project_dir)

            # Should have high score with all components
            assert result.is_valid
            assert result.score >= 6.0
            assert result.product_vision is not None
            assert result.architecture_summary is not None


class TestDocumentationDiscoveryNode:
    """Test documentation_discovery_node workflow node."""

    @pytest.mark.asyncio
    async def test_node_success_with_docs(self):
        """Test node succeeds with valid documentation."""
        from orchestrator.langgraph.nodes.documentation_discovery import (
            documentation_discovery_node,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create docs
            docs_dir = project_dir / "docs" / "product"
            docs_dir.mkdir(parents=True)
            (docs_dir / "overview.md").write_text(
                """# Product Vision
This is the product vision.

## Requirements
- [ ] Requirement 1
- [ ] Requirement 2
"""
            )

            # Create .workflow directory
            workflow_dir = project_dir / ".workflow" / "phases" / "0"
            workflow_dir.mkdir(parents=True)

            # Create config
            config = project_dir / ".project-config.json"
            config.write_text(
                json.dumps({"workflow": {"features": {"documentation_discovery": True}}})
            )

            state = {
                "project_dir": str(project_dir),
                "project_name": "test-project",
            }

            result = await documentation_discovery_node(state)

            assert result.get("next_decision") == "continue"
            assert result.get("documentation_discovery") is not None

    @pytest.mark.asyncio
    async def test_node_disabled_by_config(self):
        """Test node is skipped when disabled in config."""
        from orchestrator.langgraph.nodes.documentation_discovery import (
            documentation_discovery_node,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create config with feature disabled
            config = project_dir / ".project-config.json"
            config.write_text(
                json.dumps(
                    {
                        "workflow": {
                            "features": {
                                "documentation_discovery": False,
                                "product_validation": False,
                            }
                        }
                    }
                )
            )

            state = {
                "project_dir": str(project_dir),
                "project_name": "test-project",
            }

            result = await documentation_discovery_node(state)

            assert result.get("next_decision") == "continue"


class TestDocumentationDiscoveryRouter:
    """Test documentation_discovery_router function."""

    def test_router_continue(self):
        """Test router routes to planning on continue."""
        from orchestrator.langgraph.routers.general import documentation_discovery_router

        state = {"next_decision": "continue"}
        result = documentation_discovery_router(state)
        assert result == "planning"

    def test_router_escalate(self):
        """Test router routes to escalation."""
        from orchestrator.langgraph.routers.general import documentation_discovery_router

        state = {"next_decision": "escalate"}
        result = documentation_discovery_router(state)
        assert result == "human_escalation"

    def test_router_abort(self):
        """Test router routes to end on abort."""
        from orchestrator.langgraph.routers.general import documentation_discovery_router

        state = {"next_decision": "abort"}
        result = documentation_discovery_router(state)
        assert result == "__end__"
