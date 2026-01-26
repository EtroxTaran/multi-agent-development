"""Tests for the guardrails_agent node.

Tests the LangGraph node that applies guardrails at the
start of a workflow.
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.langgraph.nodes.guardrails_agent import guardrails_agent_node


class TestGuardrailsAgentNode:
    """Test suite for the guardrails_agent_node."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with PRODUCT.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            # Create a minimal PRODUCT.md
            (project_dir / "PRODUCT.md").write_text(
                """# Test Project

## Features
- Authentication
- API endpoints

## Tech Stack
- Python
- FastAPI
"""
            )
            yield project_dir

    @pytest.fixture
    def minimal_workflow_state(self, temp_project_dir) -> dict:
        """Create a minimal valid workflow state."""
        return {
            "project_name": "test-project",
            "project_dir": str(temp_project_dir),
            "current_phase": 0,
            "phase_status": {},
            "errors": [],
            "next_decision": "continue",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    @pytest.mark.asyncio
    async def test_node_returns_state_updates(self, minimal_workflow_state):
        """Test that node returns proper state updates."""
        # Patch at the source modules since imports are inside the function
        with patch("orchestrator.collection.gap_analysis.GapAnalysisEngine") as MockEngine, patch(
            "orchestrator.collection.project_setup.ProjectGuardrailsSetup"
        ), patch("orchestrator.collection.service.CollectionService"), patch(
            "orchestrator.db.connection.get_connection"
        ):
            # Setup mock
            mock_gap_result = MagicMock()
            mock_gap_result.matching_items = []
            mock_gap_result.gaps = []
            mock_gap_result.requirements = MagicMock()
            mock_gap_result.requirements.technologies = set()
            mock_gap_result.requirements.features = set()

            MockEngine.return_value.analyze_project = AsyncMock(return_value=mock_gap_result)

            result = await guardrails_agent_node(minimal_workflow_state)

            assert isinstance(result, dict)
            assert "next_decision" in result
            assert result["next_decision"] == "continue"

    @pytest.mark.asyncio
    async def test_node_returns_guardrails_summary(self, minimal_workflow_state):
        """Test that node returns guardrails_summary in state."""
        with patch("orchestrator.collection.gap_analysis.GapAnalysisEngine") as MockEngine, patch(
            "orchestrator.collection.project_setup.ProjectGuardrailsSetup"
        ) as MockSetup, patch("orchestrator.collection.service.CollectionService"), patch(
            "orchestrator.db.connection.get_connection"
        ):
            mock_gap_result = MagicMock()
            mock_gap_result.matching_items = []
            mock_gap_result.gaps = []
            mock_gap_result.requirements = MagicMock()
            mock_gap_result.requirements.technologies = {"python"}
            mock_gap_result.requirements.features = {"api"}

            MockEngine.return_value.analyze_project = AsyncMock(return_value=mock_gap_result)
            MockSetup.return_value.update_agent_files = AsyncMock()

            result = await guardrails_agent_node(minimal_workflow_state)

            assert "guardrails_summary" in result
            assert isinstance(result["guardrails_summary"], dict)
            assert "items_applied" in result["guardrails_summary"]

    @pytest.mark.asyncio
    async def test_node_returns_guardrails_gaps(self, minimal_workflow_state):
        """Test that node returns guardrails_gaps in state."""
        with patch("orchestrator.collection.gap_analysis.GapAnalysisEngine") as MockEngine, patch(
            "orchestrator.collection.project_setup.ProjectGuardrailsSetup"
        ) as MockSetup, patch("orchestrator.collection.service.CollectionService"), patch(
            "orchestrator.db.connection.get_connection"
        ):
            # Create mock gap
            mock_gap = MagicMock()
            mock_gap.gap_type = "technology"
            mock_gap.value = "redis"
            mock_gap.recommended_research = "Research Redis caching"

            mock_gap_result = MagicMock()
            mock_gap_result.matching_items = []
            mock_gap_result.gaps = [mock_gap]
            mock_gap_result.requirements = MagicMock()
            mock_gap_result.requirements.technologies = {"python", "redis"}
            mock_gap_result.requirements.features = set()

            MockEngine.return_value.analyze_project = AsyncMock(return_value=mock_gap_result)
            MockSetup.return_value.update_agent_files = AsyncMock()

            result = await guardrails_agent_node(minimal_workflow_state)

            assert "guardrails_gaps" in result
            assert isinstance(result["guardrails_gaps"], list)
            assert len(result["guardrails_gaps"]) == 1
            assert result["guardrails_gaps"][0]["type"] == "technology"

    @pytest.mark.asyncio
    async def test_node_handles_errors_gracefully(self, minimal_workflow_state):
        """Test graceful handling of errors."""
        with patch("orchestrator.collection.gap_analysis.GapAnalysisEngine") as MockEngine, patch(
            "orchestrator.collection.project_setup.ProjectGuardrailsSetup"
        ), patch("orchestrator.collection.service.CollectionService"):
            MockEngine.return_value.analyze_project = AsyncMock(
                side_effect=Exception("Gap analysis failed")
            )

            # Should not raise, should handle gracefully
            result = await guardrails_agent_node(minimal_workflow_state)

            assert isinstance(result, dict)
            assert result["next_decision"] == "continue"  # Workflow continues
            assert "guardrails_summary" in result
            assert "error" in result["guardrails_summary"]

    @pytest.mark.asyncio
    async def test_node_applies_matching_items(self, minimal_workflow_state):
        """Test that matching items are passed to project setup."""
        with patch("orchestrator.collection.gap_analysis.GapAnalysisEngine") as MockEngine, patch(
            "orchestrator.collection.project_setup.ProjectGuardrailsSetup"
        ) as MockSetup, patch("orchestrator.collection.service.CollectionService"), patch(
            "orchestrator.db.connection.get_connection"
        ):
            # Create mock item
            mock_item = MagicMock()
            mock_item.id = "item1"
            mock_item.name = "security-rules"
            mock_item.item_type = MagicMock(value="rule")
            mock_item.version = "1.0.0"

            mock_gap_result = MagicMock()
            mock_gap_result.matching_items = [mock_item]
            mock_gap_result.gaps = []
            mock_gap_result.requirements = MagicMock()
            mock_gap_result.requirements.technologies = {"python"}
            mock_gap_result.requirements.features = set()

            MockEngine.return_value.analyze_project = AsyncMock(return_value=mock_gap_result)

            mock_apply_result = MagicMock()
            mock_apply_result.items_applied = ["item1"]
            mock_apply_result.files_created = ["file.md"]
            mock_apply_result.cursor_rules_created = ["rule.mdc"]
            mock_apply_result.errors = []

            MockSetup.return_value.apply_guardrails = AsyncMock(return_value=mock_apply_result)
            MockSetup.return_value.update_agent_files = AsyncMock()

            _result = await guardrails_agent_node(minimal_workflow_state)

            # Verify apply_guardrails was called
            MockSetup.return_value.apply_guardrails.assert_called_once()


class TestGuardrailsAgentNodeEdgeCases:
    """Edge case tests for guardrails_agent_node."""

    @pytest.fixture
    def minimal_state(self) -> dict:
        """Create minimal state for edge case testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield {
                "project_name": "edge-test",
                "project_dir": tmpdir,
                "current_phase": 0,
                "phase_status": {},
                "errors": [],
                "next_decision": "continue",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

    @pytest.mark.asyncio
    async def test_handles_no_matching_items(self, minimal_state):
        """Test handling when no collection items match."""
        with patch("orchestrator.collection.gap_analysis.GapAnalysisEngine") as MockEngine, patch(
            "orchestrator.collection.project_setup.ProjectGuardrailsSetup"
        ) as MockSetup, patch("orchestrator.collection.service.CollectionService"), patch(
            "orchestrator.db.connection.get_connection"
        ):
            mock_gap_result = MagicMock()
            mock_gap_result.matching_items = []  # No matches
            mock_gap_result.gaps = [
                MagicMock(
                    gap_type="technology",
                    value="obscure-lang",
                    recommended_research="Research obscure patterns",
                )
            ]
            mock_gap_result.requirements = MagicMock()
            mock_gap_result.requirements.technologies = {"obscure-lang"}
            mock_gap_result.requirements.features = set()

            MockEngine.return_value.analyze_project = AsyncMock(return_value=mock_gap_result)
            MockSetup.return_value.update_agent_files = AsyncMock()

            result = await guardrails_agent_node(minimal_state)

            assert isinstance(result, dict)
            assert result["next_decision"] == "continue"
            assert result["guardrails_summary"]["items_applied"] == 0

    @pytest.mark.asyncio
    async def test_continues_workflow_on_db_error(self, minimal_state):
        """Test that DB errors don't block workflow."""
        with patch("orchestrator.collection.gap_analysis.GapAnalysisEngine") as MockEngine, patch(
            "orchestrator.collection.project_setup.ProjectGuardrailsSetup"
        ) as MockSetup, patch("orchestrator.collection.service.CollectionService"), patch(
            "orchestrator.db.connection.get_connection",
            side_effect=Exception("DB connection failed"),
        ):
            # Create mock item
            mock_item = MagicMock()
            mock_item.id = "item1"
            mock_item.item_type = MagicMock(value="rule")
            mock_item.version = "1.0.0"

            mock_gap_result = MagicMock()
            mock_gap_result.matching_items = [mock_item]
            mock_gap_result.gaps = []
            mock_gap_result.requirements = MagicMock()
            mock_gap_result.requirements.technologies = set()
            mock_gap_result.requirements.features = set()

            MockEngine.return_value.analyze_project = AsyncMock(return_value=mock_gap_result)

            mock_apply_result = MagicMock()
            mock_apply_result.items_applied = ["item1"]
            mock_apply_result.files_created = []
            mock_apply_result.cursor_rules_created = []
            mock_apply_result.errors = []

            MockSetup.return_value.apply_guardrails = AsyncMock(return_value=mock_apply_result)
            MockSetup.return_value.update_agent_files = AsyncMock()

            result = await guardrails_agent_node(minimal_state)

            # Workflow should continue despite DB error
            assert result["next_decision"] == "continue"
