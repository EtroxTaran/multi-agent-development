"""Tests for planning node.

Tests planning_node, validate_plan, and related helpers.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.langgraph.nodes.planning import (
    PlanValidationError,
    _validate_task,
    planning_node,
    validate_plan,
)
from orchestrator.langgraph.state import PhaseState


class TestValidatePlan:
    """Tests for validate_plan function."""

    def test_valid_plan_passes(self, sample_plan):
        """Test valid plan passes validation."""
        # Should not raise
        validate_plan(sample_plan)

    def test_missing_plan_name_raises(self):
        """Test missing plan_name raises error."""
        plan = {"tasks": [{"id": "T1", "title": "Task 1"}]}

        with pytest.raises(PlanValidationError) as exc_info:
            validate_plan(plan)

        assert any("plan_name" in e for e in exc_info.value.errors)

    def test_missing_tasks_raises(self):
        """Test missing tasks raises error."""
        plan = {"plan_name": "Test Plan"}

        with pytest.raises(PlanValidationError) as exc_info:
            validate_plan(plan)

        assert any("tasks" in e for e in exc_info.value.errors)

    def test_empty_plan_name_raises(self):
        """Test empty plan_name raises error."""
        plan = {
            "plan_name": "   ",
            "tasks": [{"id": "T1", "title": "Task 1"}],
        }

        with pytest.raises(PlanValidationError) as exc_info:
            validate_plan(plan)

        assert any("empty" in e.lower() for e in exc_info.value.errors)

    def test_empty_tasks_array_raises(self):
        """Test empty tasks array raises error."""
        plan = {"plan_name": "Test Plan", "tasks": []}

        with pytest.raises(PlanValidationError) as exc_info:
            validate_plan(plan)

        assert any("empty" in e.lower() for e in exc_info.value.errors)

    def test_invalid_plan_name_type_raises(self):
        """Test non-string plan_name raises error."""
        plan = {
            "plan_name": 123,
            "tasks": [{"id": "T1", "title": "Task 1"}],
        }

        with pytest.raises(PlanValidationError) as exc_info:
            validate_plan(plan)

        assert any("string" in e.lower() for e in exc_info.value.errors)

    def test_invalid_tasks_type_raises(self):
        """Test non-array tasks raises error."""
        plan = {"plan_name": "Test Plan", "tasks": "not an array"}

        with pytest.raises(PlanValidationError) as exc_info:
            validate_plan(plan)

        assert any("array" in e.lower() for e in exc_info.value.errors)

    def test_validates_each_task(self):
        """Test each task is validated."""
        plan = {
            "plan_name": "Test Plan",
            "tasks": [
                {"id": "T1", "title": "Valid Task"},
                {"id": "T2"},  # Missing title
            ],
        }

        with pytest.raises(PlanValidationError) as exc_info:
            validate_plan(plan)

        errors_str = " ".join(exc_info.value.errors)
        assert "Task 1" in errors_str  # Index 1
        assert "title" in errors_str

    def test_validates_milestones_if_present(self):
        """Test milestones are validated when present."""
        plan = {
            "plan_name": "Test Plan",
            "tasks": [{"id": "T1", "title": "Task 1"}],
            "milestones": [{"title": "Missing ID"}],  # Missing id
        }

        with pytest.raises(PlanValidationError) as exc_info:
            validate_plan(plan)

        errors_str = " ".join(exc_info.value.errors)
        assert "Milestone" in errors_str
        assert "id" in errors_str

    def test_invalid_milestones_type_raises(self):
        """Test non-array milestones raises error."""
        plan = {
            "plan_name": "Test Plan",
            "tasks": [{"id": "T1", "title": "Task 1"}],
            "milestones": "not an array",
        }

        with pytest.raises(PlanValidationError) as exc_info:
            validate_plan(plan)

        assert any("milestones" in e.lower() for e in exc_info.value.errors)


class TestValidateTask:
    """Tests for _validate_task helper."""

    def test_valid_task_returns_empty(self):
        """Test valid task returns no errors."""
        task = {
            "id": "T1",
            "title": "Test Task",
            "acceptance_criteria": ["Criterion 1"],
            "files_to_create": ["file.py"],
        }

        errors = _validate_task(task, 0)
        assert errors == []

    def test_missing_id_returns_error(self):
        """Test missing id returns error."""
        task = {"title": "Test Task"}

        errors = _validate_task(task, 0)
        assert any("id" in e for e in errors)

    def test_missing_title_returns_error(self):
        """Test missing title returns error."""
        task = {"id": "T1"}

        errors = _validate_task(task, 0)
        assert any("title" in e for e in errors)

    def test_empty_id_returns_error(self):
        """Test empty id returns error."""
        task = {"id": "  ", "title": "Test"}

        errors = _validate_task(task, 0)
        assert any("empty" in e.lower() for e in errors)

    def test_empty_title_returns_error(self):
        """Test empty title returns error."""
        task = {"id": "T1", "title": ""}

        errors = _validate_task(task, 0)
        assert any("empty" in e.lower() for e in errors)

    def test_invalid_acceptance_criteria_type(self):
        """Test non-array acceptance_criteria returns error."""
        task = {
            "id": "T1",
            "title": "Test",
            "acceptance_criteria": "not an array",
        }

        errors = _validate_task(task, 0)
        assert any("acceptance_criteria" in e for e in errors)

    def test_invalid_files_to_create_type(self):
        """Test non-array files_to_create returns error."""
        task = {
            "id": "T1",
            "title": "Test",
            "files_to_create": "not an array",
        }

        errors = _validate_task(task, 0)
        assert any("files_to_create" in e for e in errors)

    def test_invalid_files_to_modify_type(self):
        """Test non-array files_to_modify returns error."""
        task = {
            "id": "T1",
            "title": "Test",
            "files_to_modify": "not an array",
        }

        errors = _validate_task(task, 0)
        assert any("files_to_modify" in e for e in errors)

    def test_invalid_test_files_type(self):
        """Test non-array test_files returns error."""
        task = {
            "id": "T1",
            "title": "Test",
            "test_files": "not an array",
        }

        errors = _validate_task(task, 0)
        assert any("test_files" in e for e in errors)

    def test_invalid_dependencies_type(self):
        """Test non-array dependencies returns error."""
        task = {
            "id": "T1",
            "title": "Test",
            "dependencies": "T0",  # Should be array
        }

        errors = _validate_task(task, 0)
        assert any("dependencies" in e for e in errors)

    def test_non_dict_task_returns_error(self):
        """Test non-dict task returns error."""
        errors = _validate_task("not a dict", 0)
        assert len(errors) == 1
        assert "object" in errors[0].lower()


class TestPlanningNode:
    """Tests for planning_node."""

    @pytest.mark.asyncio
    async def test_successful_planning(
        self, workflow_state_phase_1, mock_specialist_runner, sample_plan
    ):
        """Test successful plan generation."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=True,
                output=json.dumps(sample_plan),
                error=None,
                model="claude",
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch(
            "orchestrator.langgraph.utils.context_builder.build_agent_context"
        ) as mock_context, patch(
            "orchestrator.langgraph.utils.context_builder.generate_context_index_file"
        ), patch(
            "orchestrator.db.repositories.phase_outputs.get_phase_output_repository"
        ), patch(
            "orchestrator.storage.async_utils.run_async"
        ), patch(
            "orchestrator.langgraph.integrations.action_logging.get_node_logger"
        ) as mock_logger:
            mock_context.return_value = MagicMock(
                document_count=5,
                total_content_size=10000,
                categories_found=["requirements", "architecture"],
                for_planning=MagicMock(return_value="Product spec content"),
            )
            mock_logger.return_value = MagicMock(
                log_phase_start=MagicMock(),
                log_agent_invoke=MagicMock(),
                log_agent_complete=MagicMock(),
                log_phase_complete=MagicMock(),
            )

            result = await planning_node(workflow_state_phase_1)

        assert "plan" in result
        assert result["plan"]["plan_name"] == sample_plan["plan_name"]
        assert result["current_phase"] == 2
        assert result["next_decision"] == "continue"

    @pytest.mark.asyncio
    async def test_planning_with_no_docs_aborts(self, workflow_state_phase_1):
        """Test planning with no documentation aborts."""
        with patch(
            "orchestrator.langgraph.utils.context_builder.build_agent_context"
        ) as mock_context, patch(
            "orchestrator.langgraph.integrations.action_logging.get_node_logger"
        ) as mock_logger:
            mock_context.return_value = MagicMock(document_count=0)
            mock_logger.return_value = MagicMock(
                log_phase_start=MagicMock(),
                log_error=MagicMock(),
            )

            result = await planning_node(workflow_state_phase_1)

        assert "errors" in result
        assert result["next_decision"] == "abort"
        assert any("documentation" in str(e).lower() for e in result["errors"])

    @pytest.mark.asyncio
    async def test_planning_failure_retries(self, workflow_state_phase_1, mock_specialist_runner):
        """Test planning failure triggers retry."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=False,
                output="",
                error="Agent timeout",
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch(
            "orchestrator.langgraph.utils.context_builder.build_agent_context"
        ) as mock_context, patch(
            "orchestrator.langgraph.utils.context_builder.generate_context_index_file"
        ), patch(
            "orchestrator.langgraph.integrations.action_logging.get_node_logger"
        ) as mock_logger:
            mock_context.return_value = MagicMock(
                document_count=5,
                total_content_size=10000,
                categories_found=["requirements"],
                for_planning=MagicMock(return_value="Product spec"),
            )
            mock_logger.return_value = MagicMock(
                log_phase_start=MagicMock(),
                log_agent_invoke=MagicMock(),
                log_agent_error=MagicMock(),
                log_phase_retry=MagicMock(),
            )

            result = await planning_node(workflow_state_phase_1)

        assert "errors" in result
        assert result["next_decision"] == "retry"

    @pytest.mark.asyncio
    async def test_planning_max_retries_escalates(
        self, workflow_state_phase_1, mock_specialist_runner
    ):
        """Test planning escalates after max retries."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=False,
                error="Persistent failure",
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        # Set attempts to max
        workflow_state_phase_1["phase_status"] = {"1": PhaseState(attempts=3, max_attempts=3)}

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch(
            "orchestrator.langgraph.utils.context_builder.build_agent_context"
        ) as mock_context, patch(
            "orchestrator.langgraph.utils.context_builder.generate_context_index_file"
        ), patch(
            "orchestrator.langgraph.integrations.action_logging.get_node_logger"
        ) as mock_logger:
            mock_context.return_value = MagicMock(
                document_count=5,
                total_content_size=10000,
                categories_found=["requirements"],
                for_planning=MagicMock(return_value="Product spec"),
            )
            mock_logger.return_value = MagicMock(
                log_phase_start=MagicMock(),
                log_agent_invoke=MagicMock(),
                log_agent_error=MagicMock(),
                log_phase_failed=MagicMock(),
                log_escalation=MagicMock(),
            )

            result = await planning_node(workflow_state_phase_1)

        assert result["next_decision"] == "escalate"

    @pytest.mark.asyncio
    async def test_planning_uses_correction_prompt(
        self, workflow_state_phase_1, mock_specialist_runner, sample_plan
    ):
        """Test planning uses correction prompt when available."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=True,
                output=json.dumps(sample_plan),
                error=None,
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        # Add correction prompt
        workflow_state_phase_1["correction_prompt"] = "Fix these issues: Missing error handling"

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch(
            "orchestrator.langgraph.utils.context_builder.build_agent_context"
        ) as mock_context, patch(
            "orchestrator.langgraph.utils.context_builder.generate_context_index_file"
        ), patch(
            "orchestrator.db.repositories.phase_outputs.get_phase_output_repository"
        ), patch(
            "orchestrator.storage.async_utils.run_async"
        ), patch(
            "orchestrator.langgraph.integrations.action_logging.get_node_logger"
        ) as mock_logger:
            mock_context.return_value = MagicMock(
                document_count=5,
                categories_found=[],
                total_content_size=1000,
                for_planning=MagicMock(return_value="Product spec"),
            )
            mock_logger.return_value = MagicMock(
                log_phase_start=MagicMock(),
                log_agent_invoke=MagicMock(),
                log_agent_complete=MagicMock(),
                log_phase_complete=MagicMock(),
            )

            await planning_node(workflow_state_phase_1)

        # Verify agent was called with correction prompt included
        call_args = mock_agent.run.call_args[0][0]
        assert "Fix these issues" in call_args

    @pytest.mark.asyncio
    async def test_planning_tracks_execution(
        self, workflow_state_phase_1, mock_specialist_runner, sample_plan
    ):
        """Test planning tracks agent execution."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=True,
                output=json.dumps(sample_plan),
                error=None,
                model="claude-sonnet",
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch(
            "orchestrator.langgraph.utils.context_builder.build_agent_context"
        ) as mock_context, patch(
            "orchestrator.langgraph.utils.context_builder.generate_context_index_file"
        ), patch(
            "orchestrator.db.repositories.phase_outputs.get_phase_output_repository"
        ), patch(
            "orchestrator.storage.async_utils.run_async"
        ), patch(
            "orchestrator.langgraph.integrations.action_logging.get_node_logger"
        ) as mock_logger:
            mock_context.return_value = MagicMock(
                document_count=5,
                categories_found=[],
                total_content_size=1000,
                for_planning=MagicMock(return_value="Product spec"),
            )
            mock_logger.return_value = MagicMock(
                log_phase_start=MagicMock(),
                log_agent_invoke=MagicMock(),
                log_agent_complete=MagicMock(),
                log_phase_complete=MagicMock(),
            )

            result = await planning_node(workflow_state_phase_1)

        assert "last_agent_execution" in result
        execution = result["last_agent_execution"]
        assert execution["agent"] == "claude"
        assert execution["node"] == "planning"
        assert execution["template_name"] == "planning"
        assert execution["success"] is True

    @pytest.mark.asyncio
    async def test_planning_validates_generated_plan(
        self, workflow_state_phase_1, mock_specialist_runner
    ):
        """Test planning validates the generated plan structure."""
        mock_agent = MagicMock()
        # Invalid plan - empty tasks
        mock_agent.run = MagicMock(
            return_value=MagicMock(
                success=True,
                output='{"plan_name": "Test", "tasks": []}',  # Empty tasks
                error=None,
            )
        )
        mock_specialist_runner.create_agent = MagicMock(return_value=mock_agent)

        with patch(
            "orchestrator.langgraph.nodes.planning.SpecialistRunner",
            return_value=mock_specialist_runner,
        ), patch(
            "orchestrator.langgraph.utils.context_builder.build_agent_context"
        ) as mock_context, patch(
            "orchestrator.langgraph.utils.context_builder.generate_context_index_file"
        ), patch(
            "orchestrator.langgraph.integrations.action_logging.get_node_logger"
        ) as mock_logger:
            mock_context.return_value = MagicMock(
                document_count=5,
                total_content_size=10000,
                categories_found=["requirements"],
                for_planning=MagicMock(return_value="Product spec"),
            )
            mock_logger.return_value = MagicMock(
                log_phase_start=MagicMock(),
                log_agent_invoke=MagicMock(),
                log_agent_error=MagicMock(),
                log_phase_retry=MagicMock(),
            )

            result = await planning_node(workflow_state_phase_1)

        # Should fail validation
        assert "errors" in result
        assert result["next_decision"] in ["retry", "escalate"]


class TestPlanValidationError:
    """Tests for PlanValidationError exception."""

    def test_error_stores_message_and_errors(self):
        """Test error stores message and error list."""
        errors = ["Missing field X", "Invalid type for Y"]
        exc = PlanValidationError("Validation failed", errors)

        assert str(exc) == "Validation failed"
        assert exc.errors == errors

    def test_error_is_exception(self):
        """Test PlanValidationError is an Exception."""
        exc = PlanValidationError("Test", [])
        assert isinstance(exc, Exception)
