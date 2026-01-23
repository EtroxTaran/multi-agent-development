"""Planning node for Phase 1.

Generates implementation plan from PRODUCT.md specification
using Claude CLI via Specialist Runner (A01-planner).
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState, PhaseStatus, PhaseState
from ..integrations.action_logging import get_node_logger
from ...specialists.runner import SpecialistRunner

logger = logging.getLogger(__name__)


class PlanValidationError(Exception):
    """Raised when plan validation fails."""

    def __init__(self, message: str, errors: list[str]):
        super().__init__(message)
        self.errors = errors


def validate_plan(plan: dict) -> None:
    """Validate the structure of a generated plan.

    Ensures the plan has all required fields with proper types to prevent
    downstream failures from malformed plans.

    Args:
        plan: The parsed plan dictionary

    Raises:
        PlanValidationError: If validation fails with list of specific errors
    """
    errors: list[str] = []

    # Required top-level fields
    required_fields = ["plan_name", "tasks"]
    for field in required_fields:
        if field not in plan:
            errors.append(f"Missing required field: '{field}'")

    # Validate plan_name
    if "plan_name" in plan:
        if not isinstance(plan["plan_name"], str):
            errors.append("'plan_name' must be a string")
        elif len(plan["plan_name"].strip()) == 0:
            errors.append("'plan_name' cannot be empty")

    # Validate tasks array
    if "tasks" in plan:
        if not isinstance(plan["tasks"], list):
            errors.append("'tasks' must be an array")
        elif len(plan["tasks"]) == 0:
            errors.append("'tasks' array cannot be empty")
        else:
            # Validate each task
            for i, task in enumerate(plan["tasks"]):
                task_errors = _validate_task(task, i)
                errors.extend(task_errors)

    # Validate optional milestones array if present
    if "milestones" in plan:
        if not isinstance(plan["milestones"], list):
            errors.append("'milestones' must be an array")
        else:
            for i, milestone in enumerate(plan["milestones"]):
                if not isinstance(milestone, dict):
                    errors.append(f"Milestone {i}: must be an object")
                elif "id" not in milestone:
                    errors.append(f"Milestone {i}: missing 'id' field")

    if errors:
        raise PlanValidationError(
            f"Plan validation failed with {len(errors)} error(s)",
            errors
        )


def _validate_task(task: dict, index: int) -> list[str]:
    """Validate a single task in the plan.

    Args:
        task: The task dictionary
        index: Task index for error messages

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []
    prefix = f"Task {index}"

    if not isinstance(task, dict):
        return [f"{prefix}: must be an object"]

    # Required task fields
    required_task_fields = ["id", "title"]
    for field in required_task_fields:
        if field not in task:
            errors.append(f"{prefix}: missing required field '{field}'")

    # Validate id
    if "id" in task:
        if not isinstance(task["id"], str):
            errors.append(f"{prefix}: 'id' must be a string")
        elif len(task["id"].strip()) == 0:
            errors.append(f"{prefix}: 'id' cannot be empty")

    # Validate title
    if "title" in task:
        if not isinstance(task["title"], str):
            errors.append(f"{prefix}: 'title' must be a string")
        elif len(task["title"].strip()) == 0:
            errors.append(f"{prefix}: 'title' cannot be empty")

    # Validate acceptance_criteria if present (should be a list)
    if "acceptance_criteria" in task:
        if not isinstance(task["acceptance_criteria"], list):
            errors.append(f"{prefix}: 'acceptance_criteria' must be an array")

    # Validate file lists if present
    for field in ["files_to_create", "files_to_modify", "test_files"]:
        if field in task and not isinstance(task[field], list):
            errors.append(f"{prefix}: '{field}' must be an array")

    # Validate dependencies if present
    if "dependencies" in task:
        if not isinstance(task["dependencies"], list):
            errors.append(f"{prefix}: 'dependencies' must be an array")

    return errors


async def planning_node(state: WorkflowState) -> dict[str, Any]:
    """Generate implementation plan from specification.

    Uses A01-planner specialist to analyze PRODUCT.md and generate
    a structured implementation plan.

    Args:
        state: Current workflow state

    Returns:
        State updates with plan or errors
    """
    logger.info(f"Starting planning phase for: {state['project_name']}")

    project_dir = Path(state["project_dir"])
    action_logger = get_node_logger(project_dir)
    start_time = time.time()

    # Log phase start
    action_logger.log_phase_start(1, "Planning")

    # Update phase status
    phase_status = state.get("phase_status", {}).copy()
    phase_1 = phase_status.get("1", PhaseState())
    phase_1.status = PhaseStatus.IN_PROGRESS
    phase_1.started_at = datetime.now().isoformat()
    phase_1.attempts += 1
    phase_status["1"] = phase_1

    # Read PRODUCT.md
    product_file = project_dir / "PRODUCT.md"
    if not product_file.exists():
        action_logger.log_error("PRODUCT.md not found", phase=1)
        return {
            "phase_status": phase_status,
            "errors": [{
                "type": "missing_file",
                "file": "PRODUCT.md",
                "message": "PRODUCT.md not found",
                "phase": 1,
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "abort",
        }

    product_spec = product_file.read_text()

    # Build prompt with task granularity reminder (detailed instructions are in A01-planner/CLAUDE.md)
    prompt = f"""PRODUCT SPECIFICATION:
{product_spec}

TASK GRANULARITY REMINDER:
- Each task: max 3 files to create, max 5 files to modify, max 5 acceptance criteria
- Tasks should be completable in <10 minutes
- Prefer many small tasks over few large tasks"""

    # Check for structured correction prompt (richer than just blockers)
    correction_prompt = state.get("correction_prompt")
    if correction_prompt:
        prompt += f"\n\n{correction_prompt}"
        logger.info("Planning with structured correction context from failed validation")
    else:
        # Fallback to basic blockers (legacy support)
        phase_2_status = phase_status.get("2", PhaseState())
        if phase_2_status.blockers:
            blockers_list = "\n".join(f"- {b}" for b in phase_2_status.blockers)
            prompt += f"""

CRITICAL FEEDBACK - PREVIOUS PLAN REJECTED:
Your previous plan was rejected by the review board. You MUST address these specific issues in your new plan:
{blockers_list}

Please revise the plan to resolve these blocking issues."""

    action_logger.log_agent_invoke("A01-planner", "Generating implementation plan", phase=1)

    try:
        # Use SpecialistRunner to execute A01-planner
        runner = SpecialistRunner(project_dir)
        
        result = await asyncio.to_thread(
            runner.create_agent("A01-planner").run,
            prompt
        )

        if not result.success:
            raise Exception(result.error or "Planning failed")

        output = result.output

        # Parse the plan from output
        plan = None
        try:
            plan = json.loads(output)
        except json.JSONDecodeError:
            # Try to extract JSON from text
            json_match = re.search(r"\{[\s\S]*\}", output)
            if json_match:
                plan = json.loads(json_match.group(0))
            else:
                raise Exception("Could not parse plan from response")

        # Validate plan structure before accepting
        try:
            validate_plan(plan)
        except PlanValidationError as e:
            error_details = "\n  - ".join(e.errors)
            raise Exception(f"Plan validation failed:\n  - {error_details}") from e

        # Save plan to database
        from ...db.repositories.phase_outputs import get_phase_output_repository, OutputType
        from ...storage.async_utils import run_async
        repo = get_phase_output_repository(state["project_name"])
        run_async(repo.save_plan(plan))

        logger.info(f"Plan generated: {plan.get('plan_name', 'Unknown')}")

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Log success
        action_logger.log_agent_complete(
            "A01-planner",
            f"Plan generated: {plan.get('plan_name', 'Unknown')}",
            phase=1,
            duration_ms=duration_ms,
            details={"plan_name": plan.get("plan_name")},
        )
        action_logger.log_phase_complete(1, "Planning", duration_ms=duration_ms)

        # Update phase status
        phase_1.status = PhaseStatus.COMPLETED
        phase_1.completed_at = datetime.now().isoformat()
        phase_1.output = {"plan_saved": True}
        phase_status["1"] = phase_1

        return {
            "plan": plan,
            "phase_status": phase_status,
            "current_phase": 2,
            "next_decision": "continue",
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Planning failed: {e}")

        # Log error
        action_logger.log_agent_error("A01-planner", str(e), phase=1, exception=e)

        phase_1.status = PhaseStatus.FAILED
        phase_1.error = str(e)
        phase_status["1"] = phase_1

        # Check if we can retry
        if phase_1.attempts < phase_1.max_attempts:
            action_logger.log_phase_retry(1, phase_1.attempts + 1, phase_1.max_attempts)
            return {
                "phase_status": phase_status,
                "next_decision": "retry",
                "errors": [{
                    "type": "planning_error",
                    "message": str(e),
                    "phase": 1,
                    "attempt": phase_1.attempts,
                    "timestamp": datetime.now().isoformat(),
                }],
            }
        else:
            action_logger.log_phase_failed(1, "Planning", str(e))
            action_logger.log_escalation(f"Planning failed after {phase_1.attempts} attempts", phase=1)
            return {
                "phase_status": phase_status,
                "next_decision": "escalate",
                "errors": [{
                    "type": "planning_error",
                    "message": f"Planning failed after {phase_1.attempts} attempts: {e}",
                    "phase": 1,
                    "timestamp": datetime.now().isoformat(),
                }],
            }
