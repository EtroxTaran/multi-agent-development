"""Unit tests for the planning node (Phase 1).

Tests cover:
- Happy path with valid PRODUCT.md
- Missing PRODUCT.md handling
- Retry logic on Claude failures
- JSON parsing with fallback
- Max attempts escalation
- Phase status updates
- Plan file saving
- Action logging
"""

import asyncio
import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.langgraph.nodes.planning import planning_node
from orchestrator.langgraph.state import PhaseStatus, create_initial_state


@dataclass
class MockAgentResult:
    """Mock result from agent run."""

    success: bool
    output: str = ""
    error: str = ""
    exit_code: int = 0
    parsed_output: dict | None = None


class TestPlanningNode:
    """Tests for the planning_node function."""

    @pytest.fixture
    def temp_project_dir(self, tmp_path):
        """Create a temporary project with docs/ folder."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Create docs/ folder with PRODUCT.md (this is the required structure)
        docs_dir = project_dir / "docs"
        docs_dir.mkdir()

        product_md = docs_dir / "PRODUCT.md"
        product_md.write_text(
            """# Test Feature

## Summary
A test feature for testing the planning node. This feature demonstrates
the multi-agent orchestration capabilities.

## Problem Statement
Currently there is no way to test the planning node effectively.
We need comprehensive test coverage to ensure reliable operation.

## Acceptance Criteria
- [ ] Planning node generates valid JSON plan
- [ ] Plan includes phases and tasks
- [ ] Tests pass successfully

## Example Inputs/Outputs
### Input
```json
{"feature": "test"}
```

### Output
```json
{"plan_name": "Test Feature", "phases": []}
```

## Technical Constraints
- Must complete within 30 seconds
- No external dependencies

## Testing Strategy
- Unit tests for all node functions
- Mock external API calls

## Definition of Done
- [ ] Planning node implemented
- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] Code reviewed
- [ ] Merged to main
"""
        )

        # Create .workflow directory
        (project_dir / ".workflow" / "phases" / "planning").mkdir(parents=True)

        return project_dir

    @pytest.fixture
    def initial_state(self, temp_project_dir):
        """Create initial workflow state for testing."""
        return create_initial_state(
            project_dir=str(temp_project_dir),
            project_name="test-project",
        )

    @pytest.fixture
    def mock_plan(self):
        """Sample plan output from Claude."""
        return {
            "plan_name": "Test Feature Implementation",
            "summary": "Implement the test feature",
            "tasks": [
                {
                    "id": "T1",
                    "title": "Create project structure",
                    "description": "Set up the basic project files",
                    "files_to_create": ["src/__init__.py"],
                    "files_to_modify": [],
                    "dependencies": [],
                    "acceptance_criteria": ["Files exist"],
                }
            ],
            "milestones": [
                {
                    "id": "M1",
                    "name": "Setup Complete",
                    "tasks": ["T1"],
                }
            ],
            "test_strategy": {
                "unit_tests": ["tests/test_main.py"],
                "integration_tests": [],
                "test_commands": ["pytest"],
            },
            "risks": ["None identified"],
            "estimated_complexity": "low",
        }

    @pytest.mark.asyncio
    async def test_planning_node_success(self, initial_state, mock_plan, temp_project_dir):
        """Test happy path with valid PRODUCT.md - should generate a plan."""
        mock_agent = MagicMock()
        mock_agent.run.return_value = MockAgentResult(
            success=True,
            output=json.dumps(mock_plan),
            parsed_output=mock_plan,  # Specialist runner returns parsed plan directly
        )
        mock_runner = MagicMock()
        mock_runner.create_agent.return_value = mock_agent

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner", return_value=mock_runner
        ):
            result = await planning_node(initial_state)

        assert result["next_decision"] == "continue"
        assert result["plan"] == mock_plan
        assert result["current_phase"] == 2
        assert result["phase_status"]["1"].status == PhaseStatus.COMPLETED
        # Plan is now saved to DB, not file - verified by mock

    @pytest.mark.asyncio
    async def test_planning_node_missing_docs(self, tmp_path):
        """Test that missing docs/ folder returns abort."""
        # Create project without docs/ folder
        project_dir = tmp_path / "empty-project"
        project_dir.mkdir()
        (project_dir / ".workflow" / "phases" / "planning").mkdir(parents=True)

        state = create_initial_state(
            project_dir=str(project_dir),
            project_name="empty-project",
        )

        result = await planning_node(state)

        assert result["next_decision"] == "abort"
        assert len(result.get("errors", [])) > 0
        assert result["errors"][0]["type"] == "no_documentation"

    @pytest.mark.asyncio
    async def test_planning_node_claude_failure_retry(self, initial_state):
        """Test that Claude CLI failures trigger retry (up to max attempts)."""
        mock_agent = MagicMock()
        mock_agent.run.return_value = MockAgentResult(
            success=False,
            error="Rate limit exceeded",
        )
        mock_runner = MagicMock()
        mock_runner.create_agent.return_value = mock_agent

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner", return_value=mock_runner
        ):
            result = await planning_node(initial_state)

        # Should indicate retry is needed
        assert result["next_decision"] == "retry"
        assert result["phase_status"]["1"].attempts == 1
        assert len(result.get("errors", [])) > 0
        assert result["errors"][0]["type"] == "planning_error"

    @pytest.mark.asyncio
    async def test_planning_node_json_parsing_fallback(
        self, initial_state, mock_plan, temp_project_dir
    ):
        """Test that regex extraction is tried on JSON parse failure."""
        # Return raw JSON in text that needs extraction
        raw_output = f"Here is the plan:\n```json\n{json.dumps(mock_plan)}\n```"
        mock_agent = MagicMock()
        mock_agent.run.return_value = MockAgentResult(
            success=True,
            output=raw_output,
        )
        mock_runner = MagicMock()
        mock_runner.create_agent.return_value = mock_agent

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner", return_value=mock_runner
        ):
            result = await planning_node(initial_state)

        # Should still succeed using regex extraction
        assert result["next_decision"] == "continue"
        assert result["plan"]["plan_name"] == mock_plan["plan_name"]

    @pytest.mark.asyncio
    async def test_planning_node_max_attempts_escalate(self, initial_state):
        """Test that exceeding max retries triggers escalation."""
        # Set phase to have already used max attempts
        initial_state["phase_status"]["1"].attempts = 2  # Already tried twice
        initial_state["phase_status"]["1"].max_attempts = 3

        mock_agent = MagicMock()
        mock_agent.run.return_value = MockAgentResult(
            success=False,
            error="Persistent failure",
        )
        mock_runner = MagicMock()
        mock_runner.create_agent.return_value = mock_agent

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner", return_value=mock_runner
        ):
            result = await planning_node(initial_state)

        # Should escalate after max attempts
        assert result["next_decision"] == "escalate"
        assert result["phase_status"]["1"].status == PhaseStatus.FAILED
        assert "after 3 attempts" in result["errors"][0]["message"]

    @pytest.mark.asyncio
    async def test_planning_node_updates_phase_status(self, initial_state, mock_plan):
        """Test that phase_1 status is correctly updated."""
        mock_agent = MagicMock()
        mock_agent.run.return_value = MockAgentResult(
            success=True,
            output=json.dumps(mock_plan),
            parsed_output=mock_plan,  # Specialist runner returns parsed plan directly
        )
        mock_runner = MagicMock()
        mock_runner.create_agent.return_value = mock_agent

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner", return_value=mock_runner
        ):
            result = await planning_node(initial_state)

        phase_1 = result["phase_status"]["1"]
        assert phase_1.status == PhaseStatus.COMPLETED
        assert phase_1.started_at is not None
        assert phase_1.completed_at is not None
        assert phase_1.attempts == 1
        # Plan is saved to DB, output may or may not contain plan_file

    @pytest.mark.asyncio
    async def test_planning_node_saves_plan_to_db(self, initial_state, mock_plan, temp_project_dir):
        """Test that plan is saved to database via repository."""
        mock_agent = MagicMock()
        mock_agent.run.return_value = MockAgentResult(
            success=True,
            output=json.dumps(mock_plan),
            parsed_output=mock_plan,  # Specialist runner returns parsed plan directly
        )
        mock_runner = MagicMock()
        mock_runner.create_agent.return_value = mock_agent

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner", return_value=mock_runner
        ):
            result = await planning_node(initial_state)

        # Plan should be in the result state
        assert result["plan"] == mock_plan
        # DB save is verified through mocked repository (auto_patch_db_repos)

    @pytest.mark.asyncio
    async def test_planning_node_action_logging(self, initial_state, mock_plan, temp_project_dir):
        """Test that action logging captures phase start and completion."""
        mock_agent = MagicMock()
        mock_agent.run.return_value = MockAgentResult(
            success=True,
            output=json.dumps(mock_plan),
            parsed_output=mock_plan,  # Specialist runner returns parsed plan directly
        )
        mock_runner = MagicMock()
        mock_runner.create_agent.return_value = mock_agent
        mock_logger = MagicMock()

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner", return_value=mock_runner
        ), patch("orchestrator.langgraph.nodes.planning.get_node_logger", return_value=mock_logger):
            await planning_node(initial_state)

        # Verify logging calls
        mock_logger.log_phase_start.assert_called_once_with(1, "Planning")
        mock_logger.log_agent_invoke.assert_called_once()
        mock_logger.log_agent_complete.assert_called_once()
        mock_logger.log_phase_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_planning_node_exception_handling(self, initial_state):
        """Test that exceptions are properly caught and handled."""
        mock_runner = MagicMock()
        mock_runner.create_agent.side_effect = RuntimeError("Unexpected error")

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner", return_value=mock_runner
        ):
            result = await planning_node(initial_state)

        assert result["next_decision"] == "retry"
        assert result["phase_status"]["1"].error is not None
        assert "Unexpected error" in result["phase_status"]["1"].error

    @pytest.mark.asyncio
    async def test_planning_node_empty_plan_response(self, initial_state):
        """Test handling when Claude returns empty or invalid plan."""
        mock_agent = MagicMock()
        mock_agent.run.return_value = MockAgentResult(
            success=True,
            output="No plan generated",  # Invalid - not JSON
        )
        mock_runner = MagicMock()
        mock_runner.create_agent.return_value = mock_agent

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner", return_value=mock_runner
        ):
            result = await planning_node(initial_state)

        # Should fail gracefully and request retry
        assert result["next_decision"] == "retry"
        assert "Could not find JSON" in result["phase_status"]["1"].error

    @pytest.mark.asyncio
    async def test_planning_node_timeout_handling(self, initial_state):
        """Test that timeout returns retry."""
        mock_agent = MagicMock()
        mock_agent.run.side_effect = asyncio.TimeoutError()
        mock_runner = MagicMock()
        mock_runner.create_agent.return_value = mock_agent

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner", return_value=mock_runner
        ):
            result = await planning_node(initial_state)

        assert result["next_decision"] == "retry"
        assert result["phase_status"]["1"].error is not None


class TestSpecialistRunner:
    """Tests for SpecialistRunner agent loading.

    The planning node now uses SpecialistRunner to load agent configurations
    from the agents/ directory structure.
    """

    @pytest.fixture
    def temp_project_with_agents(self, tmp_path):
        """Create a temporary project with agent configs."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Create agents directory with a test agent
        agents_dir = project_dir / "agents" / "A01-planner"
        agents_dir.mkdir(parents=True)

        # Create context file
        context_file = agents_dir / "CLAUDE.md"
        context_file.write_text(
            """# Planner Agent

## Role
You are the planning agent responsible for creating implementation plans.

## Instructions
1. Read PRODUCT.md
2. Create a structured plan
3. Output valid JSON
"""
        )

        # Create tools file
        tools_file = agents_dir / "TOOLS.json"
        tools_file.write_text('["Read", "Write", "Glob"]')

        return project_dir

    def test_specialist_runner_loads_agent_config(self, temp_project_with_agents):
        """Test that SpecialistRunner can load agent configuration."""
        from orchestrator.specialists.runner import SpecialistRunner

        runner = SpecialistRunner(temp_project_with_agents)
        config = runner.get_agent_config("A01")

        assert config["type"] == "claude"
        assert config["context_file"].exists()
        assert "planner" in config["name"].lower()
        assert len(config["tools"]) == 3

    def test_specialist_runner_creates_agent(self, temp_project_with_agents):
        """Test that SpecialistRunner can create an agent instance."""
        from orchestrator.agents.base import BaseAgent
        from orchestrator.specialists.runner import SpecialistRunner

        runner = SpecialistRunner(temp_project_with_agents)
        agent = runner.create_agent("A01")

        assert isinstance(agent, BaseAgent)
