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

        # Save plan to file
        plan_dir = project_dir / ".workflow" / "phases" / "planning"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_file = plan_dir / "plan.json"
        plan_file.write_text(json.dumps(plan, indent=2))

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
        phase_1.output = {"plan_file": str(plan_file)}
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
