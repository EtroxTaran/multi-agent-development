"""Tests for fixer research node."""

import asyncio
import sys
from unittest.mock import MagicMock

# Create a mock package for langgraph
mock_langgraph = MagicMock()
mock_checkpoint = MagicMock()
mock_graph = MagicMock()
mock_types = MagicMock()

# Setup the module structure
sys.modules["langgraph"] = mock_langgraph
sys.modules["langgraph.checkpoint"] = mock_checkpoint
sys.modules["langgraph.checkpoint.base"] = mock_checkpoint
sys.modules["langgraph.checkpoint.memory"] = mock_checkpoint
sys.modules["langgraph.graph"] = mock_graph
sys.modules["langgraph.types"] = mock_types

from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.fixer.diagnosis import DiagnosisConfidence, DiagnosisResult, RootCause
from orchestrator.fixer.triage import ErrorCategory, FixerError
from orchestrator.langgraph.nodes.fixer_research import fixer_research_node


@pytest.fixture
def mock_researcher():
    agent = AsyncMock()
    # Mock successful research response
    agent.run_iteration.return_value.output = """
```json
{
    "strategy_name": "api_fix",
    "confidence": 0.9,
    "actions": [
        {
            "type": "modify_file",
            "target": "src/main.py",
            "description": "Update API call",
            "content": "new_code",
            "verify_command": "pytest"
        }
    ]
}
```
"""
    return agent


def test_fixer_research_node_success(tmp_path, mock_researcher):
    # Setup state
    error = FixerError(error_id="e1", error_type="Error", message="msg", source="test")
    diagnosis = DiagnosisResult(
        error=error,
        root_cause=RootCause.API_MISUSE,
        confidence=DiagnosisConfidence.HIGH,
        category=ErrorCategory.UNKNOWN,
    )

    state = {
        "project_dir": str(tmp_path),
        "current_fix_attempt": {"diagnosis": diagnosis.to_dict()},
    }

    async def run_test():
        with patch(
            "orchestrator.langgraph.nodes.fixer_research.create_adapter",
            return_value=mock_researcher,
        ):
            result = await fixer_research_node(state)

        assert result["next_decision"] == "validate"
        assert "plan" in result["current_fix_attempt"]
        plan = result["current_fix_attempt"]["plan"]
        assert plan["strategy_name"] == "api_fix"
        assert len(plan["actions"]) == 1

    asyncio.run(run_test())


def test_fixer_research_node_no_diagnosis(tmp_path):
    state = {"project_dir": str(tmp_path), "current_fix_attempt": {}}  # Missing diagnosis

    async def run_test():
        result = await fixer_research_node(state)
        assert result["next_decision"] == "escalate"

    asyncio.run(run_test())
